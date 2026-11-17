import hashlib,json
from pathlib import Path
import pytest
from scripts.research import chunk_development_evidence as chunks

def sha(b):return hashlib.sha256(b).hexdigest()
def setup(root,data=b'abcdefghijk'):
    source=root/'original.zip';source.write_bytes(data);parts=root/'parts';chunks.split(source,parts,expected_sha256=sha(data),part_bytes=4);return source,parts

@pytest.mark.parametrize('data',[b'',b'x',b'abcd',b'abcde',bytes(range(256))])
def test_exact_roundtrip_and_original_preservation(tmp_path,data):
    source,parts=setup(tmp_path,data);result=chunks.assemble(parts,tmp_path/'restored.zip',expected_sha256=sha(data))
    assert (tmp_path/'restored.zip').read_bytes()==source.read_bytes()==data
    assert result['sha256']==sha(data) and not result['independent_attestation']
    assert not list(tmp_path.glob('.pending-evidence-*'))

def test_bad_source_pin_retains_failed_output_and_no_final_manifest(tmp_path):
    source=tmp_path/'source';source.write_bytes(b'abc')
    with pytest.raises(ValueError,match='hash'):chunks.split(source,tmp_path/'parts',expected_sha256='0'*64,part_bytes=2)
    assert (tmp_path/'parts/ERROR.json').exists() and not (tmp_path/'parts/chunks.json').exists()
    assert source.read_bytes()==b'abc'

def test_exclusive_outputs_do_not_overwrite_prior_evidence(tmp_path):
    source,parts=setup(tmp_path);original={p.name:p.read_bytes() for p in parts.iterdir()}
    with pytest.raises(FileExistsError):chunks.split(source,parts,expected_sha256=sha(source.read_bytes()))
    output=tmp_path/'restored';output.write_bytes(b'prior')
    with pytest.raises(FileExistsError):chunks.assemble(parts,output,expected_sha256=sha(source.read_bytes()))
    assert output.read_bytes()==b'prior' and original=={p.name:p.read_bytes() for p in parts.iterdir()}

@pytest.mark.parametrize('mutation',['tamper','truncate','rehashed_tamper'])
def test_corruption_cannot_publish_even_when_a_part_manifest_is_rehashed(tmp_path,mutation):
    source,parts=setup(tmp_path);p=parts/'part-000001.bin';p.write_bytes(b'Xbcd' if mutation!='truncate' else b'abc')
    if mutation=='rehashed_tamper':
        path=parts/'chunks.json';m=json.loads(path.read_bytes());m['parts'][0]['sha256']=sha(p.read_bytes());path.write_bytes(chunks.encode(m))
    with pytest.raises(ValueError):chunks.assemble(parts,tmp_path/'out',expected_sha256=sha(source.read_bytes()))
    assert not (tmp_path/'out').exists() and list(tmp_path.glob('.pending-evidence-*'))

@pytest.mark.parametrize('mutation',['path','scope','extra','duplicate_field','external_pin'])
def test_manifest_and_external_pin_are_strict(tmp_path,mutation):
    source,parts=setup(tmp_path);path=parts/'chunks.json';m=json.loads(path.read_bytes());expected=sha(source.read_bytes())
    if mutation=='path':m['parts'][0]['name']='../original.zip'
    if mutation=='scope':m['operational_authorization']=True
    if mutation=='extra':(parts/'unlisted').write_bytes(b'bad')
    if mutation=='external_pin':expected='f'*64
    path.write_bytes(chunks.encode(m))
    if mutation=='duplicate_field':path.write_text('{"schema":"one","schema":"two"}')
    with pytest.raises(ValueError):chunks.assemble(parts,tmp_path/'out',expected_sha256=expected)
    assert not (tmp_path/'out').exists()

def test_symlink_source_and_part_are_rejected(tmp_path):
    source,parts=setup(tmp_path);link=tmp_path/'source-link';link.symlink_to(source)
    with pytest.raises(ValueError,match='symlink'):chunks.split(link,tmp_path/'other',expected_sha256=sha(source.read_bytes()))
    part=parts/'part-000001.bin';part.unlink();part.symlink_to(source)
    with pytest.raises(ValueError,match='symlink'):chunks.assemble(parts,tmp_path/'out',expected_sha256=sha(source.read_bytes()))

@pytest.mark.parametrize('size',[0,-1,chunks.MAX_PART+1,True])
def test_resource_limit_is_not_relaxed(tmp_path,size):
    source=tmp_path/'source';source.write_bytes(b'abc')
    with pytest.raises(ValueError,match='limit'):chunks.split(source,tmp_path/'parts',expected_sha256=sha(b'abc'),part_bytes=size)
    assert not (tmp_path/'parts').exists()

def test_failed_atomic_publication_preserves_pending_bytes(tmp_path,monkeypatch):
    source,parts=setup(tmp_path)
    def fail(*a,**kw):raise OSError('publication unavailable')
    monkeypatch.setattr(chunks.os,'link',fail)
    with pytest.raises(OSError):chunks.assemble(parts,tmp_path/'out',expected_sha256=sha(source.read_bytes()))
    assert not (tmp_path/'out').exists()
    assert list(tmp_path.glob('.pending-evidence-*'))[0].read_bytes()==source.read_bytes()
