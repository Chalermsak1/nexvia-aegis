import json,shutil
import pytest
from scripts.research import live_recovery_study as study


@pytest.fixture(scope='module')
def completed(tmp_path_factory):
    root=tmp_path_factory.mktemp('live_study')/'campaign'
    study.run(root,ids=['SIMULATION_CONTRACT_CHECKS_nominal']);return root


def test_assignment_and_read_only_reconstruction(completed):
    r=study.audit(completed)
    assert r['ledger_counts']['COMPLETED']==1 and not r['incomplete']
    assert r['aggregate_pass_fail'] is None


def test_measurement_tamper_is_rejected_without_changing_original(completed,tmp_path):
    copied=tmp_path/'tampered';shutil.copytree(completed,copied);path=copied/'SIMULATION_CONTRACT_CHECKS_nominal/measurements.json';r=json.loads(path.read_bytes());r['nominal_control_availability']['new_consumptions']=999;path.write_text(json.dumps(r))
    with pytest.raises(ValueError,match='measurements'):study.audit(copied)
    assert study.audit(completed)['ledger_counts']['COMPLETED']==1
