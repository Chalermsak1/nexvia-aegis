"""DEVELOPMENT sampled 1D backup-reserve supervisor and invariant set.

Hypothesized, power-independent sampled spring/damper backup. This is NOT existing
robot hardware. Static exact parameters, bounded additive force, no-impulse
handoff and an independent bounded-delay trigger are explicit premises. No
physical dispatch, source authentication, continuous-time or release authority.
"""
from fractions import Fraction as Q
from itertools import product
from .recovery_feedback_state_1d import _number,_bounds,_fields,_tick,_label
from .recovery_envelope_1d import internal,point
from .runtime_readiness import select_response


def _solve(matrix,rhs):
    rows=[list(row)+[value] for row,value in zip(matrix,rhs)]
    for col in range(3):
        pivot=next((i for i in range(col,3) if rows[i][col]),None)
        if pivot is None:raise ValueError('singular discrete Lyapunov equation')
        rows[col],rows[pivot]=rows[pivot],rows[col];scale=rows[col][col]
        rows[col]=[x/scale for x in rows[col]]
        for i in range(3):
            if i!=col:
                scale=rows[i][col];rows[i]=[x-scale*y for x,y in zip(rows[i],rows[col])]
    return [row[-1] for row in rows]


def _quad(p,x,y):return p[0][0]*x*x+2*p[0][1]*x*y+p[1][1]*y*y
def _wire(matrix):return [[str(x) for x in row] for row in matrix]


def model(raw):
    _fields(raw,'dt mass spring damping position_scale velocity_scale anchor level force_cap disturbance safe_position')
    s={k:_number(raw[k]) for k in raw if k!='safe_position'};s['safe_position']=_bounds(raw['safe_position'])
    if any(s[k]<=0 for k in ('dt','mass','spring','damping','position_scale','velocity_scale','level','force_cap')) or s['disturbance']<0:
        raise ValueError('positive model/level parameters and nonnegative disturbance required')
    h,m,k,c,L,V=[s[key] for key in ('dt','mass','spring','damping','position_scale','velocity_scale')]
    a,b,d,e=1-h*h*k/m,h*V/L*(1-h*c/m),-h*k*L/(m*V),1-h*c/m
    A=((a,b),(d,e));B=(h*h/(m*L),h/(m*V))
    p,q,r=_solve(((a*a-1,2*a*d,d*d),(a*b,a*e+b*d-1,d*e),(b*b,2*b*e,e*e-1)),(Q(-1),Q(0),Q(-1)))
    det=p*r-q*q
    if p<=0 or r<=0 or det<=0:raise ValueError('positive-definite Lyapunov solution not established')
    P=((p,q),(q,r));inverse=((r/det,-q/det),(-q/det,p/det));trace=p+r
    # These exact checks make the algebraic premise explicit, independent of
    # a floating eigensolver. P-I=A^T P A must be positive semidefinite.
    if p<1 or r<1 or (p-1)*(r-1)-q*q<0:raise ValueError('Lyapunov contraction premise unsupported')
    for i,j in product(range(2),repeat=2):
        value=sum(A[u][i]*P[u][v]*A[v][j] for u,v in product(range(2),repeat=2))
        if value-P[i][j]!=(-1 if i==j else 0):raise ValueError('exact discrete Lyapunov identity mismatch')
    rho=1-1/(2*trace)
    beta=_quad(P,*B);minimum=s['disturbance']**2*beta/(1-rho)**2
    level=s['level'];pos2=level*L*L*inverse[0][0];vel2=level*V*V*inverse[1][1]
    force2=level*_quad(inverse,k*L,c*V)
    margin=min(s['anchor']-s['safe_position'].lo,s['safe_position'].hi-s['anchor'])
    s.update(A=A,B=B,P=P,inverse=inverse,trace=trace,rho=rho,minimum_level=minimum,
             position_bound_squared=pos2,velocity_bound_squared=vel2,force_bound_squared=force2,
             invariant=level>=minimum and margin>=0 and pos2<=margin*margin and force2<=s['force_cap']**2)
    return s


def certificate(raw):
    s=model(raw)
    return dict(status='CONDITIONAL_SAMPLED_INVARIANT_SET' if s['invariant'] else 'INVARIANCE_NOT_ESTABLISHED',
        A=_wire(s['A']),B=[str(x) for x in s['B']],P=_wire(s['P']),P_inverse=_wire(s['inverse']),
        level=str(s['level']),minimum_disturbance_level=str(s['minimum_level']),contraction_upper=str(s['rho']),
        position_bound_squared=str(s['position_bound_squared']),velocity_bound_squared=str(s['velocity_bound_squared']),
        backup_force_bound_squared=str(s['force_bound_squared']),
        level_sufficient=s['level']>=s['minimum_level'],force_cap_sufficient=s['force_bound_squared']<=s['force_cap']**2,
        safe_region_sufficient=(min(s['anchor']-s['safe_position'].lo,s['safe_position'].hi-s['anchor'])>=0 and
            s['position_bound_squared']<=min(s['anchor']-s['safe_position'].lo,s['safe_position'].hi-s['anchor'])**2),
        asymptotic_origin_convergence_under_zero_disturbance=s['invariant'] and s['disturbance']==0,
        physical_hardware_verified=False,operational_authorization=False,
        scope='EXACT_DECLARED_SAMPLED_POINT_PARAMETER_MODEL_NOT_FORMALLY_VERIFIED_CODE')


def energy_box(s,position,velocity):
    return max(_quad(s['P'],(p-s['anchor'])/s['position_scale'],v/s['velocity_scale'])
               for p,v in product((position.lo,position.hi),(velocity.lo,velocity.hi)))


def bridge(s,p,v,steps,active_cap,environment_force):
    # Arbitrary capped force covers old carried force and pending requests.
    # No unknown command is assumed zero and no healthy software is assumed.
    acceleration=internal(-(active_cap+environment_force)/s['mass'],(active_cap+environment_force)/s['mass'])
    result=[];h=s['dt']
    for n in range(steps+1):
        pn=p+point(n*h)*v+point(h*h*n*(n+1)/2)*acceleration;vn=v+point(n*h)*acceleration
        result.append(dict(tick=n,position=pn.wire(),velocity=vn.wire(),energy_upper=str(energy_box(s,pn,vn)),
                           in_backup_set=energy_box(s,pn,vn)<=s['level'],inside_safe_region=pn.inside(s['safe_position'])))
    return result


def assess_supervisor(backup,state,*,assessment_tick,boot_id,active_force_cap,environment_force,
                      handoff_delay_ticks,monitor_ticks,max_state_age_ticks,premises,primary):
    out=dict(status='UNRESOLVED_PHYSICAL_RESPONSE',development_action=None,dispatch=False,operational_authorization=False,
        hardware_validation=False,conditional_future_sampled_containment=False,scope='PROPOSED_BACKUP_MODEL_ONLY')
    try:
        s=model(backup);proof=certificate(backup);out['backup_certificate']=proof
        _fields(state,'boot_id epoch_tick position velocity source_id evidence_status');_label(state['source_id']);_label(boot_id)
        _tick(assessment_tick);_tick(state['epoch_tick'])
        flags='state_bounds_asserted active_cap_asserted backup_model_asserted independent_handoff_asserted power_independent_backup_asserted no_impulse_handoff_asserted'
        _fields(premises,flags)
        if any(type(x) is not bool for x in premises.values()):raise ValueError('explicit boolean backup premises required')
        if not all(premises.values()):return dict(out,reason='UNESTABLISHED_BACKUP_OR_HANDOFF_PREMISE')
        if state['boot_id']!=boot_id:return dict(out,reason='BOOT_MISMATCH')
        if state['evidence_status']!='COMPATIBLE_UNDER_ASSERTED_BOUNDS':return dict(out,reason='NO_SUPPORTED_BACKUP_STATE')
        if type(max_state_age_ticks) is not int or not 0<=max_state_age_ticks<=16:raise ValueError('bounded explicit state transport age required')
        age=assessment_tick-state['epoch_tick']
        if not 0<=age<=max_state_age_ticks:return dict(out,reason='STATE_EPOCH_UNSUPPORTED')
        if not isinstance(handoff_delay_ticks,list) or len(handoff_delay_ticks)!=2 or any(type(x) is not int or not 0<=x<=16 for x in handoff_delay_ticks) or handoff_delay_ticks[0]>handoff_delay_ticks[1]:raise ValueError('bounded handoff delay interval required')
        if type(monitor_ticks) is not int or not 1<=monitor_ticks<=16:raise ValueError('explicit monitoring interval required')
        cap,external=_number(active_force_cap),_number(environment_force)
        if cap<0 or external!=s['disturbance']:raise ValueError('one consistent persistent environmental force bound required')
        p,v=_bounds(state['position']),_bounds(state['velocity'])
        aged=bridge(s,p,v,age,cap,external)[-1];p,v=_bounds(aged['position']),_bounds(aged['velocity'])
        low,high=handoff_delay_ticks;prefix=bridge(s,p,v,monitor_ticks+high,cap,external)
        current_ok=all(x['inside_safe_region'] for x in prefix[:high+1]) and all(prefix[j]['in_backup_set'] for j in range(low,high+1))
        continue_ok=all(x['inside_safe_region'] for x in prefix) and all(prefix[j]['in_backup_set'] for j in range(monitor_ticks+low,monitor_ticks+high+1))
        out.update(bridge=prefix,assessment_tick=assessment_tick,current_handoff_supported=current_ok,
                   continued_operation_reserve_supported=continue_ok,transported_position=p.wire(),transported_velocity=v.wire())
        if not s['invariant']:return dict(out,reason='BACKUP_INVARIANT_MODEL_NOT_ESTABLISHED')
        if not current_ok:return dict(out,reason='CURRENT_HANDOFF_REACHES_OUTSIDE_CERTIFIED_REGION')
        temporal=None
        if primary is None:
            ready=dict(status='NO_JUSTIFIED_RESPONSE',reason='PRIMARY_RESULT_UNAVAILABLE')
        else:
            _fields(primary,'temporal deadline restart calibration');temporal=primary['temporal']
            # Do not mix a stale nominal result with a newer backup estimate.
            ready=select_response(temporal,deadline=primary['deadline'],restart=primary['restart'],calibration=primary['calibration'],boot_id=boot_id,mode='DEVELOPMENT_SIMULATION')
        if ready['status']=='DEVELOPMENT_RECOVERY_CANDIDATE_ONLY':
            if temporal.get('assessment_tick')!=assessment_tick:return dict(out,reason='PRIMARY_ASSESSMENT_EPOCH_MISMATCH')
            a=temporal['preparation']['model']
            if (_number(a['dt'])!=s['dt'] or not _bounds(a['mass']).contains(s['mass']) or _bounds(a['cap']).hi>cap
                    or _number(a['disturbance'])<external or _bounds(a['safe_position'])!=s['safe_position']):
                return dict(out,reason='PRIMARY_AND_BACKUP_PHYSICAL_CONTRACT_MISMATCH')
            for x,y in ((p,_bounds(a['position'])),(v,_bounds(a['velocity']))):
                if max(x.lo,y.lo)>min(x.hi,y.hi):return dict(out,reason='CONTRADICTORY_PRIMARY_AND_BACKUP_STATE_BOUNDS')
        action='CONTINUE_WITH_BACKUP_RESERVE' if ready['status']=='DEVELOPMENT_RECOVERY_CANDIDATE_ONLY' and continue_ok else 'HANDOFF_TO_PASSIVE_BACKUP'
        return dict(out,status='CONDITIONAL_DEVELOPMENT_PLAN',development_action=action,
                    conditional_future_sampled_containment=True,reason=None,primary_decision=ready)
    except (ValueError,TypeError,KeyError,OverflowError,ZeroDivisionError,AttributeError) as exc:
        return dict(out,status='UNKNOWN_INPUT',reason=str(exc))


def check_backup_step(backup,before,after):
    """Necessary sampled consistency check, not sensor/source authentication."""
    s=model(backup)
    if before is None or after is None:return dict(status='UNKNOWN_BACKUP_OBSERVATION',operational_authorization=False)
    _fields(before,'position velocity');_fields(after,'position velocity')
    p,v=_bounds(before['position']),_bounds(before['velocity'])
    force=-(point(s['spring'])*(p-point(s['anchor']))+point(s['damping'])*v)
    # Physical simulator clips; the invariant proof establishes no saturation
    # within its set. Outside that set this remains only a consistency check.
    cap=s['force_cap'];force=internal(max(-cap,min(cap,force.lo)),max(-cap,min(cap,force.hi)))
    vn=v+point(s['dt']/s['mass'])*(force+internal(-s['disturbance'],s['disturbance']));pn=p+point(s['dt'])*vn
    compatible=all(max(a.lo,b.lo)<=min(a.hi,b.hi) for a,b in ((pn,_bounds(after['position'])),(vn,_bounds(after['velocity']))))
    return dict(status='COMPATIBLE_UNDER_ASSERTED_BACKUP_MODEL' if compatible else 'BACKUP_MODEL_OR_EVIDENCE_CONTRADICTION',
                predicted_position=pn.wire(),predicted_velocity=vn.wire(),operational_authorization=False)
