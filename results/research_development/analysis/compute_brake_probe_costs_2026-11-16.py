"""Reproduce descriptive costs from this development probe ledger, not inference."""
import argparse,json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('probe_ledger',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
if a.output.exists():p.error('output exists')
with a.probe_ledger.open() as f:
 header=json.loads(next(f))['payload']
 if header['study']!='V9-M5 finite-window brake diagnostic v1':raise ValueError('wrong development study')
 runtime,terminal={},{}
 for line in f:
  r=json.loads(line)['payload']
  if r['kind']=='EVENT' and r['details']['type']=='DESIGN':runtime[r['id']]=r['details']['runtime']
  elif r['kind']=='TERMINAL':
   if r['status']!='COMPLETED':raise ValueError('incomplete/error design')
   terminal[r['id']]=r['details']['summary']
rows=[]
for design in header['assignments']:
 s=terminal[design['id']];v=design['initial_speed_m_s'];m=runtime[design['id']]['mass_kg'];dt=runtime[design['id']]['dt']
 if m!=1.:raise ValueError('this descriptive artifact expects the declared 1 kg probe model')
 rows.append({'assignment_id':design['id'],'physics_steps':s['physics_steps'],'window_seconds':s['physics_steps']*dt,
  'sampled_path_m':s.get('sampled_path_m'),'initial_speed_m_s':v,'residual_speed_m_s':s['residual_speed_m_s'],
  'observed_delta_kinetic_energy_j':.5*m*(s['residual_speed_m_s']**2-v**2) if s['residual_speed_m_s'] is not None else None,
  'energy_admission_limit':'UNSPECIFIED_NOT_AN_OPERATIONAL_ENERGY_BUDGET'})
with a.output.open('x') as f:json.dump({'classification':'POSTHOC_DESCRIPTIVE_MODEL_COSTS','mass_kg':1.,'rows':rows,'limitations':'True simulation velocities for scoring only; no energy/rest approval threshold.'},f,indent=2);f.write('\n')
