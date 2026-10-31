import sys
import pytest
from scripts.research import study_recovery_monitor_ledger as study
from scripts.research.compare_recovery_budgets import compare


def run(tmp_path, monkeypatch, budget, seed=2255000):
    path = tmp_path / f'{budget}_{seed}.jsonl'
    monkeypatch.setattr(sys,'argv',['study','--development-seeds',str(seed),'--case','nominal',
        '--max-steps','2','--post-stop-steps','1','--incremental-events','--recovery-steps',str(budget),'--output',str(path)])
    study.main()
    return path


def test_matched_real_short_simulation_compares_only_budget(tmp_path,monkeypatch):
    a = run(tmp_path,monkeypatch,100)
    b = run(tmp_path,monkeypatch,300)
    result = compare(a,b)
    assert result['budgets'] == [100,300]
    assert len(result['assignments']) == 4
    assert all(x['execution_status']=='COMPLETED' for row in result['assignments'] for x in row['observations'])
    with pytest.raises(ValueError):
        compare(a,a)


def test_unmatched_worlds_rejected(tmp_path,monkeypatch):
    a=run(tmp_path,monkeypatch,100)
    b=run(tmp_path,monkeypatch,300,seed=2255001)
    with pytest.raises(ValueError):
        compare(a,b)
