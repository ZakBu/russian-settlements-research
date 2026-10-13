from pathlib import Path
import json,pandas as pd
from research_rebuild.mass_linkage.coverage import sha
from research_rebuild.mass_linkage.coordinate_ledger import norm
from research_rebuild.mass_linkage.modern_historical_point_candidates import compatible_type
w=Path('/workspace/settlements-work/coordinates');s=w/'modern_noncity_application_v2';out=w/'accepted_extension_noncity_v1';assert not out.exists()
r=json.loads((s/'receipt.json').read_text());p=pd.read_parquet(s/'staged_point_uses.parquet');l=pd.read_parquet(s/'candidate_ledger.parquet');c=pd.read_parquet(w/'modern_historical_noncity_v1/new_point_candidates.parquet').set_index('source_record_id');base=pd.read_parquet(w/'accepted_extension_v1/accepted_point_uses.parquet')
assert len(p)==13766 and p.target_source_record_id.is_unique and len(l)==13772
assert set(l.loc[l.candidate_status.eq('held'),'source_record_id'])==set(r['six_frozen_review_holds'])
assert sha(s/'staged_point_uses.parquet')==r['artifacts']['staged_point_uses']['sha256']
assert sha(s/'candidate_ledger.parquet')==r['artifacts']['candidate_ledger']['sha256']
rawpath=Path(r['inputs']['raw_2021']['path']);assert sha(rawpath)==r['inputs']['raw_2021']['sha256'];raw=pd.read_parquet(rawpath,columns=['object_level','oktmo','population','settlement_dadata','settlement_type_full_dadata','latitude_dadata','longitude_dadata'])
for row in p.itertuples(index=False):
 nr=int(row.target_source_record_id.rsplit(':',1)[1]);rr=raw.iloc[nr-1];cr=c.loc[row.target_source_record_id]
 assert (row.latitude,row.longitude)==(rr.latitude_dadata,rr.longitude_dadata)
 assert rr.object_level=='Населенный пункт' and rr.oktmo==cr.oktmo and rr.population==cr.population
 assert norm(rr.settlement_dadata)==norm(cr.settlement_name) and compatible_type(cr.settlement_type,rr.settlement_type_full_dadata)
 assert row.point_origin_file==str(rawpath) and row.point_origin_sha256==r['inputs']['raw_2021']['sha256']
 assert str(nr) in row.point_origin_locator and row.admission_allowed==False
 assert cr.provider_settlement_fias_duplicate_count==1 and cr.provider_general_fias_duplicate_count==1 and cr.provider_coordinate_duplicate_count==1
assert not set(p.target_source_record_id)&set(base.target_source_record_id)
review={'verdict':'APPROVE 13766 staged current-provider point uses under the frozen noncity rule and explicit addendum.','review_id':'modern_noncity_whole_application_root_review_20261003','application_receipt_sha256':sha(s/'receipt.json'),'staged_point_uses_sha256':sha(s/'staged_point_uses.parquet'),'candidate_ledger_sha256':sha(s/'candidate_ledger.parquet'),'whole_positive_raw_point_source_native_code_population_name_type_checks':13766,'held_exact_frozen_six_ids':True,'coordinate_rule_review_sha256':r['inputs']['review']['sha256'],'scientific_rule_addendum_sha256':r['inputs']['addendum']['sha256'],'review_script_sha256':sha(Path(__file__)),'limits':'Automatic current point-to-2021-source-row association only; neither historical census-date point nor official FIAS identity correctness nor boundary/population comparability is admitted.'}
p['coordinate_admission_status']='reviewed_extension_rule_accepted';p['coordinate_quality']='automatically_accepted_checked_rule';p['admission_allowed']=True;p['coordinate_application_review_sha256']=sha(s/'receipt.json');p['application_inference_kind']='current_representative_point_bound_to_2021_physical_source_row';p['direct_historical_coordinate_measurement']=False;p['population_scope_comparability_asserted']=False
out.mkdir();(out/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n');result=pd.concat([base,p],ignore_index=True);assert result.target_source_record_id.is_unique;path=out/'accepted_point_uses.parquet';result.to_parquet(path,index=False)
receipt={'status':'independently_checked_modern_noncity_application_accepted','rows':len(result),'new_accepted_points':len(p),'preserved_baseline_rows':len(base),'review_sha256':sha(out/'review.json'),'output':{'path':str(path),'sha256':sha(path)}};(out/'acceptance_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt))
