from pathlib import Path
import json,hashlib,zipfile,shutil,xml.etree.ElementTree as ET
root=Path('/Users/chalermsak/Documents/ChatGPT/New project/nexvia-aegis');pkg=Path('/private/tmp/nexvia-recovery-package-20261116')
snapshot=Path('/private/tmp/nexvia-recovery-source-snapshot-20261116');reproduced=Path('/private/tmp/nexvia-recovery-source-reproduction-20261116')
verification=json.loads((reproduced/'verification.json').read_text());assert verification['raw_identical'] and verification['summary_identical']
archive=pkg/'results/research_development/dev/recovery_contract_source_reproduction_2026-11-16.zip'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
 for base,prefix in ((snapshot,'source'),(reproduced,'reproduced')):
  for f in sorted(base.rglob('*')):
   if f.is_file():z.write(f,prefix+'/'+str(f.relative_to(base)))
 z.write('/private/tmp/nexvia-recovery-source-reproduction-20261116.log','execution.log')
 z.writestr('README.txt','Extract into a new directory. Use the recorded Python 3.12.14 / NumPy 2.5.3 / MuJoCo 3.14.0 runtime. From source/, run PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. /ABSOLUTE/PATH/TO/PYTHON reproduce.py /NEW/OUTPUT/DIRECTORY. Driver verifies source/version maps and import paths, reuses ORIGINAL parent metadata and checks raw and summary equality. This is not an independent build or replication.\n')
with zipfile.ZipFile(archive) as z:assert z.testzip() is None
# Keep packaging/reproduction tooling as readable evidence, too.
for f in ('prepare_recovery_evidence.py','finish_recovery_package.py','reproduce.py'):
 target=pkg/'results/research_development/analysis/recovery_packaging_2026-11-16'/f;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(Path('/private/tmp/nexvia-recovery-20261116')/f,target)
print('Source reproduction archived:',archive.stat().st_size)
