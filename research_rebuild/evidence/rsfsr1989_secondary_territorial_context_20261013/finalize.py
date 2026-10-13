from pathlib import Path
import json,shutil,hashlib,pyarrow.parquet as pq,pyarrow as pa,collections
H=Path(__file__).resolve().parent;O=Path('/workspace/scratch/rsfsr1989_secondary_territorial_context_20261013');B=Path('/workspace/scratch/rsfsr1989_secondary_okato_extension_20261013');candidate=pq.read_table(O/'secondary_population_1989_long.parquet');base=pq.read_table(B/'secondary_population_1989_long.parquet');keys={r['statement_uri_raw'].casefold() for r in base.to_pylist()};new=[r for r in candidate.to_pylist() if r['statement_uri_raw'].casefold() not in keys];audit=json.loads((H/'large_subject_scope_audit.json').read_text());ad={r['qid']:r for r in audit['audit']};municipal={'Q2661988','Q634099','Q13626398'};held=[];accepted=[]
for r in new:
 a=ad.get(r['wikidata_qid']);why=[]
 if not a or not a['GUID_matched']:why.append('full_subject_type_or_statement_unverified')
 if a and municipal&set(a['P31_ids']):why.append('municipal_or_mixed_subject_object_level')
 if a and (a.get('P518_present') or a.get('unit')!='1'):why.append('subset_or_nonunit_quantity')
 if why:held.append({'candidate':r,'full_item_audit':a,'hold_reasons':why})
 else:accepted.append(r)
assert not accepted
for name in ['secondary_population_1989_long.parquet','current_own_NP_bindings.parquet']:
 shutil.copy2(O/name,O/('candidate_'+name));shutil.copy2(B/name,O/name);shutil.copy2(O/name,H/name)
pq.write_table(candidate.slice(0,0),O/'accepted_territorial_context_delta.parquet',compression='zstd');shutil.copy2(O/'accepted_territorial_context_delta.parquet',H/'accepted_territorial_context_delta.parquet');(H/'held_new_candidates.json').write_text(json.dumps(held,ensure_ascii=False,indent=2)+'\n')
receipt=json.loads((H/'receipt.json').read_text());receipt['candidate_extraction_metrics']={k:receipt[k] for k in ['current_bound_QIDs','secondary1989_rows_GUID_deduplicated','own1989_NP_or_explicit_city_subjects','source_bounded_population_sum_min','source_bounded_population_sum_max']};oldreceipt=json.loads((H.parent/'rsfsr1989_secondary_okato_extension_20261013/receipt.json').read_text())
for k in ['current_bound_QIDs','secondary1989_rows_GUID_deduplicated','own1989_NP_or_explicit_city_subjects','source_bounded_population_sum_min','source_bounded_population_sum_max','single_value_subjects','conflicting_subjects','secondary_disjoint_min','secondary_disjoint_max']:receipt[k]=oldreceipt[k]
receipt['new_route_disposition']={'candidate_GUIDs':len(new),'accepted_GUIDs':0,'held_GUIDs':len(held),'empirical_API_type_block':'three municipal-only and one mixed municipal/physical type','final_full_replacement_identical_to_frozen_OKATO_input':True};receipt['outputs']={p.name:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'candidate_only':p.name.startswith('candidate_')} for p in O.glob('*.parquet')};receipt['new_downloads_used_for_small_scope_audit_only']=True;(H/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(receipt['new_route_disposition'])
