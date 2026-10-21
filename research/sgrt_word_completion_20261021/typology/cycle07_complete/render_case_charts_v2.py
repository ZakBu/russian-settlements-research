"""Russian review cards: rendering-only revision; classifier/source data untouched."""
import argparse,hashlib,json,re,textwrap
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

OBJECT={'own':'Собственный ряд','center':'Ядро','rural':'Сельское окружение','system':'Вся система'}
STATE={'growth':'рост','stable':'стабильность','decline':'убыль','extinction_observed':'наблюдаемое обнуление','emergence_observed':'рост из нулевой базы','observed_zero_both':'оба наблюдения нулевые','unavailable':'динамика недоступна','not_applicable':'объект не применим'}
CONFIDENCE={'structural_only':'Структура известна, динамика не установлена.','partial_demographic_support':'Динамика установлена для части объектов.','tentative_source_quality':'Предварительная динамика: качество источников и сопоставимость ограничены.','source_supported_numeric':'Классификация поддержана наблюдёнными численностями.'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def short_description(row):
 states=json.loads(row.trajectory_class)
 if row.structural_class=='protected_carry':return 'Исходная единица без подтверждённого функционального присоединения. '+STATE[states['own']].capitalize()+'.'
 return '; '.join(OBJECT[obj]+': '+STATE[st] for obj,st in states.items())+'.'
def main():
 p=argparse.ArgumentParser();p.add_argument('--classification',required=True);p.add_argument('--output',required=True);a=p.parse_args();src=Path(a.classification);out=Path(a.output)
 if out.exists():raise FileExistsError('Fresh chart output required')
 r=json.loads((src/'receipt.json').read_text());assert r['all_units_classified'] is True and r['status']=='COMPUTED_COMPLETE_MEASURED_PARTITION_NOT_CAUSAL_TYPES'
 for f,s in r['files'].items():assert sha(src/f)==s
 cases=pd.read_parquet(src/'case_chart_selection.parquet');ev=pd.read_parquet(src/'trajectory_evidence.parquet');out.mkdir(parents=True);ledger=[]
 for _,case in cases.iterrows():
  rows=ev[ev.unit_id==case.unit_id];objects=list(rows.object.drop_duplicates());single=len(objects)==1
  fig,axes=plt.subplots(1,len(objects),figsize=(7.4 if single else 14,6.2),squeeze=False)
  for ax,obj in zip(axes[0],objects):
   rr=rows[rows.object==obj];points={}
   for _,e in rr.iterrows():
    for side in ('start','end'):
     y=int(e[side+'_year']);v=e[side+'_population_raw'];complete=e[side+'_complete']
     usable=pd.notna(complete) and bool(complete) and pd.notna(v) and np.isfinite(float(v)) and float(v)>=0 and pd.notna(e.applicable) and bool(e.applicable)
     points[y]=float(v) if usable else np.nan
   years=[2002,2010,2021];values=[points.get(y,np.nan) for y in years]
   ax.plot(years,values,'o-',lw=1.7,color='#25658a');ax.set_xlim(2001,2022);ax.set_xticks(years);ax.set_title(OBJECT[obj],fontsize=12,pad=10);ax.set_ylabel('Численность, чел.',fontsize=10);ax.grid(alpha=.2)
   ax.yaxis.set_major_formatter(FuncFormatter(lambda x,pos:f'{x:,.0f}'.replace(',',' ')))
   finite=[v for v in values if np.isfinite(v)]
   if not finite:ax.set_ylim(0,1);ax.set_yticks([]);ax.text(.5,.5,'Нет полного наблюдаемого ряда',ha='center',va='center',transform=ax.transAxes,color='#666666',fontsize=9,wrap=True)
   elif max(finite)==0:ax.set_ylim(0,1)
   elif min(finite)==0:ax.set_ylim(bottom=0)
   for year,value in zip(years,values):
    if not np.isfinite(value):ax.text(year,.035,'NA',transform=ax.get_xaxis_transform(),ha='center',color='#777777',fontsize=9)
   diagnosis='\n'.join(f"{e.period.replace('-','–')}: {STATE[e.state]}" for _,e in rr.iterrows())
   ax.text(0,-.27,diagnosis,transform=ax.transAxes,fontsize=9,va='top',linespacing=1.5)
  match=re.match(r'cap_(\d+):',str(case.unit_id));cap=int(match.group(1)) if match else None
  title=str(case.unit_name)+(f' · вариант {cap} мин' if cap is not None else '')
  fig.suptitle(title,fontsize=15,y=.965)
  fig.text(.5,.89,textwrap.fill(short_description(case),80 if single else 150),ha='center',va='top',fontsize=10)
  fig.subplots_adjust(left=.10 if single else .065,right=.97,bottom=.36,top=.77,wspace=.35)
  confidence=CONFIDENCE[case.classification_confidence]
  fig.text(.035,.115,textwrap.fill(confidence,95 if single else 180),fontsize=9,va='top')
  limitation='NA означает пропуск или неполную сумму, а не ноль. История границ и причинные механизмы не подтверждены.'
  if not single:limitation+=' Вся система включает ядро, сельских и прочих несельских членов. Шкалы численности различаются.'
  if cap is not None:limitation+=' Временной предел — операционный вариант, не географический ранг.'
  fig.text(.035,.065,textwrap.fill(limitation,105 if single else 200),fontsize=8,va='top',color='#555555')
  name=hashlib.sha256(str(case.unit_id).encode()).hexdigest()[:18]+'.png';fig.savefig(out/name,dpi=150);plt.close(fig)
  ledger.append({'unit_id':case.unit_id,'unit_name':case.unit_name,'primary_type_id':case.primary_type_id,'primary_type_name':case.primary_type_name,'classification_confidence':case.classification_confidence,'path':name,'sha256':sha(out/name)})
 pd.DataFrame(ledger).to_csv(out/'case_chart_ledger.csv',index=False)
 receipt={'status':'COMPUTED_RUSSIAN_CASE_CARDS_RENDER_ONLY_V2','classification_receipt_sha256':sha(src/'receipt.json'),'case_count':len(cases),'all_selected_cases_rendered':len(ledger)==len(cases),'renderer_sha256':sha(__file__),'source_data_or_classifier_changed':False,'display_aliases_only':True,'technical_ids_retained_in_ledger_not_plot':True,'files':{p.name:sha(p) for p in out.iterdir() if p.is_file()}}
 (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps({'case_count':len(cases),'receipt_sha256':sha(out/'receipt.json')}))
if __name__=='__main__':main()
