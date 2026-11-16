"""Descriptive force observability examples; asserted bounds are not CIs."""
import argparse,hashlib,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p=argparse.ArgumentParser(description=__doc__);p.add_argument('reference_ledger',type=Path);p.add_argument('probe_ledger',type=Path);p.add_argument('output_prefix',type=Path);a=p.parse_args()
outputs=[a.output_prefix.with_suffix('.png'),a.output_prefix.with_suffix('.svg')]
if any(o.exists() for o in outputs):p.error('output exists')
series=[]
with a.reference_ledger.open() as f:
 items=[]
 for line in f:
  r=json.loads(line)['payload']
  if r['kind']=='EVENT' and r['id']=='v1:brake_loss:REFERENCE_FEEDBACK' and r['details']['type']=='SENSORS':
   e=r['details'];b=e['monitor']['feedback']['brake_force']
   if b['expected_force_intervals_n'] is not None:
    items.append((e['step']*.02,b['expected_force_intervals_n'][0],e['measurements']['force']['value'][0],b['status']))
 series.append(items)
for identifier in ('v1:brake_absent','v1:coherent_spoof'):
 items=[]
 with a.probe_ledger.open() as f:
  for line in f:
   r=json.loads(line)['payload']
   if r['kind']=='EVENT' and r['id']==identifier and r['details']['type']=='OBSERVATION':
    e=r['details'];b=e['brake_check']
    if b['expected_force_intervals_n'] is not None:items.append((e['tick']*.02,b['expected_force_intervals_n'][0],e['force']['value'][0],b['status']))
 series.append(items)
fig,axes=plt.subplots(3,1,figsize=(11,8.8))
fig.subplots_adjust(left=.08,right=.98,bottom=.12,top=.88,hspace=.60)
titles=['Passive low-speed brake loss: the uncertainty set permits zero force',
        'Earlier finite-window pulse: missing brake force becomes inconsistent',
        'Coordinated false feedback: a plausible reading can still be false']
colors=['#777777','#D55E00','#0072B2']
for ax,items,title,color in zip(axes,series,titles,colors):
 t=[x[0] for x in items];lo=[x[1][0] for x in items];hi=[x[1][1] for x in items];measured=[x[2] for x in items]
 assert items
 tx=t+[t[-1]+.02]
 ax.fill_between(tx,lo+[lo[-1]],hi+[hi[-1]],step='post',color='#56B4E9',alpha=.35,label='Expected X-force interval under asserted model')
 ax.errorbar(t,measured,yerr=.005,fmt='o',color=color,markersize=4,capsize=2,label='Virtual force reading ± asserted coordinate error')
 ax.axhline(0.,color='#222222',ls='--',lw=1,label='Actual modeled brake force: zero')
 ax.set(title=title,ylabel='X force (N)',xlabel='Interval start (simulation seconds)')
 ax.set_ylim(-1.12,.15);ax.grid(alpha=.15);ax.spines[['top','right']].set_visible(False)

handles,labels=axes[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.96),ncol=3,frameon=False,fontsize=8)
fig.suptitle('Brake diagnosis depends on excitation and trustworthy feedback',fontsize=15,y=.995)
fig.supxlabel('Representative 0.5 m/s start · different declared experiments; no direct reliability comparison\nReadings are available after the interval ends. Shading/error bars are asserted bounds, not confidence intervals. No rest/operational approval.',fontsize=9,color='#444444')
for o in outputs:fig.savefig(o,dpi=180)
plt.close(fig)
print(json.dumps({'source_sha256':{'reference':hashlib.sha256(a.reference_ledger.read_bytes()).hexdigest(),'probe':hashlib.sha256(a.probe_ledger.read_bytes()).hexdigest()},'outputs':[str(o) for o in outputs]}))
