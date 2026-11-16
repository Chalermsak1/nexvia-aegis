"""Render descriptive dependent-world observations; no inferential error bars."""
import argparse
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('summary',type=Path);p.add_argument('output_prefix',type=Path)
a=p.parse_args()
outputs=[a.output_prefix.with_suffix('.png'),a.output_prefix.with_suffix('.svg')]
if any(path.exists() for path in outputs):p.error('output already exists')
r=json.loads(a.summary.read_text())
cases=['nominal','primary_reverse','secondary_reverse','shared_reverse','shared_retimestamped_stale','damper_unavailable']
labels=['Nominal','Primary\nreversal','Secondary\nreversal','Shared\nreversal','Shared stale data\nrelabeled fresh','Damper\nunavailable']
styles=[('SINGLE_COAST','One source + coast','#0072B2','o',-.20),('DUAL_COAST','Two sources + coast','#D55E00','s',0.),('DUAL_DAMPER','Two sources + modeled damper','#009E73','^',.20)]
fig,ax=plt.subplots(figsize=(12,6.1),layout='constrained')
for arm,label,color,marker,offset in styles:
    xs,ys=[],[]
    for i,case in enumerate(cases):
        selected=[v for v in r['assignments'] if v['id'].endswith(':'+case+':'+arm)]
        assert len(selected)==3 and all(v['state']=='COMPLETED' for v in selected)
        for j,v in enumerate(selected):
            xs.append(i+offset+(j-1)*.035);ys.append(v['summary']['final_sampled_speed_m_s'])
    ax.scatter(xs,ys,label=label,color=color,marker=marker,s=45,alpha=.85,edgecolors='white',linewidth=.5,zorder=3)
ax.set_yscale('log');ax.set_ylim(.0008,7.)
ax.set_xticks(range(len(cases)),labels);ax.tick_params(axis='x',length=0,pad=9)
ax.set_ylabel('Final sampled speed (m/s; log scale)',fontsize=11)
ax.set_title('Two-source checking helps with individual faults; shared faults remain',loc='left',fontsize=15,pad=45)
ax.legend(loc='lower left',bbox_to_anchor=(0.,1.015),ncol=3,frameon=False,fontsize=10,borderaxespad=0)
ax.grid(axis='y',which='major',color='#e1e4e8',linewidth=.8,zorder=0)
ax.spines[['top','right']].set_visible(False)
fig.supxlabel('Three inspected development worlds per arm · 100 × 20 ms steps · hypothetical passive damper\nIndividual dots are dependent observations. No rest threshold, safety certification or population inference.',fontsize=9,color='#444444')
for output in outputs:fig.savefig(output,dpi=180)
plt.close(fig)
print(json.dumps({'summary_sha256':hashlib.sha256(a.summary.read_bytes()).hexdigest(),'outputs':[str(o) for o in outputs]}))
