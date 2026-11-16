"""Same-interpreter source-path reproduction; no independent attestation.

The original run's source/parent/version metadata are intentionally reused and
identified. This does not create a release commit or claim a clean checkout.
"""
from pathlib import Path
import hashlib,importlib,json,platform,sys
import numpy as np
import mujoco
from scripts.research import recovery_contract_study as study
from scripts.research.development_ledger import DevelopmentLedger
root=Path(__file__).resolve().parent;expected=json.loads((root/'expected_summary.json').read_text());meta=expected['metadata']
assert study.ROOT==root
assert study.hashes()==meta['sources']
assert meta['versions']=={'python':platform.python_version(),'numpy':np.__version__,'mujoco':mujoco.__version__}
origins={}
for relative in study.FILES:
 name=relative.removeprefix('src/').removesuffix('.py').replace('/','.')
 if name.endswith('.__init__'):name=name.removesuffix('.__init__')
 m=importlib.import_module(name);origin=Path(m.__file__).resolve()
 assert origin==root/relative,(name,origin)
 origins[name]=str(origin.relative_to(root))
out=Path(sys.argv[1]);out.mkdir(exist_ok=False);ledger=out/'assignments.jsonl'
assignments=[dict(a,metadata=meta) for a in study.plan()]
with DevelopmentLedger.create(ledger,study=study.STUDY,assignments=assignments,record_events=True) as w:
 for a in assignments:
  w.start(a['id'])
  try:
   result=study.execute(a,lambda e:w.event(a['id'],details=e))
   assert study.hashes()==meta['sources']
   w.complete(a['id'],status='COMPLETED',details={'summary':result,'sources_after':study.hashes()})
  except Exception as exc:
   w.complete(a['id'],status='ERROR',details={'error_type':type(exc).__name__,'error':str(exc)});raise
 w.finalize()
actual=study.audit(ledger);digest=hashlib.file_digest(ledger.open('rb'),'sha256').hexdigest()
expected_hash=(root/'expected_raw_sha256.txt').read_text().strip()
verification={'raw_sha256':digest,'expected_raw_sha256':expected_hash,'raw_identical':digest==expected_hash,'summary_identical':actual==expected,'import_origins':origins,'classification':'SAME_RUNTIME_SOURCE_PATH_REPRODUCTION_REUSES_ORIGINAL_PARENT_METADATA','gate_b':'GATE_B_NOT_AUTHORIZED'}
(out/'summary.json').write_text(json.dumps(actual,indent=2,allow_nan=False)+'\n');(out/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
assert verification['raw_identical'] and verification['summary_identical']
print(json.dumps(verification,indent=2))
