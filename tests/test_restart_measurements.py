from fractions import Fraction as Q
import json
import pytest
from aegis.development import restart_process_experiment as actors
from scripts.research.restart_failure_study import analyze_case


def fixture(tmp_path):
    config=dict(scenario='nominal',steps=1,initial_position='.31998',initial_velocity='.0099',sources={})
    (tmp_path/'config.json').write_text(json.dumps(config))
    logs={n:actors.Records(tmp_path/n,dict(role=n)) for n in ('plant','watchdog','ctrl-0','orchestrator')}
    p=Q('.31998');v=Q('.0099');a=Q('-.99');pn=p+actors.DT*v+actors.DT**2*a/2;vn=v+actors.DT*a
    logs['plant'].append('STEP_INTENT',tick=0,position=str(p),velocity=str(v),force='-1',target='-1',queue=[],active_force='-1',backup_force='0',power=True,backup_engaged=False,permission_valid=False,generation=0)
    logs['plant'].append('STEP_RESULT',tick=0,position=str(pn),velocity=str(vn),continuous_position=actors.extrema(p,v,a),wall_lateness_ns=0)
    return logs


def test_between_sample_counterexample_is_retained_with_six_separate_outcomes(tmp_path):
    fixture(tmp_path);r=analyze_case(tmp_path)
    assert not r['trajectory_containment']['continuous_ideal_position_contained']
    assert r['trajectory_containment']['violation_ticks']==[0]
    assert r['recovery_latency']['handoff'] is None
    assert not r['execution']['distinct_actor_pids']  # synthetic fixture is not process evidence
    assert not any(k in r for k in ('pass','passed','success','aggregate_pass_fail'))
    assert all(k in r for k in ('unsupported_claims','uncertain_effects','duplicate_effects','nominal_control_availability'))


def test_altered_physical_result_cannot_be_reclassified_by_only_rehashing_file(tmp_path):
    logs=fixture(tmp_path)
    p=tmp_path/'plant'/'00000002.json';r=json.loads(p.read_bytes());r['payload']['position']='0'
    body={k:r[k] for k in ('seq','previous','payload')};r['sha256']=actors.sha(body);p.write_bytes(actors.canonical(r)+b'\n')
    with pytest.raises(ValueError,match='physical'):analyze_case(tmp_path)
