"""Read-only one-episode-at-a-time audit of the retained physical-reference study.

Reuses the same scientific/physics reconstruction as the existing reader. Study
writers are sequential; interleaved assignments are rejected explicitly here.
Cross-arm comparisons use canonical SHA-256 fingerprints, not authenticity.
"""
import argparse,hashlib,json
from pathlib import Path
from scripts.research.streaming_ledger import LedgerStream
from scripts.research.development_ledger import _encode
from scripts.research import physical_reference_study as reference


def fingerprint(events):
    reset={k:events[0][k] for k in ('runtime','position','velocity','reference_anchor')}
    pose=hashlib.sha256();aux=hashlib.sha256()
    for e in events:
        if e['type']=='TICK':pose.update(_encode(e['noise'])+b'\n')
        elif e['type']=='SENSORS':aux.update(_encode({k:e['measurements'][k] for k in ('force_noise','acceleration_noise')})+b'\n')
    return {'reset':hashlib.sha256(_encode(reset)).hexdigest(),'pose_noise':pose.hexdigest(),'reference_noise':aux.hexdigest()}


def audit(path):
    assignments=meta=None;active=None;events=[];summaries={};fingerprints={};peak=0
    with LedgerStream(path) as reader:
        for r in reader:
            kind=r['kind']
            if kind=='HEADER':
                assignments=r['assignments']
                if r['study']!=reference.STUDY or [{k:v for k,v in a.items() if k!='metadata'} for a in assignments]!=reference.plan():raise ValueError('study/plan mismatch')
                meta=assignments[0]['metadata'];by_id={a['id']:a for a in assignments}
                if any(a['metadata']!=meta for a in assignments):raise ValueError('metadata mismatch')
            elif kind=='START':
                if active is not None:raise ValueError('study adapter requires sequential assignments')
                active=r['id'];events=[]
            elif kind=='EVENT':
                if r['id']!=active:raise ValueError('nonsequential study event')
                events.append(r['details']);peak=max(peak,len(events))
            elif kind=='TERMINAL':
                if r['id']!=active:raise ValueError('nonsequential study terminal')
                if r['status']=='COMPLETED':
                    summaries[active]=reference.audit_episode(by_id[active],events,r['details'],meta)
                    fingerprints[active]=fingerprint(events)
                active=None;events=[]
        log=reader.summary();peak_line=reader.peak_line_bytes
    rows=[{'id':a['id'],'state':log['assignments'][a['id']],'summary':summaries.get(a['id'])} for a in assignments]
    triples=[]
    for i in range(3):
        for case in reference.CASES:
            ids=[f'v{i}:{case}:{arm}' for arm in reference.ARMS]
            if any(k not in fingerprints for k in ids):triples.append({'initial_index':i,'case':case,'status':'UNEVALUABLE_INCOMPLETE'});continue
            first,second,third=(fingerprints[k] for k in ids)
            if first!=second or first!=third:raise ValueError('matched reset/runtime/noise fingerprint mismatch')
            triples.append({'initial_index':i,'case':case,'status':'MATCHED_RESET_RUNTIME_NOISE_ONLY'})
    return {'study':reference.STUDY,'ledger_state':log['state'],'counts':log['counts'],'metadata':meta,'assignments':rows,'matched_triples':triples,
       'reader':'STREAMING_ONE_EPISODE_V1','peak_buffered_episode_events':peak,'peak_input_line_bytes':peak_line,
       'gate_b':'GATE_B_NOT_AUTHORIZED','limitations':['Must exhaust the ledger; no prefix acceptance.',
        'Same existing episode reconstruction; no independent runtime authentication.',
        'Canonical SHA-256 fingerprints replace retaining all cross-arm raw events.',
        'Sequential study adapter; generic ledger stream itself permits valid interleaving.']}


def normalized(result):
    return {k:result[k] for k in ('study','ledger_state','counts','metadata','assignments','matched_triples')}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('ledger',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    result=audit(a.ledger)
    with a.output.open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'state':result['ledger_state'],'counts':result['counts'],'peak_buffered_episode_events':result['peak_buffered_episode_events']}))
if __name__=='__main__':main()
