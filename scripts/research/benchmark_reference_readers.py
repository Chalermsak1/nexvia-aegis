"""Read-only, single-process reader benchmark; invoke each method separately."""
import argparse,hashlib,json,platform,resource,time
from pathlib import Path
from scripts.research import physical_reference_study as old
from scripts.research import audit_reference_stream as stream
p=argparse.ArgumentParser();p.add_argument('method',choices=('retained','streaming'));p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
if a.output.exists():raise SystemExit('output exists')
start=time.perf_counter();result=(old.audit if a.method=='retained' else stream.audit)(a.input);elapsed=time.perf_counter()-start
core=stream.normalized(result);digest=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if platform.system()=='Darwin' else 1024)
r={'method':a.method,'wall_seconds':elapsed,'peak_process_rss_bytes':rss,'normalized_sha256':digest,'counts':result['counts'],'state':result['ledger_state'],'peak_buffered_episode_events':result.get('peak_buffered_episode_events'),'input_bytes':a.input.stat().st_size,'input_sha256':hashlib.file_digest(a.input.open('rb'),'sha256').hexdigest(),'python':platform.python_version(),'system':platform.platform(),'classification':'READ_ONLY_DEVELOPMENT_ARTIFACT_BENCHMARK_NO_PHYSICS_EXECUTION','cache_control':'NONE','gate_b':'GATE_B_NOT_AUTHORIZED'}
with a.output.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
print(json.dumps(r))
