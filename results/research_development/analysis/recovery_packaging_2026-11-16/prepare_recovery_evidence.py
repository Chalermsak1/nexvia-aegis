from pathlib import Path
import hashlib,json,shutil,zipfile,os
root=Path('/Users/chalermsak/Documents/ChatGPT/New project/nexvia-aegis')
pkg=Path('/private/tmp/nexvia-recovery-package-20261116');pkg.mkdir()
def put(rel,source):
 p=pkg/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,p)
put('results/research_development/analysis/recovery_streaming_tests_2026-11-16.xml','/private/tmp/nexvia-recovery-regression-v1-20261116.xml')
for f in Path('/private/tmp/nexvia-recovery-study-v1-20261116').iterdir():put('results/research_development/dev/recovery_contract_v1_2026-11-16/'+f.name,f)
for f in Path('/private/tmp/nexvia-reader-benchmark-20261116').iterdir():put('results/research_development/analysis/reference_reader_benchmark_2026-11-16/'+f.name,f)
# Retain all test fixture bytes, including intentional interruptions/corruption, by content.
objects={};logical={}
for dirname in ('nexvia-recovery-unit-v1-20261116','nexvia-recovery-native-v1-20261116','nexvia-recovery-regression-v1-20261116'):
 base=Path('/private/tmp')/dirname
 for p in sorted(base.rglob('*')):
  if p.is_symlink():continue
  if p.is_file():
   data=p.read_bytes();h=hashlib.sha256(data).hexdigest();objects.setdefault(h,data);logical[dirname+'/'+str(p.relative_to(base))]={'sha256':h,'size_bytes':len(data),'member':'objects/'+h}
 xml=base.with_suffix('.xml');data=xml.read_bytes();h=hashlib.sha256(data).hexdigest();objects.setdefault(h,data);logical[xml.name]={'sha256':h,'size_bytes':len(data),'member':'objects/'+h}
archive=pkg/'results/research_development/dev/recovery_streaming_test_fixtures_2026-11-16.zip';archive.parent.mkdir(parents=True,exist_ok=True)
restore='''from pathlib import Path
import hashlib,json,sys,zipfile
out=Path(sys.argv[2]);out.mkdir(exist_ok=False)
with zipfile.ZipFile(sys.argv[1]) as z:
 for logical,item in json.loads(z.read('manifest.json')).items():
  p=Path(logical)
  if p.is_absolute() or '..' in p.parts:raise ValueError('unsafe logical path')
  b=z.read(item['member'])
  if len(b)!=item['size_bytes'] or hashlib.sha256(b).hexdigest()!=item['sha256']:raise ValueError('integrity mismatch')
  target=out/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
'''
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
 z.writestr('manifest.json',json.dumps(logical,indent=2));z.writestr('restore.py',restore)
 z.writestr('README.txt','All three overlapping test invocations and fixture bytes. Intentional corrupted/incomplete/error ledgers are NOT successful research. Extract restore.py, then run python restore.py ARCHIVE NEW_DIRECTORY.\n')
 for h,data in objects.items():z.writestr('objects/'+h,data)
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for h in objects:assert hashlib.sha256(z.read('objects/'+h)).hexdigest()==h
stats={'logical_files':len(logical),'unique_objects':len(objects),'logical_bytes':sum(v['size_bytes'] for v in logical.values()),'unique_bytes':sum(map(len,objects.values())),'archive_bytes':archive.stat().st_size}
(pkg/'fixture_archive_stats.json').write_text(json.dumps(stats,indent=2)+'\n')
print(json.dumps(stats))
# Snapshot explicitly declared source/dependency files, plus new reader/tests/benchmark.
import sys
sys.path[:0]=[str(root),str(root/'src')]
from scripts.research import recovery_contract_study as study
snapshot=Path('/private/tmp/nexvia-recovery-source-snapshot-20261116');snapshot.mkdir()
extra=('src/aegis/__init__.py','src/aegis/env/__init__.py','scripts/research/audit_reference_stream.py','scripts/research/benchmark_reference_readers.py','tests/test_recovery_contract.py','tests/test_recovery_contract_study.py','tests/test_streaming_ledger.py')
for f in dict.fromkeys(study.FILES+extra):
 target=snapshot/f;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/f,target)
summary=Path('/private/tmp/nexvia-recovery-study-v1-20261116/summary.json')
shutil.copyfile(summary,snapshot/'expected_summary.json')
raw=summary.with_name('assignments.jsonl')
(snapshot/'expected_raw_sha256.txt').write_text(hashlib.file_digest(raw.open('rb'),'sha256').hexdigest()+'\n')
print('Prepared source snapshot',len(study.FILES+extra),'paths')
