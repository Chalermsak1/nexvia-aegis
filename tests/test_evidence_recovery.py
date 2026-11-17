from copy import deepcopy
import pytest
from aegis.development import evidence_recovery as adapter
from aegis.development.recovery_evidence import EvidenceJournal,PREMISE_NAMES
from scripts.research import evidence_recovery_study as study


def ready(tmp_path):
    j=EvidenceJournal.create(tmp_path/'journal',policy=study.policy(),boot_id='boot-A',clock_domain='local-A',now=100)
    for row in study.artifacts():j.submit(row,now=100)
    return j


def test_supported_fixture_can_produce_only_a_conditional_simulation_candidate(tmp_path):
    with ready(tmp_path) as j:
        r=adapter.assess(j,study.inputs(),finish_clock=lambda:100)
        assert r['status']=='DEVELOPMENT_EVIDENCE_BACKED_CONDITIONAL_PLAN' and r['development_action']=='CONTINUE'
        assert not r['dispatch'] and not r['operational_authorization'] and not r['hardware_validation'] and not r['independent_attestation']


@pytest.mark.parametrize('key,value',[('active_force_cap','2'),('handoff_delay_seconds',['0','.3']),('primary_healthy',False),('dynamics_id','foreign'),('monitor_seconds','.07')])
def test_evidence_cannot_be_transferred_to_different_physical_inputs(tmp_path,key,value):
    with ready(tmp_path) as j:
        a=study.inputs();a[key]=value;r=adapter.assess(j,a,finish_clock=lambda:100)
        assert r['development_action'] is None and not r['conditional_continuous_containment']


@pytest.mark.parametrize('key,value',[('position',['0','.01']),('velocity',['.3','.31']),('remote_epoch','sensor-B')])
def test_packet_or_clock_epoch_change_invalidates_binding(tmp_path,key,value):
    with ready(tmp_path) as j:
        a=study.inputs();a['packet'][key]=value
        assert adapter.assess(j,a,finish_clock=lambda:100)['development_action'] is None


@pytest.mark.parametrize('finish',[99,101,105,True])
def test_regression_time_advance_or_expiry_during_compute_withholds(tmp_path,finish):
    with ready(tmp_path) as j:
        r=adapter.assess(j,study.inputs(),finish_clock=lambda:finish)
        assert r['development_action'] is None and not r['conditional_continuous_containment']


def test_input_mutation_during_proof_is_detected(tmp_path,monkeypatch):
    a=study.inputs();original=adapter.physical.assess
    def mutate(**kwargs):
        result=original(**kwargs);a['active_force_cap']='2';return result
    monkeypatch.setattr(adapter.physical,'assess',mutate)
    with ready(tmp_path) as j:
        r=adapter.assess(j,a,finish_clock=lambda:100)
        assert r['reason']=='INPUT_CHANGED_DURING_ASSESSMENT' and r['development_action'] is None


def test_all_assertions_remain_insufficient_without_observations(tmp_path):
    with EvidenceJournal.create(tmp_path/'journal',policy=study.policy(),boot_id='boot-A',clock_domain='local-A',now=100) as j:
        for row in study.artifacts():j.submit(dict(row,kind='ASSERTED',observations=None),now=100)
        r=adapter.assess(j,study.inputs(),finish_clock=lambda:100)
        assert r['model_plan'] is None and r['development_action'] is None


def test_false_physical_boolean_cannot_be_injected_outside_evidence_contract(tmp_path):
    with ready(tmp_path) as j:
        a=study.inputs();a['premises']={k:True for k in PREMISE_NAMES}
        assert adapter.assess(j,a,finish_clock=lambda:100)['development_action'] is None


def test_clock_driver_failure_returns_withheld_result(tmp_path):
    def failed_clock():raise RuntimeError('synthetic clock driver disconnected')
    with ready(tmp_path) as j:
        r=adapter.assess(j,study.inputs(),finish_clock=failed_clock)
        assert r['development_action'] is None and r['reason']=='INVALID_OR_UNCOMMITTED_EVIDENCE_INPUT'
        assert j.state['fault']=='ASSESSMENT_CLOCK_FAILURE'
        assert adapter.assess(j,study.inputs(),finish_clock=lambda:100)['development_action'] is None


def test_supported_evidence_cannot_override_failed_physical_feasibility(tmp_path):
    a=study.inputs();a['packet']['velocity']=['1.5','1.5'];rows=study.artifacts(a);rows[0]['observations'][1]='1.5'
    with EvidenceJournal.create(tmp_path/'journal',policy=study.policy(),boot_id='boot-A',clock_domain='local-A',now=100) as j:
        for row in rows:j.submit(row,now=100)
        r=adapter.assess(j,a,finish_clock=lambda:100)
        assert r['evidence']['status']=='SIMULATION_PREDICATES_SUPPORTED'
        assert r['status']=='MODEL_UNRESOLVED' and r['development_action'] is None
