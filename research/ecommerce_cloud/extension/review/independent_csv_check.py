"""Independent, standard-library recalculation of published panel summaries."""
from pathlib import Path
import csv,json,statistics,collections
ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'work/sources/research/ecommerce_settlement_20261024/settlement_role_stage_20261024'
OUT=Path(__file__).resolve().parent

def read(p):
    with p.open() as f:return list(csv.DictReader(f))
def number(x):return float(x) if x else None
dem=read(BASE/'system/centre_system_demography.csv')
medium=[r for r in dem if r['medium_primary2002']=='True']
supported=[r for r in medium if r['demographic_comparison_supported']=='True']
panel=[r for r in read(BASE/'bdmo/singleton/internal_centre_district_common_panels2022_2024.csv') if r['medium_primary2002']=='True']
res={'scope':'Independent recomputation from saved CSV; not raw acquisition audit or causal identification','demography':{'medium_n':len(medium),'supported_n':len(supported),'median_change_pct':statistics.median(number(r['centre_change2002_2021_pct']) for r in supported),'median_share_change_pp':statistics.median(number(r['centre_population_share_change_pp']) for r in supported),'share_gain_ge1pp_n':sum(number(r['centre_population_share_change_pp'])>=1 for r in supported),'share_loss_le_minus1pp_n':sum(number(r['centre_population_share_change_pp'])<=-1 for r in supported)},'trade':[],'failures':[]}
assert len(medium)==1273 and len(supported)==1195
for cat in sorted({r['category'] for r in panel}):
    g=[r for r in panel if r['category']==cat]
    for r in g:
        for yr in [2022,2023,2024]:
            calc=100*number(r[f'centre_shops_{yr}'])/number(r[f'district_shops_{yr}'])
            if abs(calc-number(r[f'centre_share_pct_{yr}']))>1e-8:res['failures'].append({'id':r['source_record_id_2021'],'year':yr,'issue':'share formula'})
        if abs(number(r['centre_share_pct_2024'])-number(r['centre_share_pct_2022'])-number(r['centre_share_change2022_2024_pp']))>1e-8:res['failures'].append({'id':r['source_record_id_2021'],'issue':'share difference'})
    ids={r['source_record_id_2021'] for r in g}
    selected=[r for r in medium if r['source_record_id_2021'] in ids]
    absent=[r for r in medium if r['source_record_id_2021'] not in ids]
    res['trade'].append({'category':cat,'n':len(g),'share_loss_ge1pp_n':sum(number(r['centre_share_change2022_2024_pp'])<=-1 for r in g),'share_gain_ge1pp_n':sum(number(r['centre_share_change2022_2024_pp'])>=1 for r in g),'stock_decline_n':sum(number(r['centre_stock_change2022_2024'])<0 for r in g),'stock_growth_n':sum(number(r['centre_stock_change2022_2024'])>0 for r in g),'median_share_change_pp':statistics.median(number(r['centre_share_change2022_2024_pp']) for r in g),'selected_regions_n':len({r['region_2021'] for r in selected}),'all_medium_regions_n':len({r['region_2021'] for r in medium}),'selected_median_population2002':statistics.median(number(r['population_2002']) for r in selected),'not_selected_median_population2002':statistics.median(number(r['population_2002']) for r in absent),'selected_region_counts':dict(collections.Counter(r['region_2021'] for r in selected))})
(OUT/'independent_csv_results.json').write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(res,ensure_ascii=False,indent=2))
