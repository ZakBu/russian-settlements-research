#!/usr/bin/env python3
"""Presentation-only actual two-family regression plots. No refit; no cross-family benefit claim."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np,pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3]
def path(x):
 p=Path(x);return p if p.is_absolute() else REPO/p
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
LABELS={'log_own_mass2021':'Собственная масса центра (log)','log_baseline_system_population2010':'Население исходного состава в 2010 г. (log)','log_rural_own_center_minutes':'До собственного центра (log1p минут)','log_agro_grain_yield2021':'Урожайность зерновых в 2021 г. (log1p)','sat_normal':'Сумма активных температур','summer_moisture_normal':'Летнее увлажнение','soil_rating_midpoint':'Почвенный прокси GAEZ','polycentric_potential':'Полицентрический потенциал своего порядка','configuration_shared_origin_fraction':'Доля сельских НП с близкими полями','rural_suburban_share':'Доля населения в поясе 30–60 мин','mass_x_suburban':'Масса × пояс 30–60 мин','yield2021_x_polycentric':'Урожайность × полицентричность','log_rural_large_city_minutes':'До крупного города (log1p минут)'}
FAMILIES=[('A_M1_M2','A: общая выборка M1/M2',['M1','M2'],'M2'),('B_M1_M2_M3_configuration_observed','B: наблюдаемая конфигурация, M1/M2/M3',['M1','M2','M3'],'M3')]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--analysis',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();source=path(a.analysis);out=path(a.output)
 if out.exists():raise FileExistsError('Use a new presentation export directory')
 files=[source/f for f in ['model_metrics.csv','coefficient_intervals.csv','system_predictions.parquet','sample_gates.csv','run_receipt.json','output_manifest.json','effective_analysis_inputs.json']];before={str(p):sha(p) for p in files};metrics=pd.read_csv(files[0]);coeff=pd.read_csv(files[1]);pred=pd.read_parquet(files[2]);gates=pd.read_csv(files[3]);r=json.loads(files[4].read_text());assert r['status']=='ACTUALLY_COMPUTED_DESCRIPTIVE_REGRESSIONS';out.mkdir(parents=True)
 for table in [metrics,coeff,pred,gates]:assert 'comparison_family' in table
 plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white','svg.fonttype':'none'})
 records=[]
 def save(fig,name,meta):
  for ext in ['png','pdf','svg']:fig.savefig(out/(name+'.'+ext),dpi=200,bbox_inches='tight',pad_inches=.18)
  records.append({'name':name,**meta});plt.close(fig)
 colors=['#285b8b','#c06b31','#4c8272','#876f9b'];fig,axs=plt.subplots(2,2,figsize=(13,9),layout='constrained')
 for row,(family,title,models,final) in enumerate(FAMILIES):
  scenario=family+'__primary';primary=metrics[metrics.scenario.eq(scenario)]
  for j,level in enumerate(sorted(primary.level.unique())):
   g=primary[primary.level.eq(level)].set_index('model').loc[models];assert g.n.nunique()==1
   for ax,col in zip(axs[row],['r2','group_oof_r2_train_mean_baseline']):ax.plot(models,g[col],marker='o',color=colors[j%len(colors)],label=f'Уровень {level}; n={int(g.n.iloc[0])}');ax.set_ylabel('R²');ax.axhline(0,color='#777',lw=.7);ax.grid(axis='y',alpha=.2)
  for col,subtitle in enumerate(['Обучающая выборка','Отложенные регионы']):
   axs[row,col].set_title(title+'\n'+subtitle)
   if len(primary):axs[row,col].legend(frameon=False,fontsize=9)
   else:axs[row,col].text(.5,.5,'Модели не оценены:\nнедостаточная общая выборка',ha='center',va='center',transform=axs[row,col].transAxes,color='#555');axs[row,col].set_axis_off()
 fig.suptitle('Сопоставление моделей внутри каждой семьи\nВыборки A и B различаются; их разность не является эффектом добавления контекста',fontsize=14);save(fig,'within_family_model_comparison',{'source':'model_metrics.csv','scenarios':[x[0]+'__primary' for x in FAMILIES],'cross_family_effect_comparison':False,'r2_axis_not_clipped_to_positive_values':True})
 cfg=json.loads((source/'effective_analysis_inputs.json').read_text());fig,axs=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
 for ax,(family,title,models,final) in zip(axs,FAMILIES):
  z=gates[gates.scenario.eq(family+'__primary')].sort_values('level');required={term for model in models for term in cfg['model_terms'][model]};minimum=max(cfg['minimum_sample'],10*(len(required)+1));ax.bar(z.level.astype(str),z.common_sample,color='#285b8b' if family.startswith('A_') else '#c06b31');ax.axhline(minimum,color='#555',linestyle='--',label=f'Минимум по плану: {minimum}');ax.set_ylim(0,max(minimum*1.15,z.common_sample.max()*1.2));ax.set_xlabel('Уровень');ax.set_ylabel('Общая выборка, систем');ax.set_title(title);ax.legend(frameon=False,fontsize=9)
  for row in z.itertuples():ax.text(str(row.level),row.common_sample+max(minimum,z.common_sample.max())*.025,f'{row.common_sample}\n{row.regions} рег.',ha='center',fontsize=9)
 fig.suptitle('Достаточность общей выборки до оценки моделей\nДополнительно требуется не менее10 регионов; пороги не изменялись после расчёта',fontsize=13);save(fig,'primary_comparison_sample_gates',{'source':'sample_gates.csv','gate':'max(minimum_sample,10*(unionpredictorcount+1)) and minimum_regions','configuration_unknown_never_imputed':True})
 for family,title,models,final in FAMILIES:
  scenario=family+'__primary';eligible=coeff[coeff.scenario.eq(scenario)&coeff.model.eq(final)&coeff.term.ne('intercept')];geo=pred[pred.scenario.eq(scenario)&pred.model.eq(final)].copy()
  if eligible.empty or geo.empty:continue
  low=float(eligible.ci95_lower.min());high=float(eligible.ci95_upper.max());span=max(high-low,1.);xlim=(low-.05*span,high+.05*span);geo['plot_lon']=np.where(geo.lon<0,geo.lon+360,geo.lon);limit=max(float(np.quantile(np.abs(geo.group_oof_residual),.95)),1e-9);xmin,xmax=geo.plot_lon.min(),geo.plot_lon.max();ymin,ymax=geo.lat.min(),geo.lat.max()
  for level in sorted(eligible.level.unique()):
   z=eligible[eligible.level.eq(level)];fig,ax=plt.subplots(figsize=(11,max(5.2,len(z)*.46)),layout='constrained');y=np.arange(len(z));ax.errorbar(z.beta,y,xerr=[z.beta-z.ci95_lower,z.ci95_upper-z.beta],fmt='o',capsize=3,color='#285b8b',markersize=5);ax.set_yticks(y,[LABELS.get(t,t) for t in z.term]);ax.axvline(0,color='#666',lw=.8);ax.set_xlim(xlim);ax.set_xlabel('Изменение населения системы, п.п. на 1 SD предиктора');ax.set_title(f'{family[0]} · {final} · уровень {level}\n95% интервалы CR1 с группировкой по регионам',pad=14);ax.grid(axis='x',alpha=.18);save(fig,f'{family[0]}_{final}_coefficients_level{level}',{'source':'coefficient_intervals.csv','scenario':scenario,'comparison_family':family,'model':final,'level':int(level),'interval':'95% region-cluster CR1, t critical G−1','common_xscale_within_family':list(xlim),'omitted_terms':'Constant/collinear terms omitted, not zero'})
   z=geo[geo.level.eq(level)];fig,ax=plt.subplots(figsize=(11,5.2),layout='constrained');sc=ax.scatter(z.plot_lon,z.lat,c=z.group_oof_residual,s=22,cmap='RdBu_r',vmin=-limit,vmax=limit,edgecolors='none',alpha=.85);ax.set_xlim(xmin-2,xmax+2);ax.set_ylim(ymin-1,ymax+1);ax.set_xlabel('Долгота (отрицательные значения +360°)');ax.set_ylabel('Широта');ax.set_title(f'{family[0]} · {final} · уровень {level} · география ошибок\nПроверка на других регионах; фактическая выборка этой семьи',pad=12);cb=fig.colorbar(sc,ax=ax,shrink=.85);cb.set_label('Факт − прогноз, п.п.');save(fig,f'{family[0]}_{final}_residual_geography_level{level}',{'source':'system_predictions.parquet','scenario':scenario,'comparison_family':family,'model':final,'level':int(level),'coordinate_plot_not_boundary_map':True,'color_clip':'95thabsolutepercentilewithinthisfamily; visualonly','common_color_limits_within_family':[-limit,limit]})
 assert before=={str(p):sha(p) for p in files};receipt={'status':'RENDERED_FROM_FROZEN_ACTUAL_TWO_FAMILY_TABLES_NO_REFIT','analysis':str(source),'inputs':before,'code_sha256':sha(Path(__file__)),'figures':records,'outputs':{p.name:sha(p) for p in out.iterdir() if p.is_file()},'semantic_notes':['Only within-family comparisons share samples; no cross-family benefit inference.','L1 structural configuration remains unknown; absent B fit never drawn as mono.','Unknown-own-population ctxcores excluded from wholeincludingcenter outcomes, rural/context retained.','Suburban share is30–60minute band; soil is GAEZproxy, not bonitet.','Point geography covers modeledcompletecases, not complete national territory.']};(out/'render_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'figures':len(records),'formats':['png','pdf','svg'],'source_tables_unchanged':True}))
if __name__=='__main__':main()
