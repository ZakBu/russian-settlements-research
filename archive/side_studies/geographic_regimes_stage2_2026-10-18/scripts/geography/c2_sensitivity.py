"""C2 frozen descriptive claims; all prescribed grids, exact and1e-9km thresholds."""
import json,hashlib,platform
from pathlib import Path
import numpy as np,pandas as pd
B=Path(__file__).parent;O=B/'outputs';P=Path('/workspace/scratch/c21afd18c709/stage2_work/publish/research/geographic_regimes_stage2/protocols/descriptive_claims.md')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();inputs={p.name:sha(p) for p in [O/'territory_metrics.csv',O/'point_distances.csv.gz',P]}
m=pd.read_csv(O/'territory_metrics.csv');pts=pd.read_csv(O/'point_distances.csv.gz');origin=pts.nn2002_km.notna();d=pts.loc[origin].copy();d['change_fixed2002']=d.nn2021_km-d.nn2002_km;d['change_coords2021']=d.nn2021_original_coords_km-d.nn2002_km;d['change_survivor_neighbors']=d.nn2021_survivor_neighbors_km-d.nn2002_km
for v in ['fixed2002','coords2021','survivor_neighbors']:d['ratio_'+v]=np.divide(d['change_'+v]+d.nn2002_km,d.nn2002_km,out=np.full(len(d),np.nan),where=d.nn2002_km>0)
rows=[]
for kind in m.kind.unique():
 for unit,gg in d.groupby(kind):
  r={'kind':kind,'unit':unit}
  for variant in ['fixed2002','coords2021','survivor_neighbors']:
   for prefix in ['change','ratio']:
    v=gg[prefix+'_'+variant].dropna().to_numpy();r[f'{prefix}_{variant}_median']=np.quantile(v,.5) if len(v) else np.nan;r[f'{prefix}_{variant}_p90']=np.quantile(v,.9) if len(v) else np.nan
  rows.append(r)
agg=pd.DataFrame(rows);z=m.merge(agg,on=['kind','unit'],how='left',validate='one_to_one');diff=np.nanmax(np.abs(z.change_fixed2002_p90-z.nn_change_km_p90));assert diff<1e-10
z.to_csv(O/'c2_unit_sensitivities.csv',index=False)
records=[]
def summary(gg,kind,variant,tol,excluded):
 q=gg[gg.support20 & (gg.relchange_2002_2021<0)].copy();n=len(q);c=q.top10_delta_pp>0;t=q['change_'+variant+'_p90']>tol;r={'kind':kind,'variant':variant,'nn_threshold_km':tol,'excluded_dominant_region':excluded,'declined_supported_units':n,'joint_count':int((c&t).sum()),'concentration_only_count':int((c&~t).sum()),'nn_tail_only_count':int((~c&t).sum()),'neither_count':int((~c&~t).sum()),'joint_fraction':float((c&t).mean()) if n else np.nan,'concentration_increase_fraction':float(c.mean()) if n else np.nan,'nn_tail_increase_fraction':float(t.mean()) if n else np.nan,'top10_delta_pp_median':q.top10_delta_pp.median(),'paired_change_median_median_km':q['change_'+variant+'_median'].median(),'paired_change_p90_median_km':q['change_'+variant+'_p90'].median(),'ratio_p90_median':q['ratio_'+variant+'_p90'].median()};assert sum(r[k] for k in ['joint_count','concentration_only_count','nn_tail_only_count','neither_count'])==n;records.append(r)
regions=sorted(m[m.kind=='region'].unit.unique())
for kind,gg in z.groupby('kind'):
 for variant in ['fixed2002','coords2021','survivor_neighbors']:
  for tol in [0.,1e-9]:
   summary(gg,kind,variant,tol,'NONE')
   for reg in regions:summary(gg[gg.dominant_region.ne(reg)],kind,variant,tol,reg)
s=pd.DataFrame(records);s.to_csv(O/'sensitivity_table.csv',index=False)
base=s[(s.excluded_dominant_region=='NONE')&(s.nn_threshold_km==0)];primary=base[(base.kind=='grid50')&(base.variant=='fixed2002')].iloc[0];lo=s[(s.kind=='grid50')&(s.variant=='fixed2002')&(s.nn_threshold_km==0)&(s.excluded_dominant_region!='NONE')]
md='# C2: концентрация и изменение ближайшего соседства\n\nПротокол `descriptive_claims.md` опубликован координатором до этой проверки (c7b6770). Все исходные фиксированные разбиения сохранены; новые шкалы не подбирались.\n\n'
md+=f"Первичная совокупность: {int(primary.declined_supported_units)} убывающих ячеек50км с≥20 положительныхНП2002. Совместное увеличение доли фиксированнойtop10%группы иp90 индивидуальногоNNизменения: **{int(primary.joint_count)}/{int(primary.declined_supported_units)} = {100*primary.joint_fraction:.2f}%**. Только рост концентрации: {int(primary.concentration_only_count)}; только положительныйp90NN: {int(primary.nn_tail_only_count)}; ни одно: {int(primary.neither_count)}. Неположительная концентрация включает нулевое изменение.\n\n"
md+='## Все заданные масштабы и варианты\n\nЧисла относятся к соответствующим убывающим supportedединицам, поэтому знаменатели меняются со шкалой. `fixed2002` — обе сети в координатах2002; `coords2021` — соседи2021 в их координатах2021, исходные точки2002 неизменны; `survivor_neighbors` — сеть2021 только из положительных2002. Наблюдения с нулевой исходнойNNдистанцией сохраняются в километрах; отношения для нихundefined, безepsilon.\n\n'
md+='|Масштаб|Вариант|Убывающих единиц|Совместный рост|Доля,%|\n|---|---|---:|---:|---:|\n'
for r in base.itertuples():md+=f'|{r.kind}|{r.variant}|{r.declined_supported_units}|{r.joint_count}|{r.joint_fraction*100:.2f}|\n'
md+=f'\nПоследовательное исключение каждого из81 исходных регионов (ячейка относится кdominantregion2002 по числустрок) даёт первичную долюот **{100*lo.joint_fraction.min():.2f}%до{100*lo.joint_fraction.max():.2f}%**. Это диапазон чувствительности состава, **неCI**, не независимая репликация; округи не конструировались. Для ячеек смешанныхрегионов удаляется вся ячейка, а не часть её жителей. Доля смешанности сохранена в паспорте.\n\n'
changes=(d.change_fixed2002.to_numpy());md+=f'На уровне исходных133688положительныхточек индивидуальноеNNрасстояние увеличилось у{int((changes>1e-10).sum())}, уменьшилось у{int((changes<-1e-10).sum())}, неизменно в пределах1e-10км у{int((np.abs(changes)<=1e-10).sum())}. Нулевая национальнаямедиана/p90 не равна полной неизменности: меняется часть исходныхмест. Первичная мера — доля ячеек с положительным локальнымp90, а не национальныйp90.\n\n'
t=s[(s.excluded_dominant_region=='NONE')&(s.nn_threshold_km==1e-9)][['kind','variant','joint_count']].merge(base[['kind','variant','joint_count']],on=['kind','variant'],suffixes=('_tol','_exact'));md+=f'Порог1e-9км меняет jointcount в{int((t.joint_count_tol!=t.joint_count_exact).sum())} из15 комбинаций. Полные четверки, отношения и исключения: `sensitivity_table.csv`; значения каждой единицы: `c2_unit_sensitivities.csv`.\n\nВсе выводы описываютordinaryпанель, не всю территориюРоссии. Доказательство механизма, статистическаязначимость и интервалыне заявлены. Ошибки источников и границ не исчезают при точном пересчёте.\n'
(O/'c2_summary.md').write_text(md)
receipt={'script_sha256':sha(__file__),'inputs':inputs,'rows_units':len(z),'sensitivity_rows':len(s),'selfcheck_fixed_p90_maxdiff_km':diff,'python':platform.python_version(),'outputs':{p.name:sha(p) for p in [O/'c2_unit_sensitivities.csv',O/'sensitivity_table.csv',O/'c2_summary.md']}}
(O/'c2_receipt.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False));print(md,flush=True)
