"""Synthetic repositories only; never alter the actual research Git index."""
import hashlib
import json
from pathlib import Path
import subprocess
import pytest
from scripts.research import package_temporal_feedback as package


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(root,name,value):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(value if isinstance(value,bytes) else value.encode());return p


def git(root,*args):
    return subprocess.run(['git','--no-optional-locks','-c','core.fsmonitor=false','-c','commit.gpgsign=false',
        '-c','user.name=Synthetic Fixture','-c','user.email=fixture@example.invalid','-C',str(root),*args],
        capture_output=True,text=True,check=True).stdout


@pytest.fixture
def repo(tmp_path):
    root=tmp_path/'repo';root.mkdir();git(root,'init','-q')
    write(root,'src/tracked.py','original = True\n');git(root,'add','src/tracked.py');git(root,'commit','-q','-m','Synthetic packaging fixture')
    source=write(root,'src/main.py','value = 1\n')
    data=write(root,'results/research_development/dev/data.json','{"fixture": true}\n')
    write(root,'docs/research/report.md','# Unit report\n\n## Evidence\n\n[Data](../../results/research_development/dev/data.json)\n\n[Other](other.md#details)\n')
    write(root,'docs/research/other.md','# Other report\n\n## Details\n\n| Item | Value |\n|---|---|\n| Fixture | Yes |\n')
    old=write(root,'results/research_development/dev/historical.json','{"old": 1}\n')
    receipt={'source_sha256':{'src/main.py':digest(source)},'artifacts':{
        'results/research_development/dev/data.json':{'sha256':digest(data),'size_bytes':data.stat().st_size}}}
    write(root,'results/research_development/analysis/receipt.json',package.canonical(receipt))
    write(root,'results/research_development/analysis/prior.json',package.canonical({str(old.relative_to(root)):digest(old)}))
    return root


def export(root,dest):
    return package.export_package(root,dest,receipts=['results/research_development/analysis/receipt.json'],
        prior_maps=['results/research_development/analysis/prior.json'],reports=['docs/research/report.md'])


def test_export_and_detached_verification_keep_source_and_git_unchanged(repo,tmp_path):
    before=git(repo,'status','--porcelain=v1');out=tmp_path/'out'
    result=export(repo,out);assert result==package.verify_package(out)
    assert result['files_verified']==6 and result['reports_verified']==2 and result['links_verified']==2
    assert result['historical_original_hashes_recorded']==1 and not result['independent_attestation']
    assert result['gate_b']=='GATE_B_NOT_AUTHORIZED'
    assert git(repo,'status','--porcelain=v1')==before
    assert (out/'files/src/main.py').read_bytes()==(repo/'src/main.py').read_bytes()
    assert not (out/'files/results/research_development/dev/historical.json').exists()


@pytest.mark.parametrize('name',['src/main.py','results/research_development/dev/data.json','results/research_development/dev/historical.json'])
def test_any_recorded_source_artifact_or_prior_hash_change_refuses_before_output(repo,tmp_path,name):
    (repo/name).write_bytes(b'changed\n');out=tmp_path/'out'
    with pytest.raises(package.PackageError,match='SHA-256 mismatch'):export(repo,out)
    assert not out.exists()


def test_recorded_size_checked_independently_of_digest(repo,tmp_path):
    path=repo/'results/research_development/analysis/receipt.json';r=json.loads(path.read_text())
    r['artifacts']['results/research_development/dev/data.json']['size_bytes']+=1;path.write_bytes(package.canonical(r))
    with pytest.raises(package.PackageError,match='size mismatch'):export(repo,tmp_path/'out')


def test_conflicting_historical_hashes_cannot_be_silently_reconciled(repo,tmp_path):
    write(repo,'results/research_development/analysis/prior.json',package.canonical({'src/main.py':'0'*64}))
    with pytest.raises(package.PackageError,match='conflicting recorded hashes'):export(repo,tmp_path/'out')


@pytest.mark.parametrize('kind',['directory','file','symlink'])
def test_existing_destination_is_never_reused_or_overwritten(repo,tmp_path,kind):
    out=tmp_path/'out'
    if kind=='directory':out.mkdir();(out/'sentinel').write_text('preserve')
    elif kind=='file':out.write_text('preserve')
    else:out.symlink_to(tmp_path/'missing')
    with pytest.raises(FileExistsError):export(repo,out)
    if kind=='directory':assert (out/'sentinel').read_text()=='preserve'
    elif kind=='file':assert out.read_text()=='preserve'
    else:assert out.is_symlink()


@pytest.mark.parametrize('kind',['dirty','staged'])
def test_tracked_or_staged_changes_preserved_and_export_refused(repo,tmp_path,kind):
    write(repo,'src/tracked.py','user_change = True\n')
    if kind=='staged':git(repo,'add','src/tracked.py')
    before=git(repo,'status','--porcelain=v1')
    with pytest.raises(package.PackageError):export(repo,tmp_path/'out')
    assert git(repo,'status','--porcelain=v1')==before
    assert (repo/'src/tracked.py').read_text()=='user_change = True\n'


def test_staged_change_with_clean_worktree_still_refused(repo,tmp_path):
    write(repo,'src/main.py','not_committed = True\n');git(repo,'add','src/main.py')
    with pytest.raises(package.PackageError,match='staged changes'):export(repo,tmp_path/'out')
    assert git(repo,'diff','--cached','--name-only').strip()=='src/main.py'


@pytest.mark.parametrize('name',['/etc/passwd','../escape','src/../escape','src/.secret','results/holdout/seeds.json','results/research_development/dev/reserved_seed.json'])
def test_protected_or_traversing_inputs_rejected_before_read(name):
    with pytest.raises(package.PackageError):package.relative(name)


def test_symlinked_source_is_not_followed(repo,tmp_path):
    src=repo/'src/main.py';src.unlink();src.symlink_to(repo/'src/tracked.py')
    with pytest.raises(package.PackageError,match='symlinked input'):export(repo,tmp_path/'out')


@pytest.mark.parametrize('content,reason',[
    ('# Report\n\n[Broken](missing.md)\n','missing regular'),
    ('# Report\n\n[Bad](other.md#absent)\n','broken report fragment'),
    ('# Report\n\n[Web](https://example.invalid)\n','external/URI'),
    ('# Report\n\n[Bad](../../../../outside.md)\n','traversing'),
    ('# Report\n\n[Bad][missing]\n','undefined reference'),
    ('# Report\n\n[Bad](file(name).md)\n','unsupported/unclosed'),
    ('# Report\n\n<a href="missing.md">Hidden</a>\n','HTML/unsupported'),
    ('# Report\n\n```text\nunclosed\n','unclosed Markdown fence'),
    ('# Report\n\n### Skipped\n','skipped Markdown heading'),
    ('# Report\n\n# Another\n','exactly one'),
    ('# Report\n\nText  \n','whitespace'),
    ('# Report\n\n| A | B |\n|---|---|\n| One |\n','column mismatch'),
    ('# Report\n\n| A | B |\n| One | Two |\n','table separator'),
    ('# Report\n\nNo final newline','newline/encoding'),
])
def test_report_links_and_structure_fail_closed(repo,tmp_path,content,reason):
    write(repo,'docs/research/report.md',content)
    with pytest.raises(package.PackageError,match=reason):export(repo,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_inline_code_fences_reference_links_and_encoded_paths(repo,tmp_path):
    write(repo,'docs/research/a report.md','# A report\n\n## Details\n\nContent.\n')
    write(repo,'docs/research/report.md','# Report\n\n`[fake](missing.md)`\n\n```text\n[not a link](missing.md)\n```\n\n[Good][ref]\n\n[ref]: <a%20report.md#details>\n')
    result=export(repo,tmp_path/'out')
    assert result['reports_verified']==2


def test_reference_report_cycles_and_duplicate_heading_anchors_terminate(repo,tmp_path):
    write(repo,'docs/research/report.md','# Report\n\n## Details\n\nOne.\n\n## Details\n\n[Self](#details-1)\n\n[Other](other.md)\n')
    write(repo,'docs/research/other.md','# Other\n\n[Back](report.md#details)\n')
    assert export(repo,tmp_path/'out')['reports_verified']==2


def test_interrupted_copy_keeps_started_evidence_without_completion_marker(repo,tmp_path,monkeypatch):
    original=package._copy_file;calls=[]
    def fail(src,dest,info):
        original(src,dest,info);calls.append(str(dest));raise OSError('intentional post-copy failure')
    monkeypatch.setattr(package,'_copy_file',fail);out=tmp_path/'partial'
    with pytest.raises(OSError):export(repo,out)
    assert calls and (out/'STARTED.json').exists() and not (out/'COMPLETE.json').exists()
    with pytest.raises(package.PackageError,match='completion'):package.verify_package(out)
    with pytest.raises(FileExistsError):export(repo,out)


def test_input_change_during_export_detected_after_copy(repo,tmp_path,monkeypatch):
    original=package._copy_file;changed=False
    def mutation(src,dest,info):
        nonlocal changed
        original(src,dest,info)
        if src==repo/'src/main.py':src.write_text('changed during export\n');changed=True
    monkeypatch.setattr(package,'_copy_file',mutation);out=tmp_path/'partial'
    with pytest.raises(package.PackageError,match='original changed'):export(repo,out)
    assert changed and not (out/'COMPLETE.json').exists()


@pytest.mark.parametrize('kind',['data','manifest','checksums','missing','extra','symlink','files_root_symlink'])
def test_detached_verifier_rejects_tampering_or_unlisted_paths(repo,tmp_path,kind):
    out=tmp_path/'out';export(repo,out)
    if kind=='data':(out/'files/src/main.py').write_text('tampered\n')
    if kind=='manifest':(out/'manifest.json').write_text('{}\n')
    if kind=='checksums':(out/'SHA256SUMS').write_text('bad\n')
    if kind=='missing':(out/'files/src/main.py').unlink()
    if kind=='extra':(out/'unlisted').write_text('unexpected\n')
    if kind=='symlink':(out/'files/src/main.py').unlink();(out/'files/src/main.py').symlink_to(repo/'src/main.py')
    if kind=='files_root_symlink':
        (out/'files').rename(out/'old-files');(out/'files').symlink_to(repo,target_is_directory=True)
    with pytest.raises(package.PackageError):package.verify_package(out)


def test_duplicate_json_keys_rejected(repo,tmp_path):
    write(repo,'results/research_development/analysis/prior.json','{"src/main.py":"'+digest(repo/'src/main.py')+'","src/main.py":"'+'0'*64+'"}\n')
    with pytest.raises(package.PackageError,match='duplicate JSON key'):export(repo,tmp_path/'out')


def test_two_fresh_exports_have_identical_manifest_and_copy_bytes(repo,tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';export(repo,a);export(repo,b)
    for path in a.rglob('*'):
        if path.is_file():assert path.read_bytes()==(b/path.relative_to(a)).read_bytes()


def test_receipt_change_during_parsing_is_not_packaged_as_the_same_record(repo,tmp_path,monkeypatch):
    load=package.load_json
    def changing(path):
        value=load(path)
        if path.name=='receipt.json':path.write_text(path.read_text()+' ')
        return value
    monkeypatch.setattr(package,'load_json',changing)
    with pytest.raises(package.PackageError,match='record changed while parsing'):export(repo,tmp_path/'out')
    assert not (tmp_path/'out').exists()
