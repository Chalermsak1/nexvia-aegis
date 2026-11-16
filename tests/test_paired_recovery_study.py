from pathlib import Path
import json
import shutil
import pytest
from scripts.research import paired_recovery_study as study


@pytest.fixture(scope='module')
def completed(tmp_path_factory):
    p=tmp_path_factory.mktemp('paired')/'run';study.run(p);return p


def test_exact_eight_assignments_and_four_pairs(completed):
    r=study.analyze(completed)
    assert len(r['assignments'])==8 and r['declared_pairs']==len(r['pairs'])==4
    assert all(a['batch_status']=='COMPLETED' for a in r['assignments'])
    assert all(p['status']=='COMPARABLE_DEVELOPMENT_EVIDENCE' for p in r['pairs'])


@pytest.mark.parametrize('defect',['omitted_case','wrong_case','missing_child','child_bytes','source_identity'])
def test_missing_or_tampered_evidence_cannot_look_comparable(completed,tmp_path,defect):
    p=tmp_path/'copy';shutil.copytree(completed,p);manifest=json.loads((p/'manifest.json').read_text())
    if defect=='omitted_case':manifest['assignments'].pop()
    elif defect=='wrong_case':manifest['assignments'][0]['synchronized']=True
    elif defect=='source_identity':manifest['source_sha256'][next(iter(manifest['source_sha256']))]='0'*64
    elif defect=='missing_child':(p/manifest['assignments'][0]['child']).unlink()
    else:
        with (p/manifest['assignments'][0]['child']).open('ab') as f:f.write(b'bad\n')
    (p/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):study.analyze(p)


def test_failed_launch_is_preserved_without_retry(tmp_path,monkeypatch):
    p=tmp_path/'run';calls=[]
    def fail(*args,**kwargs):calls.append(1);raise RuntimeError('synthetic launch failure')
    monkeypatch.setattr(study.bridge,'execute',fail)
    with pytest.raises(RuntimeError):study.run(p)
    r=study.analyze(p)
    assert len(calls)==1 and r['ledger_state']=='INCOMPLETE'
    assert r['assignments'][0]['batch_status']=='ERROR'
    assert sum(a['batch_status']=='ASSIGNED' for a in r['assignments'])==7
    assert all(p['status']=='UNEVALUABLE' for p in r['pairs'])


def test_existing_run_directory_cannot_be_reused(tmp_path):
    p=tmp_path/'prior';p.mkdir();(p/'keep').write_text('original')
    with pytest.raises(FileExistsError):study.run(p)
    assert (p/'keep').read_text()=='original'
