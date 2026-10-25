"""Check final territorial denominators and medium-centre positive evidence."""
from pathlib import Path
import json
import pandas as pd
R=Path(__file__).resolve().parents[4];B=R/'work/sources/research/ecommerce_settlement_20261024';O=Path(__file__).resolve().parent
s=pd.read_parquet(R/'data/population/settlements_census_long.parquet',columns=['census_year','region_norm','population_scope','working_credit_present','effective_population']);s=s[s.census_year==2021]
t=pd.read_parquet(B/'national/national_target_source2021.parquet',columns=['source_record_id_2021','region_2021'])
excluded=set(s.region_norm.unique())-set(t.region_2021.unique());assert excluded=={'москва','санкт петербург','севастополь','крым'}
q=s[s.region_norm=='крым'];assert len(q)==1019 and q.population_scope.eq('settlement').all()and not q.working_credit_present.eq(True).any()
inv=pd.read_parquet(B/'national/all_physical_source2021_inventory.parquet',columns=['source_record_id_2021','region_2021','WB_evidence_status']);inv=inv[inv.region_2021=='крым'];assert len(inv)==1019 and inv.WB_evidence_status.eq('unknown_no_commerce_bridge').all()
z=pd.read_parquet(B/'national/ozon_counts_source2021_experimental.parquet');z=z[z.region_2021=='крым'];assert set(z.source_record_id_2021)==set(inv.source_record_id_2021)
pos=z.ozon_pickup_inferred_accepted_5km_count>0
c=pd.read_csv(B/'settlement_role_stage_20261024/system/centre_system_demography.csv');ids=set(c.loc[c.medium_primary2002,'source_record_id_2021'])
n=pd.read_parquet(B/'national/ozon_WB_comparison_main_target_experimental.parquet');n=n[n.source_record_id_2021.isin(ids)];assert len(n)==len(ids)==1273
positive=(n.WB_evidence_status=='positive')|(n.ozon_pickup_inferred_accepted_5km_count>0)
res={'source_regions_n':s.region_norm.nunique(),'target_regions_n':t.region_2021.nunique(),'excluded_labels':sorted(excluded),'crimea_inventory_records':len(z),'crimea_population2021':z.population_2021.sum(),'crimea_ozon_positive_5km':int(pos.sum()),'crimea_population2021_in_positive_np':z.loc[pos,'population_2021'].sum(),'crimea_wb_unknown':len(inv),'medium_centres':len(n),'medium_positive_either':int(positive.sum()),'medium_positive_pct':100*positive.mean(),'medium_no_positive_evidence':int((~positive).sum()),'scope':'Source territorial classification, separate auxiliary inventory; not contemporary border adjudication, market completeness or cause.'}
assert res['crimea_ozon_positive_5km']==331 and res['medium_positive_either']==1248
(O/'independent_scope_results.json').write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n');print(json.dumps(res,ensure_ascii=False,indent=2))
