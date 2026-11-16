#!/usr/bin/env python3
"""Read-only validation of development decision/physics event chronology."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.research.development_ledger import inspect_bytes
from scripts.research.evidence_integrity import validate_source_maps


def analyze(path):
    raw=Path(path).read_bytes(); ledger=inspect_bytes(raw)
    header=ledger['records'][0]
    if header['study'] not in ('V9-M5 recovery physical evidence v1','V9-M5 recovery physical evidence v2') or ledger['schema']!='nexvia-development-ledger/2':
        raise ValueError('unexpected development study/schema')
    events={a['id']:[] for a in header['assignments']};terminals={}
    for r in ledger['records']:
        if r['kind']=='EVENT':events[r['id']].append(r['details'])
        elif r['kind']=='TERMINAL':terminals[r['id']]=r
    output=[]
    for a in header['assignments']:
        abstain_horizon=a.get('post_abstain_steps',0)
        if type(abstain_horizon) is not int or abstain_horizon<0 or (header['study'].endswith('v1') and abstain_horizon):
            raise ValueError('invalid post-abstention horizon/study')
        if header['study'].endswith('v2') and ('post_abstain_steps' not in a or abstain_horizon<=0):
            raise ValueError('v2 requires explicit post-abstention horizon')
        decisions=[];physics=[];stages=Counter();last=None;perdecision=Counter()
        for event in events[a['id']]:
            record=event['record']
            if event['type']=='DECISION':
                if record.get('effective_decision') not in ('NAVIGATE','PROBE','VERIFY','STOP','ABSTAIN'):
                    raise ValueError('unknown decision label')
                if type(record.get('step')) is not int or record['step']!=len(decisions):raise ValueError('decision order mismatch')
                if last is not None:
                    if last['effective_decision'] in ('STOP','ABSTAIN'):
                        raise ValueError('decision after terminal decision')
                    expected=0 if last['effective_decision']=='STOP' else 1
                    if perdecision[last['step']]!=expected:raise ValueError('decision advanced without physical evidence')
                last=record;decisions.append(record)
            elif event['type']=='PHYSICS':
                if last is None or type(record.get('physics_step')) is not int or record['physics_step']!=len(physics)+1 or type(record.get('decision_step')) is not int or record['decision_step']!=last['step']:
                    raise ValueError('physical step order mismatch')
                decision=last['effective_decision']
                expectedstage='POST_STOP_BRAKE' if decision=='STOP' else (
                    'ABSTAIN_BRAKE' if perdecision[last['step']]==0 else 'POST_ABSTAIN_BRAKE') if decision=='ABSTAIN' else 'MAIN'
                if record.get('stage')!=expectedstage:raise ValueError('physical stage contradicts decision')
                def vector(name):
                    v=record.get(name)
                    if not isinstance(v,list) or len(v)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) for x in v):raise ValueError('invalid physical vector')
                    return v
                p,t=vector('position'),vector('target');vector('velocity');vector('projected_force')
                distance=record.get('distance')
                if type(distance) not in (int,float) or not math.isfinite(distance) or not math.isclose(distance,math.dist(p,t),abs_tol=1e-10):raise ValueError('physical distance mismatch')
                if type(record.get('collision')) is not bool:raise ValueError('invalid collision flag')
                residual=record.get('cbf_residual')
                if residual is not None and (type(residual) not in (int,float) or not math.isfinite(residual)):raise ValueError('invalid residual')
                perdecision[last['step']]+=1
                if decision=='STOP' and perdecision[last['step']]>a['post_stop_steps']:raise ValueError('post-STOP horizon overrun')
                limit=1+abstain_horizon if decision=='ABSTAIN' else 1
                if decision!='STOP' and perdecision[last['step']]>limit:raise ValueError('duplicate physics for decision')
                physics.append(record);stages[record['stage']]+=1
            else:raise ValueError('unknown evidence type')
        terminal=terminals.get(a['id']);status=terminal['status'] if terminal else 'INCOMPLETE'
        if status=='COMPLETED':
            detail=terminal['details'];e=detail['episode'];validate_source_maps(a['source_sha256'],detail['source_sha256_after'])
            if not last or e['controller']!=a['controller'] or e['seed']!=a['seed'] or type(e['steps']) is not int or e['steps']!=len(decisions):raise ValueError('episode identity/count mismatch')
            if type(a.get('max_steps')) is not int or a['max_steps']<=0 or not 1<=len(decisions)<=a['max_steps']:
                raise ValueError('invalid assigned horizon')
            if e.get('navigation_force_method')!=a.get('navigation_force_method') or e.get('recovery_steps_limit')!=a.get('recovery_steps_limit'):
                raise ValueError('episode method/budget mismatch')
            outcomes=[e.get(k) for k in ('true_success','false_arrival','abstained','timeout')]
            if any(type(v) is not int or v not in (0,1) for v in outcomes) or sum(outcomes)!=1:
                raise ValueError('invalid exclusive episode outcomes')
            if bool(e['abstained'])!=(last['effective_decision']=='ABSTAIN'):
                raise ValueError('abstention outcome mismatch')
            if e['timeout'] and (len(decisions)!=a['max_steps'] or last['effective_decision'] in ('STOP','ABSTAIN')):
                raise ValueError('timeout contradicts horizon or decision')
            stopped=last['effective_decision']=='STOP'
            if stopped!=bool(e['true_success'] or e['false_arrival']):raise ValueError('STOP outcome mismatch')
            if stages['POST_STOP_BRAKE']!=(a['post_stop_steps'] if stopped else 0):raise ValueError('incomplete post-STOP physical evidence')
            expected_abstain=abstain_horizon if e['abstained'] else 0
            if stages['POST_ABSTAIN_BRAKE']!=expected_abstain:raise ValueError('incomplete post-abstention evidence')
            if not stopped and perdecision[last['step']]!=(1+expected_abstain):raise ValueError('missing terminal physics')
            score_distance=last['true_distance'] if stopped else (
                next(r['distance'] for r in physics if r['stage']=='ABSTAIN_BRAKE') if e['abstained'] else physics[-1]['distance'])
            if type(e.get('final_distance')) not in (float,int) or e['final_distance']!=round(score_distance,4):
                raise ValueError('historical final_distance scope mismatch')
            post=e.get('post_stop')
            if stopped:
                if not isinstance(post,dict):raise ValueError('missing post-STOP evidence')
                if not math.isclose(post['decision_distance'],last['true_distance'],abs_tol=1e-10) or not math.isclose(post['decision_speed'],math.hypot(*last['velocity']),abs_tol=1e-10):
                    raise ValueError('post-STOP decision measurement mismatch')
                samples=[r for r in physics if r['stage']=='POST_STOP_BRAKE']
                expected=[{'distance':r['distance'],'speed':math.hypot(*r['velocity']),'collision':r['collision'],'cbf_residual':r['cbf_residual']} for r in samples]
                if post is None or len(post['steps'])!=len(expected):raise ValueError('post-STOP terminal evidence missing')
                for x,y in zip(expected,post['steps']):
                    if x['collision']!=y['collision'] or x['cbf_residual']!=y['cbf_residual'] or not math.isclose(x['distance'],y['distance'],abs_tol=1e-10) or not math.isclose(x['speed'],y['speed'],abs_tol=1e-10):raise ValueError('terminal post-STOP evidence differs')
            elif post is not None:
                raise ValueError('post-STOP evidence without STOP')
            abstain=e.get('post_abstain')
            if expected_abstain:
                if not isinstance(abstain,dict) or not isinstance(abstain.get('steps'),list):raise ValueError('missing post-abstention terminal evidence')
                first=[r for r in physics if r['stage']=='ABSTAIN_BRAKE'][0]
                if not math.isclose(abstain['initial_brake_distance'],first['distance'],abs_tol=1e-10) or not math.isclose(abstain['initial_brake_speed'],math.hypot(*first['velocity']),abs_tol=1e-10):
                    raise ValueError('initial abstention brake evidence mismatch')
                samples=[r for r in physics if r['stage']=='POST_ABSTAIN_BRAKE']
                if len(abstain['steps'])!=len(samples):raise ValueError('post-abstention terminal count mismatch')
                for x,y in zip(samples,abstain['steps']):
                    if x['collision']!=y['collision'] or x['cbf_residual']!=y['cbf_residual'] or not math.isclose(x['distance'],y['distance'],abs_tol=1e-10) or not math.isclose(math.hypot(*x['velocity']),y['speed'],abs_tol=1e-10):
                        raise ValueError('post-abstention terminal observations mismatch')
            elif abstain is not None:raise ValueError('unexpected post-abstention terminal evidence')
        output.append({'id':a['id'],'execution_status':status,'decision_events':len(decisions),'physics_events':len(physics),'stage_counts':dict(stages),
            'post_stop_collision_observed':any(r['collision'] for r in physics if r['stage']=='POST_STOP_BRAKE'),
            'post_abstain_collision_observed':any(r['collision'] for r in physics if r['stage']=='POST_ABSTAIN_BRAKE'),
            'limitation':'Post-action observations; crash between physics and persistence can leave an unrecorded step. Active truth-state braking is not a safe-stop claim.'})
    return {'classification':'EXPLORATORY_PHYSICS_EVIDENCE','input_sha256':hashlib.sha256(raw).hexdigest(),'ledger_state':ledger['state'],'assignments':output}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input',type=Path);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=analyze(args.input)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')


if __name__=='__main__':main()
