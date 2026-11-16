"""Descriptive examples from the fixed development study, not inferential plots."""
import argparse,hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser(description=__doc__);p.add_argument('ledger',type=Path);p.add_argument('output_prefix',type=Path);a=p.parse_args()
outputs=[a.output_prefix.with_suffix('.png'),a.output_prefix.with_suffix('.svg')]
if any(o.exists() for o in outputs):p.error('output exists')
ids=['v1:controller_stall:DUAL_HOLD','v1:controller_stall:WITNESS_LEASE','v1:mass_gravity_offset:WITNESS_LEASE']
data={key:{'ticks':[],'physics':[]} for key in ids}
with a.ledger.open() as f:
 for line in f:
  r=json.loads(line)['payload']
  if r['kind']=='EVENT' and r['id'] in data:
   e=r['details']
   if e['type']=='TICK':data[r['id']]['ticks'].append(e)
   elif e['type']=='PHYSICS':data[r['id']]['physics'].append(e)
fig,axes=plt.subplots(2,2,figsize=(12,7.5),layout='constrained')
styles=[(ids[0],'Hold without lease','#D55E00'),(ids[1],'Capture check + lease','#0072B2')]
for key,label,color in styles:
 ticks=data[key]['ticks'];physics=data[key]['physics']
 axes[0,0].step([t['step']*.02 for t in ticks],[t['logic']['force_n'][0] for t in ticks],where='post',label=label,color=color,lw=2)
 axes[0,1].plot([r['time'] for r in physics],[r['position'][0] for r in physics],label=label,color=color,lw=2)
axes[0,0].axvline(.12,color='#444444',ls=':',label='Controller stops at 0.12 s')
axes[0,0].axvline(.18,color='#888888',ls='--',label='Modeled brake activates at 0.18 s')
axes[0,0].set(title='Controller stall: leases cut stale commands',ylabel='Commanded X force (N)');axes[0,0].legend(frameon=False,fontsize=8,loc='lower right')
axes[0,1].axhline(-2.8,color='#444444',ls=':',label='Model arena clearance boundary')
axes[0,1].set(title='A valid travel bound can still allow leaving the arena',ylabel='X position (m)');axes[0,1].legend(frameon=False,fontsize=8)
physics=data[ids[2]]['physics'];times=[r['time'] for r in physics]
speeds=[sum(v*v for v in r['velocity'])**.5 for r in physics]
axes[1,0].plot(times,speeds,color='#CC79A7',lw=2);axes[1,0].set(title='Mass/gravity mismatch: speed falls after contact',ylabel='Sampled speed (m/s)')
axes[1,1].plot(times,[r['position'][2] for r in physics],color='#009E73',lw=2,label='Robot center height')
contact=[r for r in physics if r['contact_floor'] or r['contact_obstacle']]
axes[1,1].scatter([r['time'] for r in contact],[r['position'][2] for r in contact],s=13,color='#D55E00',label='Recorded contact',zorder=3)
axes[1,1].axhline(.2,color='#444444',ls=':',label='Sphere radius above floor')
axes[1,1].set(title='Contact makes the free-motion reference unevaluable',ylabel='Height (m)');axes[1,1].legend(frameon=False,fontsize=8)
for ax in axes.flat:
 ax.set_xlabel('Simulation time (s)');ax.grid(alpha=.18);ax.spines[['top','right']].set_visible(False)
fig.suptitle('Development fault diagnostic: timing protection does not establish recovery',fontsize=15)
fig.supxlabel('Representative 0.5 m/s initial condition · new three-slide plant · hypothetical powered brakes\nDescriptive trajectories only. Contact and arena violations remain adverse evidence; no operational rest threshold is asserted.',fontsize=9,color='#444444')
for o in outputs:fig.savefig(o,dpi=180)
plt.close(fig)
print(json.dumps({'ledger_sha256':hashlib.sha256(a.ledger.read_bytes()).hexdigest(),'outputs':[str(o) for o in outputs]}))
