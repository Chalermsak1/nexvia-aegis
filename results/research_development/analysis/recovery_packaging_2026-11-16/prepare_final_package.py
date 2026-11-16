from pathlib import Path
import json,hashlib,shutil,zipfile,sys
root=Path('/Users/chalermsak/Documents/ChatGPT/New project/nexvia-aegis');old=Path('/private/tmp/nexvia-recovery-package-20261116');pkg=Path('/private/tmp/nexvia-recovery-final-package-20261116');pkg.mkdir()
def put(rel,source):
 p=pkg/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,p)
for f in (old/'results').rglob('*'):
 if f.is_file() and f.suffix!='.zip':put(str(f.relative_to(old)),f)
put('results/research_development/dev/recovery_contract_source_reproduction_pre_label_fix_2026-11-16.zip',old/'results/research_development/dev/recovery_contract_source_reproduction_2026-11-16.zip')
put('results/research_development/analysis/recovery_streaming_tests_v2_2026-11-16.xml','/private/tmp/nexvia-recovery-regression-v2-20261116.xml')
for f in Path('/private/tmp/nexvia-recovery-study-v2-20261116').iterdir():put('results/research_development/dev/recovery_contract_v2_2026-11-16/'+f.name,f)
# Streaming construction of content-addressed fixture archive; no whole ledger held in RAM.
objects={};logical={}
bases=[Path('/private/tmp')/n for n in ('nexvia-recovery-unit-v1-20261116','nexvia-recovery-native-v1-20261116','nexvia-recovery-regression-v1-20261116','nexvia-recovery-regression-v2-20261116','nexvia-recovery-before-label-fix-20261116')]
for base in bases:
 files=[f for f in sorted(base.rglob('*')) if f.is_file() and not f.is_symlink()]
 if base.with_suffix('.xml').exists():files.append(base.with_suffix('.xml'))
 for p in files:
  with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
  objects.setdefault(h,p);key=base.name+'/'+str(p.relative_to(base)) if p.is_relative_to(base) else p.name
  logical[key]={'sha256':h,'size_bytes':p.stat().st_size,'member':'objects/'+h}
archive=pkg/'results/research_development/dev/recovery_streaming_test_fixtures_2026-11-16.zip'
with zipfile.ZipFile(old/'results/research_development/dev/recovery_streaming_test_fixtures_2026-11-16.zip') as z:restore=z.read('restore.py')
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
 z.writestr('manifest.json',json.dumps(logical,indent=2));z.writestr('restore.py',restore)
 z.writestr('README.txt','All overlapping test invocations, malformed/incomplete/error fixtures, and before-label-fix source revision. These fixtures are not successful research trajectories. Extract restore.py, run python restore.py ARCHIVE NEW_DIRECTORY.\n')
 for h,p in objects.items():z.write(p,'objects/'+h)
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 for h in objects:
  with z.open('objects/'+h) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==h
stats={'logical_files':len(logical),'unique_objects':len(objects),'logical_bytes':sum(v['size_bytes'] for v in logical.values()),'unique_bytes':sum(p.stat().st_size for p in objects.values()),'archive_bytes':archive.stat().st_size}
(pkg/'fixture_archive_stats.json').write_text(json.dumps(stats,indent=2)+'\n');print(json.dumps(stats),flush=True)
sys.path[:0]=[str(root),str(root/'src')]
from scripts.research import recovery_contract_study as study
snapshot=Path('/private/tmp/nexvia-recovery-source-snapshot-v2-20261116');snapshot.mkdir()
extra=('src/aegis/__init__.py','src/aegis/env/__init__.py','scripts/research/audit_reference_stream.py','scripts/research/benchmark_reference_readers.py','tests/test_recovery_contract.py','tests/test_recovery_contract_study.py','tests/test_streaming_ledger.py')
for f in dict.fromkeys(study.FILES+extra):
 p=snapshot/f;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/f,p)
shutil.copyfile('/private/tmp/nexvia-recovery-study-v2-20261116/summary.json',snapshot/'expected_summary.json')
with Path('/private/tmp/nexvia-recovery-study-v2-20261116/assignments.jsonl').open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
(snapshot/'expected_raw_sha256.txt').write_text(h+'\n');shutil.copyfile('/private/tmp/nexvia-recovery-20261116/reproduce.py',snapshot/'reproduce.py')
print('Prepared final snapshot',flush=True)
