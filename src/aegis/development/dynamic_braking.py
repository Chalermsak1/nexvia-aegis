"""DEVELOPMENT delayed/slew-limited force model and measured feedback monitor.

Exact model parameters and channel error budgets are assertions, not calibrated
hardware bounds. No operational authorization, terminal-set or statistical claim.
"""
from collections import deque
import math
from .bounded_braking import scalar,vector,BoundedStatePacket
from .physical_reference import KinematicReference,reading,state_consistency,force_acceleration_reference
from .recovery_contract import clearance_lower


class DelayedSlewBrake:
    """Queued force requests; per-axis slew in N/s, immediate force loss on outage.

    Delay N means request k first affects output k+N. Outage flushes pending
    requests and resets force; restoration must endure a new complete delay.
    This is an asserted force-slew actuator, not a gradual gain approximation.
    """
    def __init__(self,*,delay_ticks,slew_n_s,cap_n,dt_seconds):
        if type(delay_ticks) is not int or delay_ticks<0 or delay_ticks>10000:raise ValueError('invalid delay')
        self.delay=delay_ticks;self.slew=scalar(slew_n_s,'slew',positive=True)
        self.cap=scalar(cap_n,'cap',positive=True);self.dt=scalar(dt_seconds,'dt',positive=True)
        self.delta=self.slew*self.dt
        if not math.isfinite(self.delta) or self.delta<=0:raise ValueError('slew step numeric range')
        self.force=(0.,0.,0.);self.pending=deque([(0.,0.,0.)]*delay_ticks);self.tick=0

    def step(self,request,*,tick,powered):
        if type(tick) is not int or tick!=self.tick:raise ValueError('actuator sequence')
        if type(powered) is not bool:raise ValueError('power must be explicit bool')
        request=vector(request);target=tuple(max(-self.cap,min(self.cap,x)) for x in request)
        if powered:
            self.pending.append(target);due=self.pending.popleft()
            self.force=tuple(old+max(-self.delta,min(self.delta,new-old)) for old,new in zip(self.force,due))
        else:
            self.force=(0.,0.,0.);self.pending=deque([(0.,0.,0.)]*self.delay)
        self.tick+=1
        return list(self.force)


class MeasuredRecoveryMonitor:
    """Pure packet consumer; no plant handle, power truth or true-state input.

    Uses direct measured velocity for braking request; nominal actuator predictor
    for force consistency; independent declared acceleration for state transport.
    A compatible result is consistency under asserted channels, not authenticity.
    """
    def __init__(self,anchor,geometry,*,delay_ticks,slew_n_s,cap_n,dt_seconds,gain,
                 position_error_m,velocity_error_m_s,force_error_n,acceleration_error_m_s2,
                 mass_lower_kg,mass_upper_kg,disturbance_upper_n,terminal_speed_m_s,
                 dwell_ticks,minimum_clearance_m):
        self.dt=scalar(dt_seconds,'dt',positive=True);self.gain=scalar(gain,'gain',positive=True)
        self.ep=scalar(position_error_m,'position error');self.ev=scalar(velocity_error_m_s,'velocity error')
        self.ef=scalar(force_error_n,'force error');self.ea=scalar(acceleration_error_m_s2,'acceleration error')
        self.mlo=scalar(mass_lower_kg,'minimum mass',positive=True);self.mhi=scalar(mass_upper_kg,'maximum mass',positive=True)
        if self.mhi<self.mlo:raise ValueError('mass order')
        self.d=scalar(disturbance_upper_n,'disturbance');self.goal=scalar(terminal_speed_m_s,'terminal speed',positive=True)
        self.margin=scalar(minimum_clearance_m,'minimum clearance')
        if type(dwell_ticks) is not int or dwell_ticks<=0:raise ValueError('dwell must be positive integer')
        self.dwell_required=dwell_ticks;self.geometry=geometry
        # Anchor supplied by measurement interface with independently asserted error budgets.
        p,v=self._packet(anchor,0)
        self.reference=KinematicReference(p,v,position_error_m=self.ep,velocity_error_m_s=self.ev,dt_seconds=self.dt)
        self.predictor=DelayedSlewBrake(delay_ticks=delay_ticks,slew_n_s=slew_n_s,cap_n=cap_n,dt_seconds=self.dt)
        self.tick=0;self.awaiting=False;self.dwell=0;self.ever_inconsistent=False;self.last_pre=None

    def _packet(self,p,tick):
        if not isinstance(p,BoundedStatePacket) or p.frame!='WORLD' or type(p.sequence) is not int or p.sequence!=tick:raise ValueError('state sequence/frame')
        if type(p.acquired_seconds) not in (int,float) or p.acquired_seconds!=tick*self.dt:raise ValueError('state timestamp')
        if p.source!='SIM_DYNAMIC_STATE_V1' or p.bound_basis!='ASSERTED_SYNTHETIC_ERROR_BALL':raise ValueError('state source contract')
        if scalar(p.position_error_m,'position error')!=self.ep or scalar(p.velocity_error_m_s,'velocity error')!=self.ev:raise ValueError('state error contract')
        return vector(p.position),vector(p.velocity)

    def command(self,packet,*,tick):
        if type(tick) is not int or tick!=self.tick or self.awaiting:raise ValueError('monitor sequence')
        try:
            _,velocity=self._packet(packet,tick)
            check=state_consistency(packet,self.reference.snapshot(),tick=tick,dt_seconds=self.dt)
            valid=check['status']=='COMPATIBLE_UNDER_ASSERTED_BOUNDS'
            status='MEASURED_BRAKE_REQUEST' if valid else 'ABSTAIN_REFERENCE_CONTRADICTION'
            request=list(vector([-self.gain*x for x in velocity])) if valid else [0.,0.,0.]
        except (ValueError,TypeError,KeyError,OverflowError):
            check={'status':'UNSUPPORTED'};status='ABSTAIN_STATE_UNAVAILABLE';request=[0.,0.,0.]
        expected=self.predictor.step(request,tick=tick,powered=True)
        self.awaiting=True
        self.last_pre={'type':'COMMAND','tick':tick,'status':status,'request_n':request,'expected_force_n':expected,'state_check':check,
                       'operational_authorization':False}
        return self.last_pre

    def observe(self,force,acceleration,next_state,*,tick):
        if type(tick) is not int or tick!=self.tick or not self.awaiting:raise ValueError('monitor observation sequence')
        expected=self.last_pre['expected_force_n']
        try:
            measured,error=reading(force,'BRAKE_FORCE',tick)
            if error!=self.ef:raise ValueError('force error contract')
            gap=math.dist(measured,expected)
            if not math.isfinite(gap):raise ValueError('force residual numeric range')
            status='INCONSISTENT' if gap>error+1e-12 else 'UNINFORMATIVE_NEAR_ZERO' if math.hypot(*expected)<=2*error else 'COMPATIBLE_UNDER_ASSERTED_ACTUATOR'
            fcheck={'status':status,'force_residual_n':gap}
        except (ValueError,TypeError,OverflowError):fcheck={'status':'UNSUPPORTED','force_residual_n':None}
        try:
            _,ae=reading(acceleration,'ACCELERATION',tick)
            if ae!=self.ea:raise ValueError('acceleration error contract')
            ref=self.reference.advance(acceleration)
            cross=force_acceleration_reference([0.,0.,0.],force,acceleration,tick=tick,mass_lower_kg=self.mlo,mass_upper_kg=self.mhi,disturbance_upper_n=self.d) if fcheck['status']!='UNSUPPORTED' else {'status':'UNSUPPORTED'}
        except (ValueError,TypeError,OverflowError):
            cross={'status':'UNSUPPORTED'}
            # Missing an acceleration interval irreversibly breaks this propagated reference.
            ref=self.reference.advance(None)
        try:
            p,v=self._packet(next_state,tick+1)
            state_check=state_consistency(next_state,ref,tick=tick+1,dt_seconds=self.dt)
            lower=clearance_lower({'position':p,'position_error_m':self.ep},self.geometry)
            speed_upper=math.hypot(*v)+self.ev
            if not math.isfinite(speed_upper):raise ValueError('speed numeric range')
            measured_band=speed_upper<=self.goal and lower>=self.margin
        except (ValueError,TypeError,KeyError,OverflowError):
            state_check={'status':'UNSUPPORTED'};speed_upper=lower=None;measured_band=None
        checks=(self.last_pre['state_check'],fcheck,cross,state_check)
        inconsistent=any(c['status']=='INCONSISTENT' for c in checks)
        unknown=any(c['status']=='UNSUPPORTED' for c in checks)
        self.ever_inconsistent|=inconsistent
        self.dwell=self.dwell+1 if measured_band is True and not inconsistent and not unknown and not self.ever_inconsistent else 0
        result={'type':'OBSERVATION','tick':tick,'force_check':fcheck,'force_acceleration_check':cross,'state_check':state_check,
          'reference_after':ref,'measured_speed_upper_m_s':speed_upper,'measured_clearance_lower_m':lower,
          'measured_speed_and_clearance':measured_band,'consecutive_supported_samples':self.dwell,
          'measured_dwell_under_asserted_channels':self.dwell>=self.dwell_required,
          'assessment':'INCONSISTENCY_OBSERVED' if self.ever_inconsistent else 'UNKNOWN_EVIDENCE' if unknown else 'CONSISTENT_UNDER_ASSERTED_CHANNELS',
          'future_position_containment':'NOT_ESTABLISHED','operational_authorization':False}
        self.awaiting=False;self.tick+=1
        return result
