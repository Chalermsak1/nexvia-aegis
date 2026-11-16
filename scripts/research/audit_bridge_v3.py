"""Read-only timing/coverage audit, not full physical or statistical validation."""
import hashlib
import math
from pathlib import Path
from scripts.research.development_ledger import inspect_bytes
from scripts.research.evidence_integrity import validate_source_maps
from scripts.research.recovery_execution_bridge_v3 import STUDY, FILES
from scripts.research.configured_noise_pairing import validate


def number(x):return type(x) in (float,int) and math.isfinite(x)


def snapshot(value, coherent=False):
    required={'configuration','timestep','integrator','gravity','body_mass','geom_size','geom_pos','obstacles','cbf','versions'}
    if not isinstance(value,dict) or set(value)!=required:raise ValueError('incomplete runtime snapshot')
    if not number(value['timestep']) or value['timestep']<=0 or type(value['integrator']) is not int or value['integrator']<0:
        raise ValueError('invalid runtime scalar')
    def vector(v):return isinstance(v,list) and len(v)==3 and all(number(x) for x in v)
    if not vector(value['gravity']):raise ValueError('invalid runtime gravity')
    masses=value['body_mass'];sizes=value['geom_size']
    if not isinstance(masses,list) or not masses or any(not number(x) or x<0 for x in masses):raise ValueError('invalid body masses')
    if not isinstance(sizes,list) or not sizes or any(not vector(v) or any(x<0 for x in v) for v in sizes):raise ValueError('invalid geometry sizes')
    from dataclasses import asdict
    from aegis.env.mujoco_3d_cbf import PhysicalWorld3DConfig
    config=value['configuration']
    if not isinstance(config,dict) or set(config)!=set(asdict(PhysicalWorld3DConfig())) or not all(number(x) for x in config.values()):
        raise ValueError('invalid runtime configuration')
    if coherent and config['timestep']!=value['timestep']:raise ValueError('model/configuration timestep mismatch')
    positions=value['geom_pos']
    if not isinstance(positions,list) or len(positions)!=len(sizes) or not all(vector(v) for v in positions):raise ValueError('invalid geometry positions')
    obstacles=value['obstacles']
    if not isinstance(obstacles,list) or not obstacles:raise ValueError('missing obstacle geometry')
    for o in obstacles:
        if not isinstance(o,dict) or set(o)!={'center','radius','geom_id'} or not vector(o['center']) or not number(o['radius']) or o['radius']<=0:raise ValueError('invalid obstacle geometry')
        if type(o['geom_id']) is not int or not 0<=o['geom_id']<len(sizes):raise ValueError('invalid obstacle model index')
        if coherent and (positions[o['geom_id']]!=o['center'] or sizes[o['geom_id']][0]!=o['radius']):raise ValueError('obstacle differs from compiled geometry')
    cbf=value['cbf']
    if not isinstance(cbf,dict) or set(cbf)!={'mass','robot_radius','arena_limit','force_limit','gamma','safety_margin'} or not all(number(v) for v in cbf.values()):raise ValueError('invalid CBF runtime')
    if coherent:
        fields={'mass':'robot_mass','robot_radius':'robot_radius','arena_limit':'arena_limit','force_limit':'control_force_limit','gamma':'cbf_gamma','safety_margin':'safety_margin'}
        if any(cbf[k]!=config[v] for k,v in fields.items()):raise ValueError('CBF/configuration mismatch')
    versions=value['versions']
    if not isinstance(versions,dict) or set(versions)!={'python','numpy','mujoco'} or not all(isinstance(v,str) and v for v in versions.values()):raise ValueError('missing runtime versions')



def _timing_audit(path):
    raw=Path(path).read_bytes();data=inspect_bytes(raw);header=data['records'][0]
    if header['study']!=STUDY or data['schema']!='nexvia-development-ledger/2' or len(header['assignments'])!=1:
        raise ValueError('unsupported bridge contract')
    a=header['assignments'][0];validate(a['configuration'])
    validate_source_maps(a['source_sha256'],a['source_sha256'])
    if set(a['source_sha256'])!=set(FILES):raise ValueError('incomplete source coverage')
    labels={'AEGIS_MUJOCO_3D_SYNCHRONIZED_V1_DEVELOPMENT':'SYNCHRONIZED',
            'LEGACY_CLASS_SOURCE_IDENTIFIED_MIXED_PHASE':'LEGACY_MIXED_POSITION_VELOCITY'}
    if a['environment_id'] not in labels:raise ValueError('unknown environment')
    reset=False;dt=None;decisions=[];physics=0;perdecision=0;terminal=None;runtime=None
    for item in data['records'][1:]:
        if item['kind']=='TERMINAL':terminal=item;continue
        if item['kind']!='EVENT':continue
        e=item['details'];kind=e['type'];r=e['record']
        if kind=='RUNTIME':
            if runtime is not None or reset or decisions or physics:raise ValueError('duplicate/late runtime event')
            snapshot(r,coherent=True);runtime=r;continue
        if runtime is None:raise ValueError('observation before runtime')
        time=e['simulation_time_seconds'];stepdt=e['runtime_timestep_seconds']
        if kind not in ('RESET','DECISION','PHYSICS'):raise ValueError('unknown event')
        if e['environment_id']!=a['environment_id'] or not number(time) or not number(stepdt) or stepdt<=0:
            raise ValueError('invalid event identity/time')
        if kind=='RESET':
            if reset or decisions or physics or time!=0 or e['physical_state_phase']!='FORWARD_REFRESH_RESET':
                raise ValueError('invalid reset chronology')
            if (r['configuration']!=runtime['configuration'] or r['integrator']!=runtime['integrator'] or r['gravity']!=runtime['gravity']):
                raise ValueError('reset/runtime mismatch')
            dt=r['configuration']['timestep']
            if not number(dt) or dt<=0 or stepdt!=dt:raise ValueError('invalid reset timestep')
            reset=True;continue
        if not reset or stepdt!=dt or e['physical_state_phase']!=labels[a['environment_id']]:raise ValueError('phase/timestep mismatch')
        if kind=='DECISION':
            if decisions and (decisions[-1]['effective_decision'] in ('STOP','ABSTAIN') or perdecision!=1):
                raise ValueError('decision advanced without matching transition')
            if type(r['step']) is not int or r['step']!=len(decisions) or not math.isclose(time,physics*dt,rel_tol=0,abs_tol=1e-10):
                raise ValueError('decision time/order mismatch')
            if r['effective_decision'] not in ('NAVIGATE','VERIFY','PROBE','STOP','ABSTAIN'):raise ValueError('unknown decision')
            decisions.append(r);perdecision=0
        else:
            if not decisions or type(r['physics_step']) is not int or r['physics_step']!=physics+1 or type(r['decision_step']) is not int or r['decision_step']!=len(decisions)-1:
                raise ValueError('physics identity/order mismatch')
            label=decisions[-1]['effective_decision']
            stage='POST_STOP_BRAKE' if label=='STOP' else ('ABSTAIN_BRAKE' if perdecision==0 else 'POST_ABSTAIN_BRAKE') if label=='ABSTAIN' else 'MAIN'
            limit=a['configuration']['post_stop_steps'] if label=='STOP' else 1+a['configuration']['post_abstain_steps'] if label=='ABSTAIN' else 1
            physics+=1;perdecision+=1
            if r['stage']!=stage or perdecision>limit or not math.isclose(time,physics*dt,rel_tol=0,abs_tol=1e-10):
                raise ValueError('physics stage/time/coverage mismatch')
    status=data['assignments'][a['id']]
    if terminal:
        detail=terminal['details']
        if detail['runtime_before']!=runtime:raise ValueError('terminal/runtime baseline mismatch')
        if detail['runtime_after'] is not None:snapshot(detail['runtime_after'])
        if status=='COMPLETED' and (runtime is None or detail['runtime_after']!=runtime):
            raise ValueError('completed with runtime drift/missing runtime')
    if status=='COMPLETED':
        if not reset or not decisions:raise ValueError('completed run without reset/decisions')
        detail=terminal['details'];episode=detail['episode'];config=a['configuration']
        validate_source_maps(a['source_sha256'],detail['source_sha256_after'])
        if (type(episode['steps']) is not int or episode['steps']!=len(decisions) or
                episode['seed']!=config['seed'] or episode['controller']!=config['controller_type'] or len(decisions)>config['max_steps']):
            raise ValueError('terminal identity/count mismatch')
        label=decisions[-1]['effective_decision']
        expected=config['post_stop_steps'] if label=='STOP' else 1+config['post_abstain_steps'] if label=='ABSTAIN' else 1
        if perdecision!=expected:raise ValueError('completed run missing final physics')
        if label not in ('STOP','ABSTAIN') and len(decisions)!=config['max_steps']:raise ValueError('premature nonterminal completion')
    return {'classification':'DEVELOPMENT_BRIDGE_V2_RUNTIME_TIMING_AUDIT','input_sha256':hashlib.sha256(raw).hexdigest(),
            'ledger_state':data['state'],'execution_status':status,'reset_observed':reset,
            'runtime_observed':runtime is not None,'runtime_unchanged':(terminal['details']['runtime_after']==runtime if terminal and runtime is not None else None),
            'decision_events':len(decisions),'physics_events':physics,'runtime_timestep_seconds':dt,
            'limitations':['Timing/coverage checks only; no geometry, collision truth, outcome acceptance, unmonitored model fields or authentication validation.',
                           'Partial logs remain partial; an unpersisted physical step may exist.'],
            'governance':'GATE_B_NOT_AUTHORIZED'}


def _vector(record,key):
    value=record[key]
    if not isinstance(value,list) or len(value)!=3 or not all(number(x) for x in value):raise ValueError('invalid observed vector: '+key)
    return value


def audit(path):
    raw=Path(path).read_bytes();result=_timing_audit(path)
    if result['input_sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('input changed during audit')
    data=inspect_bytes(raw);decisions=[];physics=[];terminal=None;runtime=None
    for item in data['records']:
        if item['kind']=='TERMINAL':terminal=item
        if item['kind']!='EVENT':continue
        event=item['details'];kind=event['type'];o=event['record']
        if kind=='RUNTIME':runtime=o;continue
        p,t,v=(_vector(o,k) for k in ('position','target','velocity'))
        if kind=='RESET':continue
        key='true_distance' if kind=='DECISION' else 'distance'
        if not number(o[key]) or not math.isclose(o[key],math.dist(p,t),rel_tol=0,abs_tol=1e-10):raise ValueError('distance arithmetic mismatch')
        if kind=='DECISION':decisions.append(o);continue
        if event.get('control_diagnostics_phase')!='PRE_INTEGRATION_CBF':raise ValueError('invalid CBF diagnostic phase')
        _vector(o,'projected_force');integrated=_vector(o,'integrated_translation_qpos')
        if event['physical_state_phase']=='SYNCHRONIZED' and any(not math.isclose(x,y,rel_tol=0,abs_tol=1e-10) for x,y in zip(p,integrated)):raise ValueError('synchronized position differs from integrated state')
        if any(type(o[k]) is not bool for k in ('collision','contact_floor','contact_obstacle')):raise ValueError('invalid contact flags')
        c=runtime['configuration'];radius=c['robot_radius'];limit=c['arena_limit']-radius
        boundary=min(p[2]-radius,limit-p[2],limit-abs(p[0]),limit-abs(p[1]))
        obstacle=min(math.dist(p,v['center'])-radius-v['radius'] for v in runtime['obstacles'])
        for name,expected in [('boundary_clearance',boundary),('min_obstacle_distance',obstacle)]:
            if not number(o[name]) or not math.isclose(o[name],expected,rel_tol=0,abs_tol=1e-10):raise ValueError('clearance contradicts geometry')
        if o['collision']!=(boundary<0 or obstacle<0 or o['contact_floor'] or o['contact_obstacle']):raise ValueError('collision contradicts contacts/geometry')
        if o['cbf_residual'] is not None and not number(o['cbf_residual']):raise ValueError('invalid CBF residual')
        physics.append(o)
    if result['execution_status']=='COMPLETED':
        e=terminal['details']['episode'];last=decisions[-1];label=last['effective_decision']
        outcomes=[e[k] for k in ('true_success','false_arrival','abstained','timeout')]
        if any(type(v) is not int or v not in (0,1) for v in outcomes) or sum(outcomes)!=1:raise ValueError('invalid exclusive outcomes')
        if bool(e['abstained'])!=(label=='ABSTAIN') or bool(e['true_success'] or e['false_arrival'])!=(label=='STOP') or bool(e['timeout'])!=(label not in ('STOP','ABSTAIN')):raise ValueError('outcome contradicts decision')
        distance=last['true_distance'] if label=='STOP' else next(o['distance'] for o in physics if o['stage']=='ABSTAIN_BRAKE') if label=='ABSTAIN' else physics[-1]['distance']
        if not number(e['final_distance']) or e['final_distance']!=round(distance,4):raise ValueError('terminal distance scope mismatch')
    result['classification']='DEVELOPMENT_V3_GEOMETRY_RUNTIME_TIMING_AUDIT'
    result['collision_observed']=any(o['collision'] for o in physics) if physics else None
    result['limitations']=['Self-reported geometry/contact consistency, not independent physical truth or authenticated execution.',
                          'Legacy position remains mixed-phase; synchronized position is checked against recorded integrated translation.',
                          'No stopping acceptance, population-risk or real-robot claim.']
    return result
