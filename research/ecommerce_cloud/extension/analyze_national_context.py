"""National demographic and spatial sensitivity; no platform treatment assigned.

Run with the portable requirements, after scripts/research_data.py fetch --profile core.
The fixed 2021 cohort and points are used in both census denominators. Circular
neighbourhoods overlap and are NOT observed service areas or independent markets.
"""
from pathlib import Path
import hashlib
import json
import platform
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT / 'work/sources/research/ecommerce_settlement_20261024'
OUT = ROOT / 'work/ecommerce_cloud_extension/national'
OUT.mkdir(parents=True, exist_ok=True)
KEY = 'source_record_id_2021'
paths = [ROOT/'data/population/settlements_census_long.parquet',
         ROOT/'data/population/settlements_census_wide.parquet',
         BASE/'settlement_role_stage_20261024/system/centre_system_demography.csv',
         BASE/'settlement_role_stage_20261024/bdmo/singleton/internal_centre_district_common_panels2022_2024.csv',
         BASE/'execution_20261024/geography/by_region.csv']
long = pd.read_parquet(paths[0])
s = long[long.census_year.eq(2021) & long.population_scope.eq('settlement') &
         long.is_additive_settlement_record.eq(True) & long.working_credit_present.eq(True) &
         long.effective_population.notna()].copy()
assert len(s) == 144151 and s.source_record_id.is_unique
wide = pd.read_parquet(paths[1])
wide = wide[wide[KEY].notna()].copy()
d = s.rename(columns={'source_record_id':KEY}).merge(
    wide[[KEY,'effective_population_2002','population_value_quality_2002']], on=KEY, validate='1:1')
d['strict_pair'] = d.population_value_quality.eq('direct_published_census_value') & \
    d.population_value_quality_2002.eq('direct_published_census_value') & d.effective_population_2002.notna()
d = d[d.accepted_latitude.notna() & d.accepted_longitude.notna()].set_index(KEY)
assert len(d) == 144149
c = pd.read_csv(paths[2]).set_index(KEY)
t = pd.read_csv(paths[3])
medium = c[c.medium_primary2002].copy()
assert len(medium) == 1273
valid_admin = medium[medium.demographic_comparison_supported].copy()

def summary(g):
    return dict(centres_n=len(g), centre_decline_n=int(g.centre_change2002_2021_pct.lt(0).sum()),
        share_gain_ge1pp_n=int(g.centre_population_share_change_pp.ge(1).sum()),
        share_loss_ge1pp_n=int(g.centre_population_share_change_pp.le(-1).sum()),
        centre_decline_and_share_gain_n=int((g.centre_change2002_2021_pct.lt(0)&g.centre_population_share_change_pp.ge(1)).sum()),
        median_centre_change_pct=g.centre_change2002_2021_pct.median(),
        median_surroundings_change_pct=g.other_members_change2002_2021_pct.median(),
        median_share_change_pp=g.centre_population_share_change_pp.median())

region = pd.DataFrame([dict(region_2021=k, **summary(g)) for k,g in valid_admin.groupby('region_2021')])
region.to_csv(HERE/'demographic_regions.csv', index=False)
size = pd.DataFrame([dict(size2002=k, **summary(g)) for k,g in valid_admin.groupby(
    pd.cut(valid_admin.population_2002,[4999,9999,19999,49999],labels=['5000–9999','10000–19999','20000–49999']),observed=True)])
size.to_csv(HERE/'demographic_size.csv', index=False)

# Circular-neighbourhood sensitivity. Chord query is exactly equivalent to the
# great-circle radius on a sphere of mean Earth radius 6371.0088 km.
lat=np.radians(d.accepted_latitude.to_numpy())
lon=np.radians(d.accepted_longitude.to_numpy())
xyz=np.column_stack([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])
tree=cKDTree(xyz)
index={k:i for i,k in enumerate(d.index)}
p02=d.effective_population_2002.to_numpy()
p21=d.effective_population.to_numpy()
strict=d.strict_pair.to_numpy()
rows=[]
for cid, centre in medium.iterrows():
    if cid not in index or not d.loc[cid,'strict_pair'] or centre.population_2002<=0:
        continue
    ci=index[cid]
    for radius in [10,20,40,80]:
        ii=np.array(tree.query_ball_point(xyz[ci],2*np.sin(radius/(2*6371.0088))),dtype=int)
        jj=ii[strict[ii]]
        total21=p21[ii].sum()
        coverage=p21[jj].sum()/total21 if total21>0 else np.nan
        if len(jj)<2 or coverage<.90 or p02[jj].sum()<=0 or p21[jj].sum()<=0:
            continue
        delta=100*(p21[ci]/p21[jj].sum()-p02[ci]/p02[jj].sum())
        peripheral02=p02[jj].sum()-p02[ci]
        peripheral21=p21[jj].sum()-p21[ci]
        log_relative_growth=(np.log(p21[ci]/peripheral21)-np.log(p02[ci]/peripheral02)) \
            if min(p21[ci],p02[ci],peripheral21,peripheral02)>0 else np.nan
        rows.append({KEY:cid,'radius_km':radius,'members_n':len(ii),'common_members_n':len(jj),
            'common_population2021_coverage':coverage,'share_change_pp':delta,
            'admin_supported':bool(centre.demographic_comparison_supported),
            'admin_share_change_pp':centre.centre_population_share_change_pp,
            'log_centre_periphery_growth_ratio':log_relative_growth,
            'centre_change_pct':centre.centre_change2002_2021_pct})
r=pd.DataFrame(rows)
r.to_parquet(OUT/'circular_neighbourhoods.parquet',index=False)
ss=[]
for radius,g in r.groupby('radius_km'):
    common=g[g.admin_supported]
    sign=((common.share_change_pp>=1)&(common.admin_share_change_pp>=1)) | \
         ((common.share_change_pp<=-1)&(common.admin_share_change_pp<=-1)) | \
         ((common.share_change_pp.abs()<1)&(common.admin_share_change_pp.abs()<1))
    ss.append(dict(radius_km=int(radius),centres_n=len(g),median_share_change_pp=g.share_change_pp.median(),
        positive_share_change_n=int(g.share_change_pp.gt(1e-9).sum()),
        share_gain_ge1pp_n=int(g.share_change_pp.ge(1).sum()),share_loss_ge1pp_n=int(g.share_change_pp.le(-1).sum()),
        common_with_admin_n=len(common),three_way_category_agreement_n=int(sign.sum()),
        sign_agreement_n=int((np.sign(common.share_change_pp.where(common.share_change_pp.abs()>1e-9,0)) ==
            np.sign(common.admin_share_change_pp.where(common.admin_share_change_pp.abs()>1e-9,0))).sum()),
        log_ratio_observed_n=int(g.log_centre_periphery_growth_ratio.notna().sum()),
        median_log_centre_periphery_growth_ratio=g.log_centre_periphery_growth_ratio.median(),
        common_admin_median_change_pp=common.admin_share_change_pp.median(),
        common_circle_median_change_pp=common.share_change_pp.median()))
pd.DataFrame(ss).to_csv(HERE/'spatial_sensitivity.csv',index=False)

# Plot actual locations, not fictitious market boundaries. Spherical Lambert
# azimuthal equal-area centred on Russia, with radius in km.
def project(latitude,longitude):
    la=np.radians(np.asarray(latitude,dtype=float));lo=np.radians(np.asarray(longitude,dtype=float))
    la0=np.radians(62);lo0=np.radians(100)
    k=np.sqrt(2/(1+np.sin(la0)*np.sin(la)+np.cos(la0)*np.cos(la)*np.cos(lo-lo0)))
    return 6371.0088*k*np.cos(la)*np.sin(lo-lo0),6371.0088*k*(np.cos(la0)*np.sin(la)-np.sin(la0)*np.cos(la)*np.cos(lo-lo0))
plt.rcParams.update({'font.family':'DejaVu Sans','axes.spines.top':False,'axes.spines.right':False})
xy=project(d.accepted_latitude,d.accepted_longitude)
mc=medium.join(d[['accepted_latitude','accepted_longitude']],how='left')
trade_ids=set(t[t.category.eq('Магазины') & t.medium_primary2002][KEY])
fig,ax=plt.subplots(figsize=(13,7))
ax.scatter(*xy,s=.10,c='#bcc4cc',alpha=.35,rasterized=True)
for observed,color,label,sz in [(False,'#b5b8bc','Нет пригодной торговой панели',9),(True,'#2166a7','Есть условная панель магазинов',20)]:
    h=mc[mc.index.isin(trade_ids)==observed]
    ax.scatter(*project(h.accepted_latitude,h.accepted_longitude),s=sz,c=color,label=f'{label}: {len(h)} центров',alpha=.85)
ax.set_aspect('equal');ax.axis('off');ax.legend(loc='upper left',bbox_to_anchor=(0,-.01),frameon=False,fontsize=10)
ax.set_title('Торговая панель покрывает 174 из 1 273 средних центров',loc='left',fontsize=15)
fig.subplots_adjust(bottom=.20)
fig.text(.06,.015,'Точки поселений принятой основы 2021; 81 регион, федеральные города отдельно. Границы не показаны.\n'
    'Условная доля муниципалитета центра в районе, IV кварталы 2022–2024. Это карта отбора, не карта эффекта WB/Ozon.',fontsize=9)
fig.savefig(OUT/'trade_panel_coverage.png',dpi=170,bbox_inches='tight');plt.close(fig)

fig,ax=plt.subplots(figsize=(13,7))
ax.scatter(*xy,s=.10,c='#c9cdd2',alpha=.3,rasterized=True)
for mask,color,label in [(mc.demographic_comparison_supported & mc.centre_population_share_change_pp.ge(1),'#2166a7','Доля выросла минимум на 1 п.п.'),
                        (mc.demographic_comparison_supported & mc.centre_population_share_change_pp.le(-1),'#be572d','Доля снизилась минимум на 1 п.п.'),
                        (mc.demographic_comparison_supported & mc.centre_population_share_change_pp.abs().lt(1),'#888888','Изменение менее 1 п.п.'),
                        (~mc.demographic_comparison_supported,'#dadada','Недостаточно общей переписной основы')]:
    h=mc[mask];ax.scatter(*project(h.accepted_latitude,h.accepted_longitude),s=13,c=color,label=f'{label}: {len(h)}',alpha=.9)
ax.set_aspect('equal');ax.axis('off');ax.legend(loc='upper left',bbox_to_anchor=(0,-.01),frameon=False,fontsize=9,ncol=2)
ax.set_title('Демографическая концентрация центра и периферийное сжатие',loc='left',fontsize=15)
fig.subplots_adjust(bottom=.20)
fig.text(.06,.015,'Изменение доли населения центра в фиксированном административном контексте 2020, 2002–2021.\n'
    'Средние центры: 5–50 тыс. жителей в 2002. Не чистый доплатформенный период; не оценка влияния маркетплейсов.',fontsize=9)
fig.savefig(OUT/'demographic_concentration.png',dpi=170,bbox_inches='tight');plt.close(fig)

metadata=dict(scope='144151 credited physical census2021 settlements, 81 ordinary regions; two lack coordinates',
    python=platform.python_version(),medium_centres_n=len(medium),demographic_supported_n=len(valid_admin),
    overall=summary(valid_admin),circular_sensitivity=ss,
    identification='Descriptive sensitivity only; overlapping synthetic circles, no observed travel or platform effects.',
    inputs=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths])
(HERE/'national_context_summary.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(metadata['overall'],ensure_ascii=False,indent=2))
print(pd.DataFrame(ss).to_string(index=False))
