"""Read-only documentation guard for the 2026-11-16 owner reconciliation.

NOT a security gate, approval verifier, scientific evaluator or authorization
service. Checks agreement of explicitly unapproved review records only. A future
approved decision needs a separate reviewed record/process, not a passing check.
"""
import json,re
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[2]
FOLDER=ROOT/'docs/reports/v9_m4_release_remediation'
IDS={f'SCI-{i:02}' for i in range(1,8)}|{f'SEC-{i:02}' for i in range(1,6)}|{'PROV-01','REL-01','REL-02'}
STATUSES={'OPEN','OWNER DECISION REQUIRED','INDEPENDENT REVIEW REQUIRED','BLOCKED'}


def check(text,record):
    def require(condition,reason):
        if not condition:raise ValueError(reason)
    require('<<<<<<<' not in text and '>>>>>>>' not in text,'unresolved conflict markers')
    lines=text.splitlines()
    governance=[line for line in lines if line.startswith('**Current governance:**')]
    release=[line for line in lines if line.startswith('**Release readiness:**')]
    require(len(governance)==1 and governance[0].startswith('**Current governance:** `GATE_B_NOT_AUTHORIZED`.'),'current governance must remain unauthorized')
    require(len(release)==1 and release[0].startswith('**Release readiness:** `BLOCKED`'),'release must remain blocked in this reconciliation')
    require(record.get('classification')=='DOCUMENTATION_STATUS_RECONCILIATION_NOT_APPROVAL','wrong record classification')
    require(record.get('gate_b')=='GATE_B_NOT_AUTHORIZED' and record.get('release_readiness')=='BLOCKED','record governance mismatch')
    for flag in ('owner_decisions_approved_by_this_work','production_authorization_issued','registered_rules_modified'):
        require(record.get(flag) is False,'reconciliation cannot approve decisions, authorize production or change rules')
    items=record.get('decisions');require(isinstance(items,list),'decision list required')
    require(all(isinstance(x,dict) and isinstance(x.get('id'),str) for x in items),'invalid decision record')
    require(len(items)==len(IDS) and {x['id'] for x in items}==IDS,'decision IDs missing/duplicated/unexpected')
    records={x['id']:x for x in items}
    for item in items:
        require(item.get('review_status') in STATUSES,'invalid review status')
        require(item.get('approval_provenance_status')=='NOT_AUTHENTICATED_IN_THIS_REVIEW','approval provenance must remain explicit')
        require(item.get('engineering_completion')=='NOT_REAUDITED','engineering completion was not re-audited')
        for field in ('owner_decision','approved_by','approved_at','approval_record_reference','independent_review_reference'):
            require(field in item and item[field] is None,'use a separate approved decision record; this form remains unapproved')
        require(item.get('closure_evidence_verified') is False,'closure not established by document consistency')
        require(bool(item.get('required_reviewer')),'required reviewer missing')
    queue=[];in_queue=False;details=[];active=None
    for line in lines:
        if line=='## Decision queue':in_queue=True;continue
        if in_queue and line.startswith('## '):in_queue=False
        if in_queue and line.startswith('|'):
            cells=[c.strip() for c in line.split('|')[1:-1]]
            if cells and re.fullmatch(r'(SCI|SEC|PROV|REL)-\d\d',cells[0]):
                require(len(cells)==5,'queue column count');queue.append((cells[0],cells[3]))
        if line.startswith('### '):
            m=re.search(r'\b(?:SCI|SEC|PROV|REL)-\d\d\b',line);active=m.group(0) if m else None
        if active and '**Status:' in line:
            m=re.search(r'\*\*Status:\s*(.*?)\*\*',line)
            require(m is not None,'malformed detailed status');details.append((active,m.group(1).rstrip('.')))
    for name,entries in (('queue',queue),('details',details)):
        require(len(entries)==len(IDS) and {k for k,v in entries}==IDS,name+' IDs missing/duplicated/unexpected')
        for k,v in entries:require(v==records[k]['review_status'],name+' status disagrees with record: '+k)
    counts=dict(Counter(item['review_status'] for item in items))
    require(record.get('status_counts')==counts,'status counts disagree')
    return {'check':'CONSISTENT_DOCUMENTATION_ONLY','decisions':len(items),'status_counts':counts,
            'gate_b':'GATE_B_NOT_AUTHORIZED','approval_verified':False,'production_authorization':False,
            'limitation':'Not evidence of approval, implementation correctness, independent review or release readiness.'}


def main():
    text=(FOLDER/'V9_M4_OWNER_DECISION_REGISTER.md').read_text()
    record=json.loads((FOLDER/'V9_M4_OWNER_STATUS_RECONCILIATION_2026-11-16.json').read_text())
    print(json.dumps(check(text,record),indent=2))
if __name__=='__main__':main()
