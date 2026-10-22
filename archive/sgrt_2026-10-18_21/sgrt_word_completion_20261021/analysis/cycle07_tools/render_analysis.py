"""Presentation-only renderer of independently reviewed cycle07 analysis."""
from pathlib import Path
import argparse,json
import numpy as np,pandas as pd
from new_adapter import path,sha

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--analysis',required=True);ap.add_argument('--review');ap.add_argument('--provisional',action='store_true');ap.add_argument('--output',required=True);a=ap.parse_args();src=path(a.analysis);review=path(a.review)if a.review else None;receipt=src/'run_receipt.json';assert json.loads(receipt.read_text())['source_inputs_unchanged']is True
 if not a.provisional:
  assert review is not None;ad=json.loads(review.read_text());assert ad['all_checks_passed']is True;assert sha(receipt)in review.read_text(),'Review must bind exact completed analysis receipt'
 out=path(a.output);assert not out.exists();out.mkdir(parents=True)
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 plt.rcParams.update({'font.size':9,'savefig.dpi':180})
 labels={'log_own_mass2021':'Масса собственного центра 2021 (log)','log_baseline_system_population2010':'Население аддитивных членов 2010 (log)','log_rural_own_center_minutes':'Время пути сельских жителей к ядру (log1p)','log_agro_grain_yield2021':'Муниципальная урожайность 2021 (log1p)','sat_normal':'Сумма активных температур','summer_moisture_normal':'Влага: летнее P/PET','soil_rating_midpoint':'FAO: почвенный индекс (прокси)','log_comparable_provider_count':'Сопоставимые исходные поставщики (log1p)','observed_provider_mass_hhi':'Концентрация исходных масс (HHI)','rural_suburban_share':'Сельские жители в поясе 30–60 минут','mass_x_suburban':'Масса × пригородная доля','log_rural_large_city_minutes':'Время пути к крупному городу (log1p)'}
 if a.provisional:plt.rcParams['figure.facecolor']='#fff8ed'
 metrics=pd.read_csv(src/'model_metrics.csv');coef=pd.read_csv(src/'coefficient_intervals.csv');gates=pd.read_csv(src/'sample_gates.csv');pred=pd.read_parquet(src/'unit_predictions.parquet');primary=metrics[metrics.scenario.str.endswith('__primary')].copy();fig,axes=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
 for ax,family in zip(axes,['A_M1_M2','B_M1_M2_M3_inventory']):
  z=primary[primary.comparison_family.eq(family)]
  if z.candidate_cap.nunique()==1:
   ax.bar(np.arange(len(z)),z.group_oof_r2_train_mean_baseline,color=['#3672a5','#e39d39','#4d916c'][:len(z)]);ax.set_xticks(np.arange(len(z)),['M3: инвентарь'if m=='M3_inventory_structure'else m for m in z.model]);ax.set_xlabel(f'Модель; сценарий {int(z.candidate_cap.iloc[0])} минут')
  else:
   for model,part in z.groupby('model',sort=True):
    part=part.sort_values('candidate_cap');ax.plot(part.candidate_cap,part.group_oof_r2_train_mean_baseline,'o-',label=model)
   ax.set_xlabel('Транспортный сценарий, минут');ax.set_xticks(sorted(gates.candidate_cap.unique()));ax.legend(fontsize=8)
  ax.axhline(0,c='gray',lw=.7);ax.set_title(f'{family[0]}: отдельная общая выборка, n={int(z.n.iloc[0])}');ax.set_ylabel('R² проверки по отложенным регионам');ax.set_ylim(min(0,primary.group_oof_r2_train_mean_baseline.min())-.02,max(0,primary.group_oof_r2_train_mean_baseline.max())+.03)
 fig.suptitle(('Числа ожидают независимой проверки.\n'if a.provisional else'')+'Описательные модели: проверка на отложенных регионах\nСценарии не являются географическими уровнями; между семействами выборки различаются',fontsize=11);fig.savefig(out/'region_validation.png');fig.savefig(out/'region_validation.pdf');plt.close(fig)
 for family,model in [('A_M1_M2','M2'),('B_M1_M2_M3_inventory','M3_inventory_structure')]:
  z=coef[coef.scenario.eq(family+'__primary')&coef.model.eq(model)&coef.term.ne('intercept')];caps=sorted(z.candidate_cap.unique())
  if not caps:continue
  fig,axes=plt.subplots(1,len(caps),figsize=(max(9,3.6*len(caps)),6.5),sharey=True,constrained_layout=True);axes=np.atleast_1d(axes);terms=list(dict.fromkeys(z.term));mapping={t:i for i,t in enumerate(terms)}
  for ax,cap in zip(axes,caps):
   p=z[z.candidate_cap.eq(cap)];yy=p.term.map(mapping);ax.errorbar(p.beta,yy,xerr=[np.maximum(0,p.beta-p.ci95_lower),np.maximum(0,p.ci95_upper-p.beta)],fmt='o',capsize=2);ax.axvline(0,c='gray',lw=.7);ax.set_title(f'{int(cap)} минут');ax.set_xlabel('Изменение, п.п. / 1 SD фактора');ax.set_yticks(range(len(terms)),[labels.get(t,t)for t in terms])
  fig.suptitle(('Числа ожидают независимой проверки.\n'if a.provisional else'')+f'Семейство {family[0]}, '+('M3: инвентарь'if model=='M3_inventory_structure'else model)+': описательные коэффициенты и 95% CR1-интервалы\nОценки зависят от полноты исходных данных; инвентарная концентрация не доказывает полицентричность',fontsize=10);fig.savefig(out/f'{family}_coefficients.png',bbox_inches='tight');fig.savefig(out/f'{family}_coefficients.pdf',bbox_inches='tight');plt.close(fig)
 fig,ax=plt.subplots(figsize=(11,5),constrained_layout=True)
 for family,z in gates[gates.scenario.str.endswith('__primary')].groupby('comparison_family'):
  z=z.sort_values('candidate_cap');ax.plot(z.candidate_cap,z.common_sample,'o-',label={'A':'Семейство A: M1–M2','B':'Семейство B: M1–M3'}[family[0]])
 ax.set_xlabel('Транспортный сценарий, минут');ax.set_ylabel('Общая полная выборка единиц');ax.set_title('Доступность данных до оценивания моделей');ax.set_xticks(sorted(gates.candidate_cap.unique()));ax.legend();fig.savefig(out/'common_samples.png');plt.close(fig)
 # Explicit chart-value table makes every displayed scalar independently recoverable.
 primary.to_csv(out/'region_validation_chart_values.csv',index=False);coef[coef.scenario.str.endswith('__primary')].to_csv(out/'coefficient_chart_values.csv',index=False);gates[gates.scenario.str.endswith('__primary')].to_csv(out/'sample_chart_values.csv',index=False)
 pins={p.name:sha(p)for p in [src/'model_metrics.csv',src/'coefficient_intervals.csv',src/'sample_gates.csv',receipt]+([review]if review else[])};(out/'receipt.json').write_text(json.dumps({'status':'PROVISIONAL_PRESENTATION_PENDING_NUMERIC_AND_VISUAL_REVIEW'if a.provisional else'PRESENTATION_ONLY_NO_REFIT_PENDING_VISUAL_REVIEW','source_family':json.loads(receipt.read_text())['source_family'],'input_sha256':pins,'script_sha256':sha(Path(__file__)),'output_sha256':{p.name:sha(p)for p in out.iterdir()if p.is_file()},'predictor_labels':labels,'caps_are_scenarios_not_tiers':True,'causal_claim':False},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
