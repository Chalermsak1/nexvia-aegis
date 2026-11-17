"""Fixed synthetic temporal/feedback integration study; zero physics steps."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import platform
import subprocess

from aegis.development.temporal_feedback_1d import TemporalFeedbackSession
from scripts.research import recovery_feedback_study_1d as feedback
from scripts.research.development_ledger import DevelopmentLedger, LedgerError, LedgerWriteError, inspect

ROOT=Path(__file__).resolve().parents[2]
STUDY='V9-M5 bounded temporal feedback integration v1'
FILES=feedback.FILES+('src/aegis/__init__.py','src/aegis/development/__init__.py',
    'src/aegis/development/temporal_feedback_1d.py','scripts/research/temporal_feedback_study_1d.py',
    'tests/test_temporal_feedback_1d.py','tests/test_temporal_feedback_study_1d.py')
canonical,sha=feedback.canonical,feedback.sha


def hashes():return {name:sha((ROOT/name).read_bytes()) for name in FILES}


def packet(kind,tick,sequence=0,**payload):
    return dict(session_id='boot-A',clock_id='clock-A',frame='WORLD_X_SI',source_id=kind,
                kind=kind,sequence=sequence,event_tick=tick,payload=payload)


def ingest(row,received=100):return dict(type='INGEST',packet=row,received_tick=received)
def assess(tick=100,reaction=0):return dict(type='ASSESS',assessment_tick=tick,reaction_delay_ticks=reaction)


def plan():
    result=[]
    def add(name):
        rows=[packet('STATE',100,position=['0','0'],velocity=['.5','.5']),packet('FORCE',100,force=['0','0']),
              packet('POWER',100,absolute_cut_ticks=[260,260])]
        rows += [packet('COMMAND_ENQUEUED',t,sequence=t-97,command_id='c'+str(t),effective_target=['0','0']) for t in (97,98,99)]
        row=dict(id=name,model=deepcopy(feedback.plan()[0]['model']),
                 limits=dict(max_transport_ticks=8,max_state_age_ticks=16,max_reaction_ticks=8,reorder_window=4,max_records=128,max_streams=16),
                 assumptions=dict(feedback.FLAGS),session_id='boot-A',clock_id='clock-A',start_tick=0,
                 operations=[ingest(p) for p in rows]+[assess()])
        result.append(row);return row
    add('nominal_zero_reaction')
    a=add('reaction_latency_three_ticks');a['operations'][-1]=assess(reaction=3)
    a=add('delayed_state_four_ticks');a['operations'][0]['packet']['event_tick']=96
    a=add('replayed_state_not_refreshed');a['operations'][-1:]=[ingest(deepcopy(a['operations'][0]['packet']),101),assess(101)]
    a=add('sequence_body_equivocation');bad=deepcopy(a['operations'][0]['packet']);bad['payload']['position']=['9','9'];a['operations'][-1:]=[ingest(bad),assess()]
    a=add('receipt_clock_rollback');a['operations'][-1:]=[ingest(packet('FORCE',99,sequence=1,force=['0','0']),99),assess(101)]
    a=add('assessment_clock_rollback');a['operations'][-1:]=[assess(99),assess(101)]
    a=add('new_session_old_packet_rejected');old=deepcopy(a['operations'][0]['packet'])
    a['operations'][-1:]=[dict(type='BEGIN_SESSION',session_id='boot-B',clock_id='clock-B',start_tick=0),ingest(old,0),assess(0)]
    a=add('new_session_missing_actuator_history')
    fresh=[packet('STATE',0,position=['0','0'],velocity=['.5','.5']),packet('POWER',0,absolute_cut_ticks=[160,160])]
    for p in fresh:p.update(session_id='boot-B',clock_id='clock-B')
    a['operations'][-1:]=[dict(type='BEGIN_SESSION',session_id='boot-B',clock_id='clock-B',start_tick=0)]+[ingest(p,0) for p in fresh]+[assess(0)]
    a=add('orphan_consumption_then_history')
    a['operations'][-1:]=[ingest(packet('COMMAND_CONSUMED',100,command_id='c96')),assess(),
        ingest(packet('COMMAND_ENQUEUED',96,sequence=3,command_id='c96',effective_target=['0','0'])),assess()]
    a=add('consumed_command_replay_not_requeued');old=deepcopy(a['operations'][3]['packet'])
    a['operations'][-1:]=[ingest(packet('COMMAND_CONSUMED',101,command_id='c97'),101),ingest(old,102),assess(102)]
    a=add('elapsed_time_is_not_execution_ack');a['operations'][-1]=assess(104)
    a=add('expired_absolute_power');a['operations'][2]['packet']['payload']['absolute_cut_ticks']=[80,85]
    a=add('power_deadline_renewal_rejected');a['operations'][-1:]=[ingest(packet('POWER',101,sequence=1,absolute_cut_ticks=[270,280]),101),assess(101)]
    a=add('excess_transport_latency');a['operations'][0]['packet']['event_tick']=90
    a=add('valid_out_of_order_state')
    a['operations']=[ingest(packet('STATE',100,sequence=2,position=['0','0'],velocity=['0','0'])),
        ingest(packet('STATE',99,sequence=1,position=['0','0'],velocity=['0','0'])),ingest(packet('POWER',100,absolute_cut_ticks=[260,260])),assess()]
    a=add('consumption_wrong_static_delay');a['operations'][-1:]=[ingest(packet('COMMAND_CONSUMED',102,command_id='c97'),102),assess(102)]
    a=add('consumption_after_power_flush');a['operations'][2]['packet']['payload']['absolute_cut_ticks']=[99,100]
    a['operations'][-1:]=[ingest(packet('COMMAND_CONSUMED',101,command_id='c97'),101),assess(101)]
    a=add('expired_state_budget');a['operations'][-1]=assess(117)
    a=add('record_budget_requires_resync');a['limits']['max_records']=1
    a=add('stream_budget_requires_resync');a['limits']['max_streams']=1
    a=add('consumption_narrows_delay');a['model']['delay_ticks']=[1,3]
    a['operations'][-1:]=[ingest(packet('COMMAND_CONSUMED',100,command_id='c97')),assess()]
    a=add('inconsistent_static_delays');a['model']['delay_ticks']=[1,3]
    a['operations'][-1:]=[ingest(packet('COMMAND_CONSUMED',100,command_id='c97')),
        ingest(packet('COMMAND_CONSUMED',102,sequence=1,command_id='c98'),102),assess(102)]
    a=add('unsafe_reaction_start_safe_effect')
    a['model'].update(horizon=10,terminal_samples=2,terminal_velocity=['-1','1'])
    a['operations'][0]['packet']['payload'].update(position=['.33','.33'],velocity=['-.5','-.5'])
    a['operations'][-1]=assess(reaction=3)
    return result


def run_case(a,emit=None):
    session=TemporalFeedbackSession(a['model'],session_id=a['session_id'],clock_id=a['clock_id'],
        start_tick=a['start_tick'],limits=a['limits'],assumptions=a['assumptions'])
    responses=[]
    for index,op in enumerate(a['operations']):
        if emit:emit(dict(phase='OPERATION_INTENT',operation_index=index,operation=op))
        if op['type']=='INGEST':r=session.ingest(op['packet'],received_tick=op['received_tick'])
        elif op['type']=='ASSESS':r=session.assess_at(op['assessment_tick'],reaction_delay_ticks=op['reaction_delay_ticks'])
        elif op['type']=='BEGIN_SESSION':r=session.begin_session(**{k:v for k,v in op.items() if k!='type'})
        else:raise ValueError('unsupported operation')
        if emit:emit(dict(phase='OPERATION_RESULT',operation_index=index,status=r['status'],result_sha256=sha(canonical(r))))
        responses.append(dict(operation_index=index,operation_type=op['type'],result=r))
    return dict(responses=responses,physics_steps=0,operational_authorization=False,gate_b='GATE_B_NOT_AUTHORIZED')


def summarize(result):
    r=[row['result'] for row in result['responses'] if row['operation_type']=='ASSESS'][-1]
    a=r['assessment']
    return dict(status=r['status'],conclusion=r.get('conclusion',r['status']),
        reaction_prefix_containment=r['reaction_prefix_containment'],
        post_reaction_containment=None if a is None else a['finite_horizon_containment'],
        combined_finite_horizon_containment=r['combined_finite_horizon_containment'],
        terminal_sample_condition=None if a is None else a['terminal_sample_condition'],
        recovery_analysis_branches=0 if a is None else len(a['branches']),
        command_tracking=r.get('command_tracking',{}),replays_ignored=r.get('replays_ignored',0),
        operation_count=len(result['responses']),operational_authorization=False,action=None,
        future_position_containment='NOT_ESTABLISHED')


def run(directory):
    directory=Path(directory);directory.mkdir(exist_ok=False);sources=hashes()
    metadata=dict(source_sha256=sources,python=platform.python_version(),
        parent_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        gate_b='GATE_B_NOT_AUTHORIZED',classification='DEPENDENT_SYNTHETIC_TEMPORAL_DESIGNS_ZERO_PHYSICS_STEPS')
    assignments=[dict(a,metadata=metadata) for a in plan()]
    with DevelopmentLedger.create(directory/'assignments.jsonl',study=STUDY,assignments=assignments,record_events=True) as w:
        for a in assignments:
            w.start(a['id'])
            try:
                result=run_case(a,emit=lambda e:w.event(a['id'],details=e));raw=canonical(result)
                with (directory/(a['id']+'.json')).open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
                if hashes()!=sources:raise ValueError('sources changed during integration study')
                w.complete(a['id'],status='COMPLETED',details=dict(output_sha256=sha(raw),summary=summarize(result),sources_after=sources))
            except (LedgerError,LedgerWriteError):raise
            except Exception as exc:
                w.complete(a['id'],status='ERROR',details=dict(error_type=type(exc).__name__,error=str(exc)));raise
        w.finalize()
    return audit(directory)


def audit(directory):
    directory=Path(directory);log=inspect(directory/'assignments.jsonl');header=log['records'][0]
    assignments=header['assignments'];metadata=assignments[0]['metadata'];by={a['id']:a for a in assignments}
    if header['study']!=STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments]!=plan():raise ValueError('study/plan mismatch')
    if any(a['metadata']!=metadata for a in assignments) or metadata['gate_b']!='GATE_B_NOT_AUTHORIZED':raise ValueError('metadata mismatch')
    if hashes()!=metadata['source_sha256'] or platform.python_version()!=metadata['python']:raise ValueError('source/runtime mismatch; use recorded source snapshot')
    rows={};active=None;events=[]
    for record in log['records'][1:]:
        if record['kind']=='START':
            if active is not None:raise ValueError('nonsequential operation study')
            active=record['id'];events=[]
        elif record['kind']=='EVENT':
            if record['id']!=active:raise ValueError('event order mismatch')
            events.append(record['details'])
        elif record['kind']=='TERMINAL':
            name=record['id']
            if name!=active:raise ValueError('terminal order mismatch')
            active=None
            if record['status']=='COMPLETED':
                path=directory/(name+'.json')
                if path.is_symlink():raise ValueError('symlinked result unsupported')
                raw=path.read_bytes();details=record['details'];expected_events=[]
                rebuilt=run_case(by[name],emit=expected_events.append)
                if sha(raw)!=details['output_sha256'] or details['sources_after']!=metadata['source_sha256']:raise ValueError('source/output hash mismatch')
                if raw!=canonical(rebuilt) or summarize(rebuilt)!=details['summary'] or events!=expected_events:raise ValueError('recomputed result/summary/durable operations mismatch')
                rows[name]=details['summary']
    return dict(study=STUDY,ledger_state=log['state'],counts=log['counts'],metadata=metadata,
        assignments=[dict(id=a['id'],state=log['assignments'][a['id']],summary=rows.get(a['id'])) for a in assignments],
        unreferenced_result_files=[a['id']+'.json' for a in assignments if a['id'] not in rows and (directory/(a['id']+'.json')).exists()],
        physics_steps=0,operational_authorization=False,gate_b='GATE_B_NOT_AUTHORIZED',
        limitations=['In-memory replay tracking and asserted source/session/clock semantics; no durable trust anchor.',
                    'Bounded finite sessions and exact common clock; variable FIFO delay, clock offset/skew mapping and live deadlines unsupported.',
                    'Sampled 1D conditional enclosures; no continuous-time or real-robot assurance.',
                    'Design fixtures and operation counts are dependent, not statistical reliability trials.'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('run','audit'));p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    r=run(a.directory) if a.mode=='run' else audit(a.directory)
    with a.output.open('xb') as f:f.write(canonical(r));f.flush();os.fsync(f.fileno())
    print(json.dumps(dict(state=r['ledger_state'],counts=r['counts'])))


if __name__=='__main__':main()
