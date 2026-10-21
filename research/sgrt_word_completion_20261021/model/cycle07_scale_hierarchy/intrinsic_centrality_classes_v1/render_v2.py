"""Source-only centrality diagnostics; engineering classes are not functional ranks."""
from pathlib import Path
import json,hashlib
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;SRC=HERE/'output_source477_v2';OUT=HERE/'figures_source477_v2';OUT.mkdir(exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inputs={str(p):sha(p)for p in [SRC/'receipt.json',SRC/'all_eligible_source_provider_classes.parquet',SRC/'baseline_allK_scree.parquet',SRC/'all500_replicate_K_curves.parquet',SRC/'accepted_source_class_boundaries.csv',SRC/'class_source_descriptive_ranges.csv',Path(__file__)]}
d=pd.read_parquet(SRC/'all_eligible_source_provider_classes.parquet');a=d[d.intrinsic_class_scope.eq('ordinary_eligible_source_provider')];external=d[~d.intrinsic_class_scope.eq('ordinary_eligible_source_provider')];base=pd.read_parquet(SRC/'baseline_allK_scree.parquet');boot=pd.read_parquet(SRC/'all500_replicate_K_curves.parquet');bounds=pd.read_csv(SRC/'accepted_source_class_boundaries.csv');meta=json.loads((SRC/'receipt.json').read_text());assert meta['accepted_stable_classes'];colors=['#5e3c99','#1b9e77','#d95f02']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10});fig,axes=plt.subplots(2,2,figsize=(16,11),constrained_layout=True)
ax=axes[0,0]
for _,g in boot.groupby('replicate_id'):ax.plot(g.K,g.sse/g.sse.iloc[0],color='0.75',alpha=.35,lw=.6)
ax.plot(base.K,base.sse/base.sse.iloc[0],'o-',color='#222222',lw=2,label='исходные данные');ax.axvline(meta['baseline_elbow']['K'],color='#ba3030',ls='--',label='выбранное K=3');ax.set(xlabel='Число классов K',ylabel='SSE / SSE(K=1)',title='А. Эмпирическая инженерная дискретизация');ax.legend(fontsize=9)
ax=axes[0,1];x=np.log(a.own_positive_mass);ax.hist(x,bins=60,color='#597d8a',alpha=.85)
for b in bounds.itertuples():ax.axvline(b.logMi_midpoint,color='#ba3030',ls='--');ax.text(b.logMi_midpoint,ax.get_ylim()[1]*.95,f'Mi={b.Mi_midpoint:.3f}',rotation=90,va='top',ha='right',fontsize=9)
ax.set(xlabel='ln(фиксированной собственной Mi)',ylabel='Число исходных центров',title='Б. Фиксированная Mi; окружение не входит в расчёт классов')
ax=axes[1,0];samples=[np.log1p(a.loc[a.intrinsic_centrality_class.eq(c),'population_2021'].to_numpy())for c in range(3)];parts=ax.boxplot(samples,labels=['класс 0','класс 1','класс 2'],patch_artist=True,showfliers=True,flierprops={'markersize':1.5,'alpha':.25})
for box,color in zip(parts['boxes'],colors):box.set_facecolor(color);box.set_alpha(.7)
ticks=[0,100,1000,10000,100000,1000000];ax.set_yticks(np.log1p(ticks));ax.set_yticklabels(['0','100','1 тыс.','10 тыс.','100 тыс.','1 млн']);ax.set(ylabel='Собственное население 2021: шкала ln(1+P)',title='В. Размер центра — описание, не условие расчёта классов')
ax=axes[1,1];counts={}
for c,color in enumerate(colors):
 g=a[a.intrinsic_centrality_class.eq(c)&a[['lat','lon']].notna().all(axis=1)];lon=g.lon.to_numpy();lon=np.where(lon<0,lon+360,lon);ax.scatter(lon,g.lat,s=2.5,color=color,alpha=.55,rasterized=True,label=f'класс {c}: {int(a.intrinsic_centrality_class.eq(c).sum())}');counts[str(c)]=len(g)
lon=external.lon.to_numpy();lon=np.where(lon<0,lon+360,lon);ax.scatter(lon,external.lat,marker='*',s=95,color='#333333',edgecolor='white',linewidth=.7,label='Москва/СПб: вне расчёта классов');ax.set(xlabel='Долгота °E (отрицательная +360°)',ylabel='Широта °N',title='Г. Только реальные точки; не границы или потоки');ax.legend(markerscale=2,fontsize=8,loc='upper right');ax.set_aspect(1.7)
fig.suptitle('Три класса собственной центральности, отдельно от четырёх вложенных разрешений\n26 691 исходный центр + 2 внешних контекста; функциональный порядок НЕ присвоен\n1 центр без координат не нанесён на карту; в таблицах и расчёте классов он сохранён',fontsize=15)
fig.savefig(OUT/'intrinsic_centrality_diagnostics.png',dpi=180);fig.savefig(OUT/'intrinsic_centrality_diagnostics.pdf',dpi=180);plt.close(fig)
assert all(sha(Path(p))==h for p,h in inputs.items());r={'status':'RENDERED_PENDING_INDEPENDENT_NUMERIC_AND_VISUAL_RESULT_ADMISSION','source_pins':inputs,'numeric_admission_sha256':'9a2bcdac43b1f19c500c1fa23cda512f940bfcad6d476e1bfee7ea8156230f72','ordinary_rows':len(a),'external_unfitted':len(external),'actual_map_point_counts_by_class':counts,'nonlocated_sources_not_drawn':int(a[['lat','lon']].isna().any(axis=1).sum()),'no_continuous_polygons_or_observed_flows':True,'engineering_classes_not_functional_orders':True,'population_not_fitted':True,'files_sha256':{p.name:sha(p)for p in OUT.iterdir()if p.is_file()}};(OUT/'figure_manifest.json').write_text(json.dumps(r,indent=2));print(r['actual_map_point_counts_by_class'],r['nonlocated_sources_not_drawn'])
