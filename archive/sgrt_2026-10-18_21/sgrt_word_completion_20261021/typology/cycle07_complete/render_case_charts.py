"""Source-bound measured case cards, preserving missing observations as gaps."""
import argparse,hashlib,json,textwrap
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--classification',required=True);p.add_argument('--output',required=True);a=p.parse_args()
 src=Path(a.classification);out=Path(a.output)
 if out.exists():raise FileExistsError('Fresh chart directory required')
 receipt=json.loads((src/'receipt.json').read_text()); assert receipt['all_units_classified'] is True
 for f,s in receipt['files'].items(): assert sha(src/f)==s
 cases=pd.read_parquet(src/'case_chart_selection.parquet');ev=pd.read_parquet(src/'trajectory_evidence.parquet');out.mkdir(parents=True)
 ledger=[]
 for _,r in cases.iterrows():
  ue=ev[ev.unit_id==r.unit_id]; fig,axes=plt.subplots(1,3,figsize=(13,4),squeeze=False)
  objects=list(ue.object.drop_duplicates())
  for i,ax in enumerate(axes[0]):
   if i>=len(objects):ax.set_visible(False);continue
   obj=objects[i];rows=ue[ue.object==obj];points={}
   for _,e in rows.iterrows():
    for side in ('start','end'):
     y=int(e[side+'_year']);v=e[side+'_population_raw']; complete=e[side+'_complete']
     usable=pd.notna(complete) and bool(complete) and pd.notna(v) and np.isfinite(float(v)) and float(v)>=0
     # Non-applicable objects have no invented zero line.
     if pd.isna(e.applicable) or not bool(e.applicable):usable=False
     points[y]=float(v) if usable else np.nan
   years=[2002,2010,2021];vals=[points.get(y,np.nan) for y in years]
   ax.plot(years,vals,'o-',lw=1.5);ax.set_xticks(years);ax.set_title(obj);ax.set_ylabel('человек');ax.grid(alpha=.2)
   for y,v in zip(years,vals):
    if np.isnan(v):ax.text(y,.05,'NA',transform=ax.get_xaxis_transform(),ha='center',color='gray')
   states='; '.join(f"{e.period}: {e.state}" for _,e in rows.iterrows())
   ax.text(0,-.27,states,transform=ax.transAxes,fontsize=7,wrap=True)
  fig.suptitle(textwrap.fill(f"{r.unit_name} ({r.unit_id})",100)+"\n"+textwrap.fill(r.primary_type_name,120),fontsize=9)
  fig.text(.01,.01,f"Поддержка: {r.classification_confidence}. Качество: {r.source_quality_flags}. Пропуск не означает ноль. Причинный механизм не установлен.",fontsize=7)
  fig.subplots_adjust(bottom=.31,top=.75,wspace=.35)
  fn=hashlib.sha256(str(r.unit_id).encode()).hexdigest()[:18]+'.png';fig.savefig(out/fn,dpi=150);plt.close(fig)
  ledger.append({'unit_id':r.unit_id,'primary_type_id':r.primary_type_id,'classification_confidence':r.classification_confidence,'path':fn,'sha256':sha(out/fn)})
 pd.DataFrame(ledger).to_csv(out/'case_chart_ledger.csv',index=False)
 (out/'receipt.json').write_text(json.dumps({'status':'COMPUTED_SOURCE_BOUND_CASE_CHARTS','classification_receipt_sha256':sha(src/'receipt.json'),'case_count':len(cases),'all_selected_cases_rendered':len(ledger)==len(cases),'renderer_sha256':sha(__file__),'files':{x.name:sha(x) for x in out.iterdir() if x.is_file()}},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
