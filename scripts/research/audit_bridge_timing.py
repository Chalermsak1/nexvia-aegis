"""Read-only timing/coverage audit, not full physical or statistical validation."""
import hashlib
import math
from pathlib import Path
from scripts.research.development_ledger import inspect_bytes
from scripts.research.evidence_integrity import validate_source_maps
from scripts.research.recovery_execution_bridge import STUDY, FILES
from scripts.research.configured_noise_pairing import validate


def number(x):return type(x) in (float,int) and math.isfinite(x)


def audit(path):
    raw=Path(path).read_bytes();data=inspect_bytes(raw);header=data['records'][0]
    if header['study']!=STUDY or data['schema']!='nexvia-development-ledger/2' or len(header['assignments'])!=1:
        raise ValueError('unsupported bridge contract')
    a=header['assignments'][0];validate(a['configuration'])
    validate_source_maps(a['source_sha256'],a['source_sha256'])
    if set(a['source_sha256'])!=set(FILES):raise ValueError('incomplete source coverage')
    labels={'AEGIS_MUJOCO_3D_SYNCHRONIZED_V1_DEVELOPMENT':'SYNCHRONIZED',
            'LEGACY_CLASS_SOURCE_IDENTIFIED_MIXED_PHASE':'LEGACY_MIXED_POSITION_VELOCITY'}
    if a['environment_id'] not in labels:raise ValueError('unknown environment')
    reset=False;dt=None;decisions=[];physics=0;perdecision=0;terminal=None
    for item in data['records'][1:]:
        if item['kind']=='TERMINAL':terminal=item;continue
        if item['kind']!='EVENT':continue
        e=item['details'];kind=e['type'];r=e['record'];time=e['simulation_time_seconds'];stepdt=e['runtime_timestep_seconds']
        if kind not in ('RESET','DECISION','PHYSICS'):raise ValueError('unknown event')
        if e['environment_id']!=a['environment_id'] or not number(time) or not number(stepdt) or stepdt<=0:
            raise ValueError('invalid event identity/time')
        if kind=='RESET':
            if reset or decisions or physics or time!=0 or e['physical_state_phase']!='FORWARD_REFRESH_RESET':
                raise ValueError('invalid reset chronology')
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
    return {'classification':'DEVELOPMENT_BRIDGE_TIMING_AUDIT','input_sha256':hashlib.sha256(raw).hexdigest(),
            'ledger_state':data['state'],'execution_status':status,'reset_observed':reset,
            'decision_events':len(decisions),'physics_events':physics,'runtime_timestep_seconds':dt,
            'limitations':['Timing/coverage checks only; no geometry, collision truth, outcome acceptance, runtime drift or authentication validation.',
                           'Partial logs remain partial; an unpersisted physical step may exist.'],
            'governance':'GATE_B_NOT_AUTHORIZED'}
