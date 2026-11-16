#!/usr/bin/env python3
"""Eight fixed development assignments; no confirmatory or safety acceptance."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
import mujoco
import numpy as np
from scripts.research import recovery_execution_bridge_v3 as bridge
from scripts.research.audit_bridge_v3 import audit
from scripts.research.configured_noise_pairing import compare_configured
from scripts.research.development_ledger import DevelopmentLedger,LedgerError,LedgerWriteError,inspect_bytes
STUDY='V9-M5 synchronized recovery paired development v1'


def plan():
    rows=[]
    for controller in ('AEGIS_3D_ANCHOR_RECOVERY','AEGIS_3D_RECOVERY_MONITOR'):
        for bias_name,bias in [('nominal',[0.,0.,0.]),('heavy',[.8,.8,-.3])]:
            for synchronized in (False,True):
                identifier=controller.lower()+'_'+bias_name+('_sync' if synchronized else '_legacy')
                config=dict(controller_type=controller,seed=2256000,sensor_bias=bias,max_steps=400,
                    range_bias_m=0.,range_dropout_probability=0.,range_latency_steps=0,
                    anchor_bias_xyz=[0.,0.,0.],anchor_dropout_probability=0.,post_stop_steps=50,
                    velocity_bias_xyz=[0.,0.,0.],velocity_dropout_probability=0.,velocity_scale=1.,
                    velocity_latency_steps=0,velocity_replay_probability=0.,secondary_velocity_scale=1.,
                    secondary_velocity_dropout_probability=0.,fail_vectors_after_stop_proposal=False,
                    navigation_force_method='DIRECTION_PRESERVING_PEAK',recovery_steps=100,post_abstain_steps=25)
                rows.append({'id':identifier,'configuration':config,'synchronized':synchronized,'child':identifier+'.jsonl'})
    return rows


def hashes():
    files=set(bridge.FILES)|{'scripts/research/paired_recovery_study.py','scripts/research/configured_noise_pairing.py','scripts/research/recovery_noise_pairing.py'}
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(files)}


def dump(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def run(directory):
    directory=Path(directory);directory.mkdir()  # never resume/retry/overwrite
    rows=plan();source=hashes()
    manifest={'study':STUDY,'classification':'EXPLORATORY_DEVELOPMENT','assignments':rows,
              'parent_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'source_sha256':source,'runtime_versions':{'python':platform.python_version(),'numpy':np.__version__,'mujoco':mujoco.__version__},
              'governance':'GATE_B_NOT_AUTHORIZED','design':'One previously inspected world; eight dependent assignments, four environment pairs.'}
    dump(directory/'manifest.json',manifest)
    with DevelopmentLedger.create(directory/'batch.jsonl',study=STUDY,assignments=rows,record_events=True) as journal:
        for a in rows:
            if hashes()!=source:raise RuntimeError('source drift before assignment')
            journal.start(a['id'])
            path=directory/a['child']
            try:
                bridge.execute(path,a['configuration'],synchronized=a['synchronized'])
                result=audit(path)
            except (LedgerError,LedgerWriteError,OSError):raise
            except Exception as exc:
                journal.complete(a['id'],status='ERROR',details={'child':a['child'],'error_type':type(exc).__name__,
                    'error':str(exc),'child_sha256':hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None})
                raise  # preserve remaining ASSIGNED cases; no automatic retry
            unchanged=hashes()==source
            status='COMPLETED' if result['execution_status']=='COMPLETED' and unchanged else 'ERROR'
            journal.complete(a['id'],status=status,details={'child':a['child'],'child_sha256':result['input_sha256'],
                'child_execution_status':result['execution_status'],'sources_unchanged':unchanged})
            if not unchanged:raise RuntimeError('source drift after assignment')
        journal.finalize()
    summary=analyze(directory);dump(directory/'summary.json',summary)
    return summary


def analyze(directory):
    directory=Path(directory);manifest=json.loads((directory/'manifest.json').read_text())
    expected=plan()
    if manifest['study']!=STUDY or manifest['assignments']!=expected:raise ValueError('wrong/incomplete assignment manifest')
    if set(manifest['source_sha256'])!=set(hashes()):raise ValueError('source manifest coverage mismatch')
    from scripts.research.evidence_integrity import validate_source_maps
    validate_source_maps(manifest['source_sha256'],manifest['source_sha256'])
    data=inspect_bytes((directory/'batch.jsonl').read_bytes())
    if data['records'][0]['study']!=STUDY or data['records'][0]['assignments']!=expected:raise ValueError('batch/manifest mismatch')
    terminals={r['id']:r for r in data['records'] if r['kind']=='TERMINAL'}
    output=[];children={}
    for a in expected:
        status=data['assignments'][a['id']];path=directory/a['child'];terminal=terminals.get(a['id'])
        row={'id':a['id'],'batch_status':status,'child_execution_status':None,'outcome':None}
        if path.exists():
            raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
            if terminal and terminal['details'].get('child_sha256')!=digest:raise ValueError('child hash mismatch')
            result=audit(path)
            if result['input_sha256']!=digest:raise ValueError('child changed during audit')
            child=inspect_bytes(raw);assignment=child['records'][0]['assignments'][0]
            label='AEGIS_MUJOCO_3D_SYNCHRONIZED_V1_DEVELOPMENT' if a['synchronized'] else 'LEGACY_CLASS_SOURCE_IDENTIFIED_MIXED_PHASE'
            if assignment['configuration']!=a['configuration'] or assignment['environment_id']!=label:raise ValueError('wrong child identity/configuration')
            if any(manifest['source_sha256'].get(k)!=v for k,v in assignment['source_sha256'].items()):raise ValueError('child source identity differs from batch')
            if status=='COMPLETED' and (result['execution_status']!='COMPLETED' or terminal['details'].get('sources_unchanged') is not True):
                raise ValueError('false completed batch assignment')
            events=[r['details'] for r in child['records'] if r['kind']=='EVENT']
            ct=next((r for r in child['records'] if r['kind']=='TERMINAL'),None)
            physical=[e['record'] for e in events if e['type']=='PHYSICS']
            episode=ct['details'].get('episode') if ct else None
            row.update(child_execution_status=result['execution_status'],child_sha256=digest,
                       decision_events=result['decision_events'],physics_events=result['physics_events'],
                       outcome={k:episode[k] for k in ('true_success','false_arrival','abstained','timeout')} if episode else None,
                       last_physics_speed=math.hypot(*physical[-1]['velocity']) if physical else None,
                       observed_physics_collision=any(e['collision'] for e in physical) if physical else None)
            children[a['id']]=(events,result)
        elif status in ('COMPLETED','ERROR') and terminal['details'].get('child_sha256') is not None:
            raise ValueError('missing retained child')
        elif status=='COMPLETED':raise ValueError('completed assignment without child')
        output.append(row)
    pairs=[]
    for i in range(0,len(expected),2):
        a,b=expected[i:i+2];pair={'ids':[a['id'],b['id']],'status':'UNEVALUABLE','reason':'Missing, error or incomplete execution evidence'}
        if all(data['assignments'][x['id']]=='COMPLETED' for x in (a,b)):
            ea,ra=children[a['id']];eb,rb=children[b['id']]
            resets=[next(e['record'] for e in events if e['type']=='RESET') for events in (ea,eb)]
            if any(resets[0][k]!=resets[1][k] for k in ('position','velocity','target')):raise ValueError('paired reset mismatch')
            pairing=compare_configured([e['record'] for e in ea if e['type']=='DECISION'],[e['record'] for e in eb if e['type']=='DECISION'],
                left_config=a['configuration'],right_config=b['configuration'],numerical_tolerance=1e-10)
            agreement=list(pairing['innovation_agreement'].values())+[pairing['anchor_query_ordinal_agreement']]
            pair.update(status='COUPLING_MISMATCH' if False in agreement else 'COMPARABLE_DEVELOPMENT_EVIDENCE',reason=None,pairing=pairing)
        pairs.append(pair)
    return {'classification':'EXPLORATORY_PAIRED_RECOVERY_COMPARISON','ledger_state':data['state'],
            'assignments':output,'declared_pairs':4,'pairs':pairs,'governance':'GATE_B_NOT_AUTHORIZED',
            'limitations':['One inspected development world, not independent reliability trials or confirmatory results.',
                           'Environment synchronization changes control inputs and solver state, not merely reporting.',
                           'Self-reported hashes/runtime cannot authenticate execution; residual motion is not safe stopping.']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('directory',type=Path);p.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.mode=='run':run(args.directory)
    else:
        if args.output is None:p.error('audit requires new --output path')
        dump(args.output,analyze(args.directory))
