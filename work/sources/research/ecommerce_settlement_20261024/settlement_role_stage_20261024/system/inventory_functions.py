"""Conservative bridge of existing dated functional witnesses; no centrality index."""
from pathlib import Path
import json
import pandas as pd

OUT=Path(__file__).resolve().parent
BASE=OUT.parent.parent
OLD=BASE.parent/'sgrt_word_completion_20261021/model_inputs_cycle05/relinked_v4'
d=pd.read_parquet(BASE/'national/national_target_source2021.parquet')
s=pd.read_csv(OUT/'centre_system_demography.csv')
key='source_record_id_2021'
selected=d.merge(s[[key,'medium_primary2002']],on=key,validate='one_to_one')
assert selected.legacy_commerce_id_bridge_only.dropna().is_unique
functions={
    'medical':{'hospital_name_witness':'medical_osm_baseline_central_district_hospital_name_assertion_count',
               'healthcare_witness':'medical_osm_baseline_healthcare_sites_count'},
    'education':{'school_witness':'education_osm2021_school_baseline_count',
                 'college_witness':'education_osm2021_college_baseline_count'},
    'commerce':{'bank_witness':'services_osm2021_bank_baseline_count',
                'post_office_witness':'services_osm2021_post_office_baseline_count',
                'administration_witness':'services_osm2021_administration_baseline_count'},
}
receipt=[]
for domain,mapping in functions.items():
    old=pd.read_parquet(OLD/domain/'settlement_features_full_axis.parquet')
    assert old.id.is_unique
    joined=selected.merge(old[['id','name','type','region']+list(mapping.values())],
        left_on='legacy_commerce_id_bridge_only',right_on='id',how='left',validate='many_to_one')
    compatible=(joined.source_metadata_agreement.eq(True)&joined['id'].notna()&
                joined.name_2021.eq(joined['name'])&joined.type_2021.eq(joined['type'])&
                joined.region_2021.eq(joined['region'])&joined.accepted_vs_legacy_point_distance_km.le(1))
    selected[domain+'_bridge_status2021']='unknown_or_metadata_or_point_mismatch'
    selected.loc[compatible,domain+'_bridge_status2021']='exact_accepted_source_bridge_name_type_region_point_le1km'
    for name,column in mapping.items():
        selected[name+'_count2021']=joined[column].where(compatible)
    receipt.append({'domain':domain,'centres2020_n':len(selected),
                    'accepted_bridge_centres_n':int(compatible.sum()),
                    'medium2002_accepted_bridge_n':int((compatible&selected.medium_primary2002).sum()),
                    'medium2002_positive_witnesses':{
                        name:int((selected.medium_primary2002&selected[name+'_count2021'].gt(0)).sum())
                        for name in mapping}})
columns=[key,'name_2021','type_2021','region_2021','medium_primary2002']+[
    c for c in selected if c.endswith('_count2021') or c.endswith('_bridge_status2021')]
selected[columns].to_csv(OUT/'centre_functions2021_positive_witnesses.csv',index=False)
report={'status':'PASS','rows':len(selected),'domains':receipt,
        'interpretation':'dated2021 OSM positive map witnesses on legacy axis; bridge has exact accepted source ID, name/type/region and <=1km point agreement; zero does not establish function absence; no normalized centrality index or customer catchment',
        'temporal_limit':'No corresponding local2026 functional files or original PBF timestamp receipts found; README descriptions alone not promoted to usable repeated sources.'}
(OUT/'function_bridge_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False,indent=2))
