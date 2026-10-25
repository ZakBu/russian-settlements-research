"""Make the inherited territorial denominator and separate evidence explicit."""
from pathlib import Path
import json,hashlib
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
BASE=ROOT/'work/sources/research/ecommerce_settlement_20261024/national'
p=ROOT/'data/population/settlements_census_long.parquet'
long=pd.read_parquet(p);source=long[long.census_year.eq(2021)]
target=pd.read_parquet(BASE/'national_target_source2021.parquet')
inventory=pd.read_parquet(BASE/'all_physical_source2021_inventory.parquet')
oz=pd.read_parquet(BASE/'ozon_counts_source2021_experimental.parquet')
missing=sorted(set(source.region_norm)-set(target.region_2021))
rows=[]
for name in missing:
    s=source[source.region_norm.eq(name)]
    r=dict(source_region=name,source_records_n=len(s),source_effective_population2021=s.effective_population.sum(),
        source_scopes=s.population_scope.value_counts(dropna=False).to_dict(),
        working_credited_records_n=int(s.working_credit_present.eq(True).sum()))
    rows.append(r)
q=inventory[inventory.region_2021.eq('крым')]
assert len(q)==1019 and q.WB_evidence_status.eq('unknown_no_commerce_bridge').all()
z=oz[oz.region_2021.eq('крым')]
assert set(z.source_record_id_2021)==set(q.source_record_id_2021)
additional=[]
for km in [1,5,10]:
    positive=z[f'ozon_pickup_inferred_accepted_{km}km_count'].gt(0)
    additional.append(dict(source_region='крым',identity_radius_km=km,source_records_n=len(z),
        source_population2021=z.population_2021.sum(),ozon_positive_np_n=int(positive.sum()),
        population2021_in_positive_np=z.loc[positive,'population_2021'].sum(),
        WB_unknown_n=len(q),included_in_main_denominator=False))
pd.DataFrame(additional).to_csv(HERE/'additional_region_positive_evidence.csv',index=False)
result=dict(source_regions_n=int(source.region_norm.nunique()),target_regions_n=int(target.region_2021.nunique()),
    excluded_source_regions=rows,additional_positive_evidence=additional,
    interpretation='Inherited census-source territorial classification, not a statement about current borders. Auxiliary noncredited inventory and federal-city object labels are separate; never added to the 144151 target.',
    input_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
centres=pd.read_csv(BASE.parent/'settlement_role_stage_20261024/system/centre_system_demography.csv')
ids=centres.loc[centres.medium_primary2002,'source_record_id_2021']
comparison=pd.read_parquet(BASE/'ozon_WB_comparison_main_target_experimental.parquet').set_index('source_record_id_2021').loc[ids]
positive=comparison.WB_evidence_status.eq('positive')|comparison.ozon_pickup_inferred_accepted_5km_count.gt(0)
result['medium_current_positive']={'centres_n':len(comparison),'positive_n':int(positive.sum()),'no_positive_evidence_n':int((~positive).sum()),'interpretation':'No positive evidence is not proven absence; different network dates and source completeness retained.'}
assert len(comparison)==1273 and positive.sum()==1248
(HERE/'territorial_scope.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
