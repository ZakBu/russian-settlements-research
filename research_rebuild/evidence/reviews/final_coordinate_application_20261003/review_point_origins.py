from pathlib import Path
import json,pandas as pd
from research_rebuild.mass_linkage.coverage import sha
w=Path('/workspace/settlements-work/coordinates');a=w/'extension_application_v2';n=w/'normalized_extension_v2';r=w/'extension_application_review_v1';original=pd.read_parquet(a/'staged_proposed_point_uses.parquet');normalized=pd.read_parquet(n/'normalized_point_uses.parquet');receipt=json.loads((n/'receipt.json').read_text());review=json.loads((r/'review.json').read_text())
assert review['reviewed_counts']['new_staged_targets']==193045
assert sha(a/'manifest.json')==review['application_manifest']['sha256']
assert sha(n/'normalized_point_uses.parquet')==receipt['output']['sha256']
assert normalized[original.columns].equals(original)
assert len(normalized)==290346 and normalized.target_source_record_id.is_unique
assets=normalized.loc[normalized.point_origin_file.fillna('').ne(''),['point_origin_file','point_origin_sha256']].drop_duplicates()
for f,h in assets.itertuples(index=False,name=None):assert sha(Path(f))==h
frozen=normalized[normalized.point_origin_file.fillna('').eq('')];assert len(frozen)==81 and frozen.point_origin_kind.eq('reviewed_frozen_assertion').all()
for f,h in frozen[['point_claim_artifact_file','point_claim_artifact_sha256']].drop_duplicates().itertuples(index=False,name=None):assert sha(Path(f))==h
assert normalized.point_origin_locator.notna().all()
modern=normalized[normalized.target_year.eq(2021)].set_index('target_source_record_id');retro=normalized[normalized.coordinate_application_family.eq('R_modern_accepted_point_retrospective_continuity')]
assert len(retro)==84035
for row in retro.itertuples(index=False):
 c=modern.loc[row.inference_modern_point_use_target_source_record_id]
 assert (row.latitude,row.longitude)==(c.latitude,c.longitude)
 assert (row.point_origin_file,row.point_origin_sha256)==(c.point_origin_file,c.point_origin_sha256)
 assert row.point_origin_locator=='carrier_target_source_record_id='+row.inference_modern_point_use_target_source_record_id+';'+c.point_origin_locator
add={'review_id':'coordinate_extension_origin_condition_closed_root_review_20261003_v2','verdict':'APPROVE the 193045 new point uses under the independently reviewed application; canonical source condition is now closed.','approved_new_point_uses':193045,'normalized_point_uses_sha256':sha(n/'normalized_point_uses.parquet'),'application_manifest_sha256':sha(a/'manifest.json'),'prior_independent_application_review_sha256':sha(r/'review.json'),'origin_receipt_sha256':sha(n/'receipt.json'),'review_script_sha256':sha(Path(__file__)),'correction':'Prior root addendum retrospective-family selector was empty; v2 asserts cohort size 84035 and actually verifies all carriers. Prior files preserved. Scientific points unchanged.', 'independent_checks':{'all_original_scientific_columns_unchanged':True,'all_distinct_nonempty_canonical_origin_files_rehashed':len(assets),'frozen81_original_point_source_unknown_assertion_csv_rehashed':True,'all_84035_retrospective_carriers_exact_point_and_origin_match':True,'raw_point_verification_receipt':receipt['source_rows_verified'],'new_boundary_or_population_admissions':0},'limits':'Current/2011 representative-point association and explicitly stated spatial continuity only; neither exact census-date measurement nor boundary equivalence nor provider official-ID correctness is admitted. Fixed samples do not estimate national precision.'}
(r/'origin_acceptance_addendum_v2.json').write_text(json.dumps(add,ensure_ascii=False,indent=2)+'\n');print(json.dumps(add['independent_checks']))
