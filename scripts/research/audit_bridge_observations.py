"""Arithmetic and outcome-label consistency layered on v2 runtime/timing audit."""
import hashlib
import math
from pathlib import Path
from scripts.research.audit_bridge_v2 import audit as timing_audit
from scripts.research.development_ledger import inspect_bytes


def number(x):return type(x) in (float,int) and math.isfinite(x)


def vector(record,key):
    v=record[key]
    if not isinstance(v,list) or len(v)!=3 or not all(number(x) for x in v):
        raise ValueError('invalid observed vector: '+key)
    return v


def audit(path):
    raw=Path(path).read_bytes();result=timing_audit(path)
    if result['input_sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('input changed during audit')
    data=inspect_bytes(raw);decisions=[];physics=[];terminal=None
    for r in data['records']:
        if r['kind']=='TERMINAL':terminal=r
        if r['kind']!='EVENT':continue
        kind=r['details']['type'];o=r['details']['record']
        if kind=='RUNTIME':continue
        p,t,v=(vector(o,key) for key in ('position','target','velocity'))
        if kind=='RESET':continue
        key='true_distance' if kind=='DECISION' else 'distance'
        if not number(o[key]) or not math.isclose(o[key],math.dist(p,t),rel_tol=0,abs_tol=1e-10):
            raise ValueError('observed distance contradicts position/target')
        if kind=='DECISION':decisions.append(o)
        else:
            vector(o,'projected_force')
            if type(o['collision']) is not bool:raise ValueError('invalid collision flag')
            if o['cbf_residual'] is not None and not number(o['cbf_residual']):raise ValueError('invalid residual')
            physics.append(o)
    if result['execution_status']=='COMPLETED':
        episode=terminal['details']['episode'];last=decisions[-1];label=last['effective_decision']
        names=('true_success','false_arrival','abstained','timeout');values=[episode[k] for k in names]
        if any(type(x) is not int or x not in (0,1) for x in values) or sum(values)!=1:
            raise ValueError('invalid exclusive episode outcomes')
        if bool(episode['abstained'])!=(label=='ABSTAIN') or bool(episode['true_success'] or episode['false_arrival'])!=(label=='STOP'):
            raise ValueError('terminal outcome contradicts decision')
        if bool(episode['timeout'])!=(label not in ('STOP','ABSTAIN')):raise ValueError('timeout contradicts decision')
        if label=='STOP':distance=last['true_distance']
        elif label=='ABSTAIN':distance=next(o['distance'] for o in physics if o['stage']=='ABSTAIN_BRAKE')
        else:distance=physics[-1]['distance']
        if not number(episode['final_distance']) or episode['final_distance']!=round(distance,4):
            raise ValueError('terminal distance scope mismatch')
    result['classification']='DEVELOPMENT_BRIDGE_OBSERVATION_CONSISTENCY_AUDIT'
    result['limitations']=['Observed arithmetic and label consistency only; no independent geometry/contact truth, stopping acceptance, authentication or efficacy validation.',
                          'Historical final_distance scope is preserved; physical collision flags are type-checked, not independently verified.',
                          'Incomplete/error evidence remains partial; unpersisted physical steps cannot be reconstructed.']
    return result
