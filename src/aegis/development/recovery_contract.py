"""Conditional sampled recovery reference after a bounded diagnostic window.

No operational authorization, physical calibration, exact finite-time rest, or
interval-verified numerical certificate. Terminal speed/dwell/energy/horizon
are REQUIRED caller inputs. Persistent disturbance prevents an infinite static
position-containment claim for a velocity damper alone.
"""
import math
from .bounded_braking import scalar,vector


def clearance_lower(reference,geometry):
    p=vector(reference['position']);ep=scalar(reference['position_error_m'],'position radius')
    r=scalar(geometry['robot_radius'],'robot radius',positive=True);arena=scalar(geometry['arena_limit'],'arena',positive=True)
    limit=arena-r
    values=[p[2]-r,limit-p[2],limit-abs(p[0]),limit-abs(p[1])]
    for o in geometry['obstacles']:
        c=vector(o['center']);radius=scalar(o['radius'],'obstacle radius')
        values.append(math.hypot(*(x-y for x,y in zip(p,c)))-r-radius)
    value=min(values)-ep
    if not math.isfinite(value):raise ValueError('CLEARANCE_NUMERIC_RANGE')
    return value


def _high(s,threshold,delta,dt):
    n=max(0,math.ceil((s-threshold)/delta)) if s>threshold else 0
    end=s-n*delta
    if end>threshold and n:n+=1;end=s-n*delta
    if end<0 or not math.isfinite(end):raise ValueError('SATURATION_NUMERIC_RANGE')
    path=dt*n*((s-delta)+end)/2 if n else 0.
    return n,end,path


def _decay_to(s,target,*,gain,cap,disturbance,mass,dt):
    sat=cap/gain;eq=disturbance/gain;delta=dt*(cap-disturbance)/mass
    n,sh,path=_high(s,max(target,sat),delta,dt)
    if sh<=target:return n,sh,path
    alpha=dt*gain/mass;q=1-alpha
    if alpha<=0 or q>=1:raise ValueError('DECAY_NUMERIC_RANGE')
    if q==0:return n+1,eq,path+dt*eq
    logq=math.log1p(-alpha);x=sh-eq;y=target-eq
    if not x>y>0:raise ValueError('DECAY_DOMAIN')
    nl=max(1,math.ceil((math.log(y)-math.log(x))/logq))
    power=math.exp(nl*logq)
    if power==0 and x>0:raise ValueError('DECAY_UNDERFLOW')
    end=eq+x*power
    if end>target:
        nl+=1;power=math.exp(nl*logq);end=eq+x*power
    if end>target:raise ValueError('DECAY_ROUNDING_UNRESOLVED')
    path+=dt*(nl*eq+x*q*(-math.expm1(nl*logq))/alpha)
    return n+nl,end,path


def assess_recovery(reference,geometry,*,pre_steps,dt_seconds,probe_force_norm_upper_n,
                    mass_lower_kg,mass_upper_kg,brake_gain_lower_kg_s,brake_gain_upper_kg_s,
                    cap_lower_n,disturbance_upper_n,brake_available_asserted,
                    terminal_speed_m_s,dwell_steps,max_total_steps,max_energy_increase_j,
                    require_infinite_sampled_containment):
    result={'design_status':None,'operational_authorization':False,'registered_criterion':False,
      'required_total_steps':None,'recovery_steps':None,'terminal_speed_bound_m_s':None,
      'finite_sampled_path_upper_m':None,'infinite_sampled_path_upper_m':None,
      'post_horizon_position_containment':'UNSUPPORTED','energy_increase_upper_j':None,
      'numerical_assurance':'FLOATING_POINT_REFERENCE_NOT_INTERVAL_VERIFIED'}
    try:
        if reference['status']!='CONDITIONAL_REFERENCE':raise ValueError('REFERENCE_UNAVAILABLE')
        if type(brake_available_asserted) is not bool or type(require_infinite_sampled_containment) is not bool:raise ValueError('INVALID_ASSERTION_FLAGS')
        if any(type(x) is not int or x<0 for x in (pre_steps,dwell_steps,max_total_steps)):raise ValueError('INVALID_STEP_BUDGET')
        dt=scalar(dt_seconds,'dt',positive=True);mlo=scalar(mass_lower_kg,'minimum mass',positive=True);mhi=scalar(mass_upper_kg,'maximum mass',positive=True)
        clo=scalar(brake_gain_lower_kg_s,'minimum gain',positive=True);chi=scalar(brake_gain_upper_kg_s,'maximum gain',positive=True)
        cap=scalar(cap_lower_n,'force cap',positive=True);d=scalar(disturbance_upper_n,'disturbance')
        goal=scalar(terminal_speed_m_s,'terminal speed',positive=True);u=scalar(probe_force_norm_upper_n,'probe force')
        energy_limit=scalar(max_energy_increase_j,'energy budget')
        if mhi<mlo or chi<clo:raise ValueError('MODEL_BOUND_ORDER')
        if chi*dt/mlo>1:raise ValueError('UNSUPPORTED_DAMPING_STEP')
        if not brake_available_asserted:
            result['design_status']='UNSUPPORTED_BRAKE_AVAILABILITY';return result
        if not d<min(cap,clo*goal):
            result['design_status']='UNSUPPORTED_TERMINAL_AUTHORITY';return result
        if require_infinite_sampled_containment and d>0:
            result['design_status']='UNSUPPORTED_INFINITE_CONTAINMENT_WITH_DISTURBANCE';return result
        s0=math.hypot(*vector(reference['velocity']))+scalar(reference['velocity_error_m_s'],'velocity radius')
        a=(u+d)/mlo;sp=s0+pre_steps*dt*a
        prefix=pre_steps*dt*s0+.5*a*dt*dt*pre_steps*(pre_steps+1)
        nr,end,brake_path=_decay_to(sp,goal,gain=clo,cap=cap,disturbance=d,mass=mhi,dt=dt) if sp>goal else (0,sp,0.)
        total_steps=pre_steps+nr+dwell_steps
        finite_path=prefix+brake_path+dwell_steps*dt*goal  # invariant speed band, conservative dwell travel
        duration=pre_steps*dt
        pre_energy=duration*(u+d)*s0+.5*(duration*(u+d))**2/mlo
        energy=max(pre_energy,.5*mhi*goal*goal) if d>0 else pre_energy
        infinite=None
        if d==0:
            delta=dt*cap/mhi;sat=cap/clo
            nh,sh,high_path=_high(sp,sat,delta,dt)
            alpha=dt*clo/mhi;q=1-alpha
            if alpha<=0 or q>=1:raise ValueError('INFINITE_TAIL_NUMERIC_RANGE')
            infinite=prefix+high_path+dt*sh*q/alpha
        lower=clearance_lower(reference,geometry)
        vals=(s0,sp,prefix,end,finite_path,energy,lower)
        if not all(math.isfinite(v) for v in vals) or (infinite is not None and not math.isfinite(infinite)):raise ValueError('RECOVERY_NUMERIC_RANGE')
        if s0>0 and pre_steps>0 and prefix==0:raise ValueError('PREFIX_UNDERFLOW')
        result.update(required_total_steps=total_steps,recovery_steps=nr,terminal_speed_bound_m_s=end,
          finite_sampled_path_upper_m=finite_path,infinite_sampled_path_upper_m=infinite,
          post_horizon_position_containment=('CONDITIONAL_ZERO_DISTURBANCE_SAMPLED_CONTAINMENT' if infinite<lower else 'NOT_ESTABLISHED_ZERO_DISTURBANCE_PATH_EXCEEDS_CLEARANCE') if infinite is not None else 'UNSUPPORTED_PERSISTENT_DISTURBANCE',
          energy_increase_upper_j=energy,clearance_lower_m=lower,prefix_speed_upper_m_s=sp,
          terminal_condition='SYNTHETIC_SPEED_BAND_AND_DWELL_NOT_EXACT_REST')
        if total_steps>max_total_steps:result['design_status']='DECLINED_HORIZON_BUDGET'
        elif energy>energy_limit:result['design_status']='DECLINED_ENERGY_BUDGET'
        elif finite_path>=lower or (require_infinite_sampled_containment and infinite>=lower):result['design_status']='DECLINED_COMPOSED_CLEARANCE'
        else:result['design_status']='WITHIN_ASSERTED_RECOVERY_DESIGN'
    except (ValueError,TypeError,OverflowError,KeyError,ZeroDivisionError) as exc:
        result.update(design_status='UNSUPPORTED',reason=str(exc))
    return result
