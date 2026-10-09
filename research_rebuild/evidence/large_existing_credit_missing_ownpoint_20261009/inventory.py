from pathlib import Path
import pandas as pd,csv,gzip,json,hashlib
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence');O=Path(__file__).parent;D=Path('/workspace/settlements-delivery/final-full-20261009')
m=pd.read_csv(O/'actual_final_credited_over1000_missing_State_ownpoint.csv',dtype=str,keep_default_na=False);ids=set(m.source_record_id)
j=pd.read_csv(D/'accepted_typed_joint_reporting_scope_spatial_associations.csv',dtype=str,keep_default_na=False)
m['explicit_joint_scope_association']=m.source_record_id.isin(set(j.source_record_id));m['literal_part_label']=m.settlement_name.str.contains('часть',case=False);m['audit_class']=m.apply(lambda r:'joint_or_numbered_part_exactpoint_UNKNOWN' if r.explicit_joint_scope_association or r.literal_part_label else 'whole_named_NP_ownpoint_REQUIRED',axis=1)
hits=[];inspected=[]
for p in E.glob('**/*'):
 if not p.is_file() or O in p.parents or not (p.name.endswith('.csv') or p.name.endswith('.csv.gz')):continue
 if not any(x in p.name for x in ['accepted_former_locality_own_points','accepted_qualified_physical_observations','accepted_own_point','existing_own_representative_points','accepted_point_use','qualified_scope_point_actions','raw2011_own_physical']):continue
 if p.stat().st_size>4_000_000:continue
 op=gzip.open if p.suffix=='.gz' else open
 with op(p,'rt',encoding='utf-8-sig',newline='') as f:
  rows=csv.DictReader(f);fields=rows.fieldnames or []
  if not any('source_record_id' in x for x in fields):continue
  inspected.append(str(p))
  for ix,r in enumerate(rows,2):
   matched=ids&{str(v) for k,v in r.items() if k and ('source_record_id' in k or k=='credited_source_uid')}
   if matched:
    for sid in matched:hits.append(dict(target_source_record_id=sid,evidence_file=str(p),evidence_row=ix,evidence_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),candidate_row_json=json.dumps(r,ensure_ascii=False)))
pd.DataFrame(hits).to_csv(O/'exact_native_UID_cached_ownpoint_claim_hits.csv',index=False)
m['exact_cached_claim_hits']=m.source_record_id.map(pd.Series([x['target_source_record_id'] for x in hits]).value_counts()).fillna(0).astype(int)
m.to_csv(O/'classified_missing_ownpoint_inventory.csv',index=False)
print('class',m.audit_class.value_counts().to_dict(),'hits',len(hits),'hitUIDs',len({x['target_source_record_id'] for x in hits}),'files',len(inspected))
(O/'inspected_point_file_inventory.json').write_text(json.dumps(inspected,indent=2))
