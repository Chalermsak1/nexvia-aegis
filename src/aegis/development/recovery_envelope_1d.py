"""DEVELOPMENT exact-rational interval enclosure of a declared 1D brake model.

Static delay/cut time are enumerated. Current/past velocity dependence is linked
by the exact sum of intervening velocity increments. Parameters/errors remain
caller assertions, not calibrated bounds. No operational/production authority,
continuous-time guarantee, invariant terminal set or formal proof of software.
"""
from dataclasses import dataclass
from fractions import Fraction as Q
from itertools import product


def rational(x):
    if type(x) is int:
        value=Q(x)
    elif isinstance(x,Q):value=x
    elif type(x) is str and 0<len(x)<=80:
        try:value=Q(x)
        except (ValueError,ZeroDivisionError,OverflowError) as exc:raise ValueError('invalid rational') from exc
    else:raise ValueError('use explicit integer, Fraction or decimal/fraction string; bool/float rejected')
    if max(value.numerator.bit_length(),value.denominator.bit_length())>256:raise ValueError('input rational too large')
    return value


@dataclass(frozen=True)
class Interval:
    lo: Q
    hi: Q

    def __post_init__(self):
        lo,hi=rational(self.lo),rational(self.hi)
        if lo>hi:raise ValueError('interval order')
        object.__setattr__(self,'lo',lo);object.__setattr__(self,'hi',hi)

    def __add__(self,b):return internal(self.lo+b.lo,self.hi+b.hi)
    def __neg__(self):return internal(-self.hi,-self.lo)
    def __sub__(self,b):return self+-b
    def __mul__(self,b):
        values=[a*c for a,c in product((self.lo,self.hi),(b.lo,b.hi))]
        return internal(min(values),max(values))
    def divide_positive(self,b):
        if b.lo<=0:raise ValueError('positive divisor required')
        return self*internal(1/b.hi,1/b.lo)
    def inside(self,b):return b.lo<=self.lo<=self.hi<=b.hi
    def contains(self,x):return self.lo<=x<=self.hi
    def wire(self):return [str(self.lo),str(self.hi)]


def internal(lo,hi):
    # Arithmetic outputs may exceed the input bit limit; exact arithmetic is
    # deliberately retained rather than truncating/rounding an enclosure.
    result=object.__new__(Interval);object.__setattr__(result,'lo',lo);object.__setattr__(result,'hi',hi);return result


def hull(values):return internal(min(x.lo for x in values),max(x.hi for x in values))
def point(x):return internal(x,x)
def ends(x):return (x.lo,) if x.lo==x.hi else (x.lo,x.hi)
def clip(x,lo,hi):return max(lo,min(hi,x))
def slew(f,target,delta):return f+clip(target-f,-delta,delta)

def target_box(velocity,measurement_error,gain,cap):
    raw=-(gain*(velocity+internal(-measurement_error,measurement_error)))
    values=[clip(v,-c,c) for v,c in product(ends(raw),ends(cap))]
    return internal(min(values),max(values))


def force_box(previous,target,rate,cap,dt):
    values=[slew(f,t,r*dt) for f,t,r in product(ends(previous),ends(target),ends(rate))]
    return internal(min(values),max(values))


def linked_velocity(velocity,previous_force,due,lag,error,gain,rate,cap,mass,disturbance,dt):
    """Contractivity-preserving 1D update over a Cartesian state enclosure.

    v_past = v_now - lag_delta_v. For fixed lag/error/parameters, the clipped
    slew map is nonincreasing and gain-Lipschitz in v. Therefore v+h*force/m
    is nondecreasing if h*gain_max/mass_min <= 1. Endpoint velocities suffice.
    Extreme measurement/lag/previous force follow monotonicity; remaining
    positive gain/cap/rate/mass extrema are enumerated. Queue intersection via
    scalar clipping preserves both valid actual targets and this monotonicity.
    """
    result=[]
    for index,(v,f,l,e,d) in enumerate(((velocity.lo,previous_force.lo,lag.lo,error,-disturbance),
                       (velocity.hi,previous_force.hi,lag.hi,-error,disturbance))):
        values=[]
        for g,c,r,m in product(ends(gain),ends(cap),ends(rate),ends(mass)):
            target=clip(clip(-g*(v-l+e),-c,c),due.lo,due.hi)
            force=slew(f,target,r*dt)
            values.append(v+dt*(force+d)/m)
        result.append(min(values) if index==0 else max(values))
    return internal(*result)


def interval_input(x,name):
    if not isinstance(x,list) or len(x)!=2:raise ValueError(name+' requires two rational bounds')
    return Interval(*x)

def spec(raw):
    names={'dt','position','velocity','mass','gain','cap','slew','disturbance','measurement_error','delay_ticks','power_cut_ticks','horizon','safe_position','terminal_velocity','terminal_samples'}
    if not isinstance(raw,dict) or set(raw)!=names:raise ValueError('exact model/criteria fields required')
    result={k:interval_input(raw[k],k) for k in ('position','velocity','mass','gain','cap','slew','safe_position','terminal_velocity')}
    for k in ('dt','disturbance','measurement_error'):result[k]=rational(raw[k])
    if result['dt']<=0 or result['disturbance']<0 or result['measurement_error']<0:raise ValueError('dt/error/disturbance range')
    for k in ('mass','gain','cap','slew'):
        if result[k].lo<=0:raise ValueError(k+' must be positive')
    for k in ('horizon','terminal_samples'):
        if type(raw[k]) is not int or not 1<=raw[k]<=500:raise ValueError(k+' must be integer in 1..500')
        result[k]=raw[k]
    if result['terminal_samples']>result['horizon']:raise ValueError('not enough endpoint samples')
    for name,limit in (('delay_ticks',16),('power_cut_ticks',500)):
        x=raw[name]
        if not isinstance(x,list) or len(x)!=2 or any(type(v) is not int or not 0<=v<=limit for v in x) or x[0]>x[1]:raise ValueError(name+' invalid range')
        result[name]=tuple(x)
    if result['dt']*result['gain'].hi/result['mass'].lo>1:raise ValueError('unsupported feedback step')
    d0,d1=result['delay_ticks'];b0,b1=result['power_cut_ticks']
    # Cut times beyond N are dynamically equivalent on this finite horizon.
    cuts=list(range(b0,min(b1,result['horizon']-1)+1))
    if b1>=result['horizon']:cuts.append(max(b0,result['horizon']))
    if (d1-d0+1)*len(cuts)>128:raise ValueError('branch resource limit exceeded')
    result['cuts']=tuple(cuts)
    return result


def branch(s,delay,cut,*,linked=True):
    v,p=s['velocity'],s['position'];force=point(Q(0));queue=[point(Q(0)) for _ in range(delay)];deltas=[]
    zero=point(Q(0));history=[{'tick':0,'position':p.wire(),'velocity':v.wire(),'force':force.wire()}]
    positions=[p];velocities=[]
    for k in range(s['horizon']):
        if k<cut:
            queue.append(target_box(v,s['measurement_error'],s['gain'],s['cap']));due=queue.pop(0)
            fnext=force_box(force,due,s['slew'],s['cap'],s['dt'])
            independent=v+point(s['dt'])*(fnext+internal(-s['disturbance'],s['disturbance'])).divide_positive(s['mass'])
            if linked and k>=delay:
                lag=zero
                for dv in deltas[k-delay:k]:lag=lag+dv
                candidate=linked_velocity(v,force,due,lag,s['measurement_error'],s['gain'],s['slew'],s['cap'],s['mass'],s['disturbance'],s['dt'])
                vn=internal(max(independent.lo,candidate.lo),min(independent.hi,candidate.hi))
                if vn.lo>vn.hi:raise ValueError('empty enclosure intersection')
            else:vn=independent
            # Delta-v uses the direct force equation, not vn-v (which would
            # lose dependence a second time). This drives the delay link.
            dv=point(s['dt'])*(fnext+internal(-s['disturbance'],s['disturbance'])).divide_positive(s['mass'])
        else:
            fnext=zero;queue=[zero for _ in range(delay)]
            dv=point(s['dt'])*internal(-s['disturbance'],s['disturbance']).divide_positive(s['mass']);vn=v+dv
        pn=p+point(s['dt'])*vn
        deltas.append(dv);v,p,force=vn,pn,fnext;positions.append(p);velocities.append(v)
        history.append({'tick':k+1,'position':p.wire(),'velocity':v.wire(),'force':force.wire()})
    return {'delay':delay,'power_cut':cut,'history':history,
            'finite_containment':all(p.inside(s['safe_position']) for p in positions),
            'terminal_samples':all(v.inside(s['terminal_velocity']) for v in velocities[-s['terminal_samples']:])}


def assess(raw,*,evidence_status,measurement_bounds_asserted,actuator_model_asserted,power_bounds_asserted,linked=True):
    result={'evidence_status':evidence_status,'model_status':'NOT_ASSESSED','conclusion':'UNKNOWN_INPUT',
      'finite_horizon_containment':None,'terminal_sample_condition':None,'future_position_containment':'NOT_ESTABLISHED',
      'operational_authorization':False,'registered_criterion':False,'branches':[],
      'numerical_method':'EXACT_RATIONAL_MODEL_ENCLOSURE_NOT_FORMALLY_VERIFIED_SOFTWARE'}
    try:
        if evidence_status not in ('COMPATIBLE_UNDER_ASSERTED_BOUNDS','CONTRADICTORY','UNKNOWN'):raise ValueError('invalid evidence status')
        flags=(measurement_bounds_asserted,actuator_model_asserted,power_bounds_asserted)
        if any(type(x) is not bool for x in flags) or type(linked) is not bool:raise ValueError('explicit boolean assertions required')
        s=spec(raw)
        for d in range(s['delay_ticks'][0],s['delay_ticks'][1]+1):
            for cut in s['cuts']:result['branches'].append(branch(s,d,cut,linked=linked))
        contained=all(b['finite_containment'] for b in result['branches'])
        terminal=all(b['terminal_samples'] for b in result['branches'])
        result.update(finite_horizon_containment=contained,terminal_sample_condition=terminal,
          model_status='CONDITIONAL_FINITE_CONTAINMENT_AND_TERMINAL_SAMPLES' if contained and terminal else 'CONDITIONAL_FINITE_CONTAINMENT_ONLY' if contained else 'NOT_ESTABLISHED_ENCLOSURE_EXITS_SAFE_SET',
          hypothesis='DECLARED_1D_DELAYED_SLEW_LIMITED_MEASURED_P_POLICY',
          enclosure_method='DELAY_LINKED' if linked else 'INDEPENDENT_BOX_REFERENCE',
          horizon_seconds=str(s['dt']*s['horizon']),terminal_endpoint_span_seconds=str(s['dt']*(s['terminal_samples']-1)))
        if evidence_status=='CONTRADICTORY':result['conclusion']='CONTRADICTORY_EVIDENCE'
        elif evidence_status=='UNKNOWN':result['conclusion']='UNKNOWN_EVIDENCE'
        elif not all(flags):result['conclusion']='UNKNOWN_PHYSICAL_PREMISES'
        elif contained and terminal:result['conclusion']='SUPPORTED_FINITE_MODEL_STATEMENT_ONLY'
        else:result['conclusion']='NOT_ESTABLISHED_BY_THIS_ENCLOSURE'
    except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError) as exc:
        result.update(model_status='UNSUPPORTED_INPUT_OR_MODEL',conclusion='UNKNOWN_INPUT',reason=str(exc))
    return result


def assess_partitioned(raw,*,partitions,max_total_branches=256,**flags):
    """Cover static parameter ranges with closed rational subintervals.

    Cells cover the ORIGINAL complete parameter box, including endpoints. They
    are dependent analysis cells, not new trials. Every cell must establish a
    property for the aggregate to establish it. No failed cell is discarded.
    """
    result={'model_status':'UNSUPPORTED_INPUT_OR_MODEL','conclusion':'UNKNOWN_INPUT',
      'finite_horizon_containment':None,'terminal_sample_condition':None,'future_position_containment':'NOT_ESTABLISHED',
      'operational_authorization':False,'registered_criterion':False,'models':[]}
    try:
        s=spec(raw)
        if not isinstance(partitions,dict) or any(k not in ('mass','gain','cap','slew') for k in partitions):raise ValueError('unsupported partition dimension')
        if any(type(n) is not int or not 1<=n<=16 for n in partitions.values()):raise ValueError('partition count must be 1..16')
        if type(max_total_branches) is not int or not 1<=max_total_branches<=1024:raise ValueError('invalid total branch resource budget')
        dimensions={}
        for key,n in sorted(partitions.items()):
            x=s[key];width=(x.hi-x.lo)/n
            dimensions[key]=[[str(x.lo+i*width),str(x.lo+(i+1)*width)] for i in range(n)]
        total=(s['delay_ticks'][1]-s['delay_ticks'][0]+1)*len(s['cuts'])
        for intervals in dimensions.values():total*=len(intervals)
        if total>max_total_branches:raise ValueError('partition branch resource limit exceeded')
        for choice in product(*dimensions.values()):
            box=dict(zip(dimensions,choice));child=dict(raw,**box);assessment=assess(child,**flags)
            if assessment['model_status']=='UNSUPPORTED_INPUT_OR_MODEL':raise ValueError('child model unsupported: '+assessment.get('reason','unknown'))
            result['models'].append({'parameter_box':box,'assessment':assessment})
        contained=all(x['assessment']['finite_horizon_containment'] for x in result['models'])
        terminal=all(x['assessment']['terminal_sample_condition'] for x in result['models'])
        result.update(enclosure_method='COVERING_STATIC_PARAMETER_PARTITION',partitions=partitions,analysis_branch_count=total,
          evidence_status=result['models'][0]['assessment']['evidence_status'],
          finite_horizon_containment=contained,terminal_sample_condition=terminal,
          model_status='CONDITIONAL_FINITE_CONTAINMENT_AND_TERMINAL_SAMPLES' if contained and terminal else 'CONDITIONAL_FINITE_CONTAINMENT_ONLY' if contained else 'NOT_ESTABLISHED_ENCLOSURE_EXITS_SAFE_SET',
          cells_with_terminal_condition=sum(x['assessment']['terminal_sample_condition'] for x in result['models']))
        conclusions={x['assessment']['conclusion'] for x in result['models']}
        for special in ('CONTRADICTORY_EVIDENCE','UNKNOWN_EVIDENCE','UNKNOWN_PHYSICAL_PREMISES'):
            if special in conclusions:result['conclusion']=special;break
        else:result['conclusion']='SUPPORTED_FINITE_MODEL_STATEMENT_ONLY' if contained and terminal else 'NOT_ESTABLISHED_BY_THIS_ENCLOSURE'
    except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError) as exc:result['reason']=str(exc)
    return result
