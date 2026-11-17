"""Prevent recurrence of an authorization-looking header over pending decisions."""
import copy,json,re,subprocess
from pathlib import Path
import pytest
from scripts.research.check_owner_register_consistency import check,FOLDER


def inputs():
 return (FOLDER/'V9_M4_OWNER_DECISION_REGISTER.md').read_text(),json.loads((FOLDER/'V9_M4_OWNER_STATUS_RECONCILIATION_2026-11-16.json').read_text())


def test_current_package_is_consistent_and_cannot_grant_authorization():
 text,record=inputs();r=check(text,record)
 assert r['decisions']==15 and r['approval_verified'] is False and r['production_authorization'] is False
 assert r['status_counts']=={'OWNER DECISION REQUIRED':6,'INDEPENDENT REVIEW REQUIRED':5,'BLOCKED':4}
 # Historical approval claims remain visible as claims; they do not close reviews.
 assert any(d['prior_summary_claim'].startswith('APPROVED') for d in record['decisions'])


@pytest.mark.parametrize('defect',['authorized_header','ready_header','queue_status','detail_status','duplicate_row','missing_row','conflict_marker'])
def test_conflicting_or_missing_document_statuses_are_rejected(defect):
 text,record=inputs()
 if defect=='authorized_header':text=text.replace('**Current governance:** `GATE_B_NOT_AUTHORIZED`.','**Current governance:** `GATE_B_CONFIRMED`.')
 if defect=='ready_header':text=text.replace('**Release readiness:** `BLOCKED`','**Release readiness:** `READY`')
 if defect=='queue_status':text=text.replace('| SCI-02 | P0 | H2 identity and H1 gate | OWNER DECISION REQUIRED |','| SCI-02 | P0 | H2 identity and H1 gate | APPROVED |')
 if defect=='detail_status':text=text.replace('**Status: BLOCKED.**','**Status: APPROVED.**',1)
 if defect in ('duplicate_row','missing_row'):
  row=next(line for line in text.splitlines() if line.startswith('| SCI-02 |'))
  text=text.replace(row,row+'\n'+row if defect=='duplicate_row' else '')
 if defect=='conflict_marker':text+='\n<<<<<<< unresolved\n'
 with pytest.raises(ValueError):check(text,record)


@pytest.mark.parametrize('defect',['approved_flag','production_flag','rules_flag','decision_id','duplicate_id','approval_identity','decision_value','closure_claim','reviewer_missing','count','status','provenance'])
def test_structured_record_cannot_silently_promote_approval_or_drop_reviews(defect):
 text,record=inputs();d=record['decisions'][0]
 if defect=='approved_flag':record['owner_decisions_approved_by_this_work']=True
 if defect=='production_flag':record['production_authorization_issued']=True
 if defect=='rules_flag':record['registered_rules_modified']=True
 if defect=='decision_id':d['id']='SCI-99'
 if defect=='duplicate_id':record['decisions'][1]['id']=d['id']
 if defect=='approval_identity':d['approved_by']='unverified name'
 if defect=='decision_value':d['owner_decision']='Option A'
 if defect=='closure_claim':d['closure_evidence_verified']=True
 if defect=='reviewer_missing':d['required_reviewer']=''
 if defect=='count':record['status_counts']={}
 if defect=='status':d['review_status']='APPROVED'
 if defect=='provenance':d['approval_provenance_status']='VERIFIED'
 with pytest.raises(ValueError):check(text,record)


def test_original_detailed_scientific_and_security_questions_are_preserved():
 text,record=inputs();source=record['source']
 original=subprocess.check_output(['git','show',source['detailed_workstream_baseline_commit']+':'+source['register_path']],cwd=FOLDER,text=True)
 start='## Workstream 1 — Release candidate and Staging Manifest';end='## Required owner summary'
 assert text[text.index(start):text.index(end)]==original[original.index(start):original.index(end)]
