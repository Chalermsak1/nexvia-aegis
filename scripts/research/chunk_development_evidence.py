"""Bounded, hash-pinned development-evidence transport; never extract or execute.

Unkeyed hashes and caller pins are integrity checks, not source authentication.
The original artifact and previous incomplete outputs are never overwritten.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, stat, tempfile

SCHEMA='nexvia-development-evidence-chunks/1'
MAX_PART=256*1024*1024
MAX_PARTS=10000

def encode(value):return (json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
def pin(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None:raise ValueError('external SHA-256 pin required')
    return value
def write(path,data):
    with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
def sync_directory(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def opened(path):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    if not stat.S_ISREG(os.fstat(fd).st_mode):os.close(fd);raise ValueError('regular file required')
    return os.fdopen(fd,'rb')
def identity(info):return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns)

def split(source,directory,*,expected_sha256,part_bytes=128*1024*1024):
    source=Path(source);directory=Path(directory);expected_sha256=pin(expected_sha256)
    if type(part_bytes) is not int or not 1<=part_bytes<=MAX_PART:raise ValueError('part byte limit')
    if source.is_symlink():raise ValueError('symlink source')
    if directory.exists() or directory.is_symlink():raise FileExistsError(directory)
    with opened(source) as src:
        before=os.fstat(src.fileno())
        if (before.st_size+part_bytes-1)//part_bytes>MAX_PARTS:raise ValueError('part count limit')
        directory.mkdir(exist_ok=False)
        write(directory/'STARTED.json',encode(dict(schema=SCHEMA,expected_sha256=expected_sha256,status='INCOMPLETE_UNTIL_MANIFEST',gate_b='GATE_B_NOT_AUTHORIZED')))
        parts=[];total=0;whole=hashlib.sha256()
        try:
            while total<before.st_size:
                name=f'part-{len(parts)+1:06d}.bin';h=hashlib.sha256();count=0
                with (directory/name).open('xb') as target:
                    while count<part_bytes:
                        b=src.read(min(1024*1024,part_bytes-count))
                        if not b:break
                        target.write(b);h.update(b);whole.update(b);count+=len(b);total+=len(b)
                    target.flush();os.fsync(target.fileno())
                parts.append(dict(name=name,sha256=h.hexdigest(),size_bytes=count))
                if count==0:raise ValueError('source truncated')
            if src.read(1) or identity(before)!=identity(os.fstat(src.fileno())):raise ValueError('source identity changed')
            if whole.hexdigest()!=expected_sha256 or total!=before.st_size:raise ValueError('source hash or size differs')
            result=dict(schema=SCHEMA,classification='DEVELOPMENT_TRANSPORT_NOT_ATTESTATION',original_name=source.name,size_bytes=total,sha256=whole.hexdigest(),parts=parts,gate_b='GATE_B_NOT_AUTHORIZED',operational_authorization=False)
            write(directory/'chunks.json',encode(result));sync_directory(directory)
            return result
        except BaseException as exc:
            write(directory/'ERROR.json',encode(dict(error_type=type(exc).__name__,error=str(exc),status='INCOMPLETE_RETAINED',gate_b='GATE_B_NOT_AUTHORIZED')))
            raise

def unique_pairs(items):
    result={}
    for k,v in items:
        if k in result:raise ValueError('duplicate manifest field')
        result[k]=v
    return result

def assemble(directory,output,*,expected_sha256):
    directory=Path(directory);output=Path(output);expected_sha256=pin(expected_sha256)
    if directory.is_symlink():raise ValueError('symlink directory')
    if output.exists() or output.is_symlink():raise FileExistsError(output)
    manifest_path=directory/'chunks.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size>8*1024*1024:raise ValueError('manifest resource/type limit')
    with opened(manifest_path) as f:m=json.load(f,object_pairs_hook=unique_pairs)
    if type(m) is not dict or set(m)!={'schema','classification','original_name','size_bytes','sha256','parts','gate_b','operational_authorization'}:raise ValueError('manifest fields')
    if m['schema']!=SCHEMA or m['classification']!='DEVELOPMENT_TRANSPORT_NOT_ATTESTATION' or m['gate_b']!='GATE_B_NOT_AUTHORIZED' or m['operational_authorization'] is not False:raise ValueError('scope changed')
    if m['sha256']!=expected_sha256:raise ValueError('manifest differs from external pin')
    if type(m['size_bytes']) is not int or m['size_bytes']<0 or type(m['original_name']) is not str or type(m['parts']) is not list or len(m['parts'])>MAX_PARTS:raise ValueError('manifest bounds')
    total=0;names={'STARTED.json','chunks.json'}
    for i,p in enumerate(m['parts'],1):
        if type(p) is not dict or set(p)!={'name','sha256','size_bytes'} or p['name']!=f'part-{i:06d}.bin':raise ValueError('part order/name')
        pin(p['sha256'])
        if type(p['size_bytes']) is not int or not 1<=p['size_bytes']<=MAX_PART:raise ValueError('part size bound')
        names.add(p['name']);total+=p['size_bytes']
    if total!=m['size_bytes']:raise ValueError('part size sum')
    if {p.name for p in directory.iterdir()}!=names or any(p.is_symlink() or not p.is_file() for p in directory.iterdir()):raise ValueError('unexpected or symlink input')
    fd,pending=tempfile.mkstemp(prefix='.pending-evidence-',dir=output.parent);pending=Path(pending);whole=hashlib.sha256();total=0
    # Keep pending bytes on any error, including a failed final publication.
    with os.fdopen(fd,'wb') as target:
        for p in m['parts']:
            count=0;part=hashlib.sha256()
            with opened(directory/p['name']) as src:
                if os.fstat(src.fileno()).st_size!=p['size_bytes']:raise ValueError('part length differs')
                for b in iter(lambda:src.read(1024*1024),b''):
                    count+=len(b)
                    if count>p['size_bytes']:raise ValueError('part grew while reading')
                    target.write(b);part.update(b);whole.update(b);total+=len(b)
            if count!=p['size_bytes'] or part.hexdigest()!=p['sha256']:raise ValueError('part digest or length differs')
        target.flush();os.fsync(target.fileno())
    if whole.hexdigest()!=expected_sha256 or total!=m['size_bytes']:raise ValueError('assembled digest or size differs')
    os.link(pending,output);sync_directory(output.parent);pending.unlink();sync_directory(output.parent)
    return dict(status='REASSEMBLED_VERIFIED_DEVELOPMENT_BYTES',sha256=whole.hexdigest(),size_bytes=total,parts=len(m['parts']),gate_b='GATE_B_NOT_AUTHORIZED',independent_attestation=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('split');p.add_argument('source',type=Path);p.add_argument('directory',type=Path);p.add_argument('--expected-sha256',required=True);p.add_argument('--part-bytes',type=int,default=128*1024*1024)
    p=sub.add_parser('assemble');p.add_argument('directory',type=Path);p.add_argument('output',type=Path);p.add_argument('--expected-sha256',required=True)
    args=parser.parse_args();kw=vars(args);mode=kw.pop('mode')
    print(json.dumps(split(**kw) if mode=='split' else assemble(**kw),sort_keys=True))
