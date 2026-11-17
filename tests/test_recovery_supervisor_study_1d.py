from copy import deepcopy
import gzip,json
import pytest
from scripts.research import recovery_supervisor_study_1d as study
from aegis.env.mujoco_power_brake import PowerBrakeEnvironment
from scripts.research.development_ledger import DevelopmentLedger,LedgerWriteError


@pytest.mark.parametrize('a',study.plan(),ids=lambda a:a['id'])
def test_native_short_mechanisms_and_audit_without_advancing_physics(a,monkeypatch,tmp_path):
    a=deepcopy(a);a['steps']=50
    with (tmp_path/'native_events.jsonl').open('x') as stream:
        saved=study.native_case(a,emit=lambda e:stream.write(json.dumps(e)+'\n'))
    (tmp_path/'original_result.json').write_text(json.dumps(saved))
    s=study.summary(a,saved)
    assert s['native_steps']==50 and s['operational_authorization'] is False
    monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',lambda self:(_ for _ in ()).throw(AssertionError('audit advanced native physics')))
    assert study.native_case(a,saved=saved)==saved
    if a['arm']=='SUPERVISED_PROPOSED_BACKUP':
        if a['case'] in ('backup_missing_hidden','handoff_late_hidden'):
            assert s['first_model_contradiction_tick'] is not None
        if a['case']=='unestablished_backup':assert s['conditional_plan_count']==0 and s['unresolved_plan_count']>0
        if a['case']=='outside_backup_region':assert s['unresolved_plan_count']>0


@pytest.mark.parametrize('field',['physical','decision','measurement','missing_frame','geometry'])
def test_corrupted_native_evidence_not_accepted(field,monkeypatch,tmp_path):
    a=deepcopy(study.plan()[3]);a['steps']=8;saved=study.native_case(a)
    (tmp_path/'original_result.json').write_text(json.dumps(saved))
    if field=='physical':saved['frames'][1]['physical']['velocity'][0]+=1
    if field=='decision':saved['frames'][0]['intent']['supervision']['development_action']='CONTINUE_WITH_BACKUP_RESERVE'
    if field=='measurement':saved['frames'][0]['intent']['state_observation']['velocity']=['0','0']
    if field=='missing_frame':saved['frames'].pop()
    if field=='geometry':saved['frames'][1]['physical']['geometric_or_contact_violation']=not saved['frames'][1]['physical']['geometric_or_contact_violation']
    monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',lambda self:(_ for _ in ()).throw(AssertionError('audit advanced physics')))
    with pytest.raises(ValueError):study.native_case(a,saved=saved)


def test_partial_error_keeps_unstarted_assignments(tmp_path,monkeypatch):
    monkeypatch.setattr(study,'native_case',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('intentional supervisor simulation error')))
    path=tmp_path/'failed'
    with pytest.raises(RuntimeError):study.run(path)
    r=study.audit(path)
    assert r['counts']==dict(ASSIGNED=15,STARTED=0,COMPLETED=0,ERROR=1)
    with pytest.raises(FileExistsError):study.run(path)


def test_post_physics_sink_failure_preserves_unknown_motion_not_zero_motion(tmp_path,monkeypatch):
    event=DevelopmentLedger.event;step=PowerBrakeEnvironment.advance_prepared;calls=[]
    def fail(self,name,*,details):
        if details['phase']=='NATIVE_PHYSICS':raise LedgerWriteError('intentional post-physics sink failure')
        return event(self,name,details=details)
    def advance(self):calls.append(1);return step(self)
    monkeypatch.setattr(DevelopmentLedger,'event',fail);monkeypatch.setattr(PowerBrakeEnvironment,'advance_prepared',advance)
    path=tmp_path/'failed'
    with pytest.raises(LedgerWriteError):study.run(path)
    r=study.audit(path)
    assert calls==[1] and r['counts']==dict(ASSIGNED=15,STARTED=1,COMPLETED=0,ERROR=0)
    assert all(a['summary'] is None for a in r['assignments'])


def test_small_exclusive_study_reconstructs_durable_events(tmp_path,monkeypatch):
    original=study.plan
    def small():
        a=original()[3];a['steps']=8;return [a]
    monkeypatch.setattr(study,'plan',small)
    path=tmp_path/'batch';study.run(path)
    r=study.audit(path);assert r['counts']['COMPLETED']==1 and r['ledger_state']=='FINALIZED'
    with pytest.raises(FileExistsError):study.run(path)


@pytest.mark.parametrize('value',[0.,1e-12,-1e-12,2e-8,-2e-8,1.,-1.])
def test_measurement_wire_bounds_keep_near_zero_and_cap_values_parseable(value):
    from aegis.development.recovery_feedback_state_1d import _bounds
    from fractions import Fraction
    wire=study.bounds(value,cap=1.)
    parsed=_bounds(wire)
    assert all('e' not in v.lower() for v in wire)
    assert parsed.lo <= Fraction(str(value)) <= parsed.hi
    assert parsed.lo>=-1 and parsed.hi<=1
