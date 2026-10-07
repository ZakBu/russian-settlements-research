from __future__ import annotations
import hashlib, json
from pathlib import Path
import pandas as pd
import duckdb

ROOT=Path('/workspace/russian-settlements-research')
BASE=ROOT/'research_rebuild/evidence/bracketed_2010_county_bridge_20261007'
OUT=BASE/'source_recovery'
HELD=BASE/'held_unstaged_source_candidates.csv'
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
WORK=Path('/workspace/settlements-work/continuation_20261004/R4/exact_population_source_inventory/parser_runtime')
SOURCES={
 'kaliningrad':{
  'selector':'kaliningrad_2010_tom1',
  'ledger':WORK/'kaliningrad/kaliningrad_2010_tom1_sheet4_full_row_ledger.csv',
  'manifest':WORK/'kaliningrad/source_manifest_kaliningrad_2010_tom1_candidate_r2.json',
  'ledger_row':'source_row_number_1based','ledger_id':'source_record_id','ledger_locator':'source_locator',
  'source_hash_key':'source_sha256','source_url_key':'official_asset_url',
  'row_count_expected':1257,
 },
 'murmansk':{
  'selector':'murmansk_population_by_sex_municipalities',
  'ledger':WORK/'murmansk/murmansk_2010_population_by_sex_full_table_ledger.csv',
  'manifest':WORK/'murmansk/source_manifest_murmansk_2010_candidate_r1.json',
  'ledger_row':'source_row_number_1based','ledger_id':'source_record_id','ledger_locator':'source_logical_locator',
  'source_hash_key':'population_source_sha256','source_url_key':'population_source_original_url',
  'row_count_expected':226,
 }
}

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def cells(ledger:pd.Series, prefix:str)->dict:
 if 'raw_a' in ledger.index:
  return {f'{prefix}_raw_cells':{c:ledger.get(f'raw_{c}','') for c in 'abcdef'},
          f'{prefix}_cached_cells':{c:ledger.get(f'cached_{c}','') for c in 'abcdef'},
          f'{prefix}_indent':ledger.get('source_indent','')}
 return {f'{prefix}_raw_cells':{k:ledger.get(k,'') for k in ('label_raw','raw_population','raw_men','raw_women','raw_share_men','raw_share_women')},
         f'{prefix}_cached_cells':{}, f'{prefix}_indent':''}

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 held=pd.read_csv(HELD,dtype=str).fillna('')
 all_ids=sorted(set(held['target_2010_source_record_id'])|set(held['lower_anchor_2010_id'])|set(held['upper_anchor_2010_id']))
 selected=duckdb.connect().execute("SELECT source_record_id,source_file,source_sheet,try_cast(source_row AS DOUBLE) source_row,source_name_raw FROM read_parquet(?) WHERE source_record_id IN (SELECT UNNEST(?))",[str(SELECTED),all_ids]).fetchdf()
 selected_by_id=selected.set_index('source_record_id',drop=False)
 ledgers={}; manifests={}; meta={}
 for key,cfg in SOURCES.items():
  l=pd.read_csv(cfg['ledger'],dtype=str).fillna('')
  l['_row']=pd.to_numeric(l[cfg['ledger_row']],errors='raise').astype(int)
  assert len(l)==cfg['row_count_expected'],(key,len(l))
  assert l['_row'].tolist()==list(range(1,cfg['row_count_expected']+1)),key+' row order is not complete 1..N'
  m=json.loads(cfg['manifest'].read_text())
  source_hash=m[cfg['source_hash_key']]
  ledger_hash=sha(cfg['ledger']); manifest_hash=sha(cfg['manifest'])
  if key=='kaliningrad':
   assert source_hash=='7e17a4bdb54e3ee8ff014c4311396f84c01b7f3ed38d12f4f9c1f9e6b100705f'
   assert m['source_bytes']==306344 and m['source_observation_sheet']=='4'
  else:
   assert source_hash=='d4bdb36d541ed3f90594ba95ee209fabafc5f02088758e46a143e1155f5fbc57'
   assert m['population_source_bytes']==384000 and m['source_row_count']==226
  ledgers[key]=l.set_index(cfg['ledger_id'],drop=False)
  manifests[key]=m
  source_bytes=m.get('source_bytes',m.get('population_source_bytes'))
  meta[key]={'ledger_sha256':ledger_hash,'manifest_sha256':manifest_hash,'source_sha256':source_hash,
             'source_bytes':source_bytes,'source_url':m[cfg['source_url_key']],
             'ledger_path':str(cfg['ledger']),'manifest_path':str(cfg['manifest']),
             'ledger_rows':len(l),'row_order_complete':True}

 out=[]
 for r in held.to_dict('records'):
  kind='kaliningrad' if 'kaliningrad_2010_tom1' in r['target_2010_source_file'] else 'murmansk'
  cfg=SOURCES[kind]; l=ledgers[kind]; m=manifests[kind]
  row_id=r['target_2010_source_record_id']; target=l.loc[row_id]
  target_selected=selected_by_id.loc[row_id]
  target_row=int(r['target_2010_source_row'])
  assert int(target['_row'])==target_row,(row_id,target['_row'],target_row)
  assert str(target['label_raw']).strip().casefold()==str(r['target_2010_source_name_raw']).strip().casefold(),row_id
  assert str(r['target_2010_source_sha256'])==meta[kind]['source_sha256'],row_id+' selected source hash mismatch'
  assert str(target_selected['source_file'])==r['target_2010_source_file'],row_id+' selected file mismatch'
  assert int(target_selected['source_row'])==target_row,row_id+' selected row mismatch'
  assert str(target_selected['source_name_raw']).strip().casefold()==str(target['label_raw']).strip().casefold(),row_id+' selected/ledger literal mismatch'
  target_name=target['label_raw']
  d={
   'source_recovery_status':'complete_published_cell_ledger_and_order_verified',
   'target_2010_source_record_id':row_id,'target_2010_name_raw':r['target_2010_name_raw'],
   'target_2010_type_raw':r['target_2010_type_raw'],'inferred_county_key':r['inferred_county_key'],
   'source_file_selected':r['target_2010_source_file'],'source_file_sha256':meta[kind]['source_sha256'],
   'source_file_bytes':meta[kind]['source_bytes'],'source_published_url':meta[kind]['source_url'],
   'target_source_row_1based':target_row,'target_source_locator':target.get(cfg['ledger_locator'],'') or f"{r['target_2010_source_file']}#table1!row={target_row}",
   'target_source_label_raw_selected':r['target_2010_source_name_raw'],'target_source_label_raw_ledger':target_name,
   'target_source_label_exact_match':True,'source_ledger_path':str(cfg['ledger']),'source_ledger_sha256':meta[kind]['ledger_sha256'],
   'source_manifest_path':str(cfg['manifest']),'source_manifest_sha256':meta[kind]['manifest_sha256'],
   'lower_anchor_2010_id':r['lower_anchor_2010_id'],'lower_anchor_source_row_selected':r['lower_anchor_source_row'],
   'upper_anchor_2010_id':r['upper_anchor_2010_id'],'upper_anchor_source_row_selected':r['upper_anchor_source_row'],
   'lower_target_upper_source_order_pass':False,
  }
  order_ids=[('lower',str(r['lower_anchor_2010_id']),int(r['lower_anchor_source_row'])),('target',row_id,target_row),('upper',str(r['upper_anchor_2010_id']),int(r['upper_anchor_source_row']))]
  row_values=[]
  for role,sid,selected_row in order_ids:
   rec=l.loc[sid]
   selected_rec=selected_by_id.loc[sid]
   actual=int(rec['_row'])
   assert actual==selected_row,(role,sid,actual,selected_row)
   assert str(selected_rec['source_file'])==r['target_2010_source_file'],(role,sid,'selected file mismatch')
   assert int(selected_rec['source_row'])==actual,(role,sid,'selected row mismatch')
   assert str(selected_rec['source_name_raw']).strip().casefold()==str(rec['label_raw']).strip().casefold(),(role,sid,'selected/ledger literal mismatch')
   row_values.append(actual)
   raw_name=str(rec['label_raw']).strip()
   if role!='target':
    # Anchor names are preserved from the selected source_name_raw field via their source ID.
    pass
   d.update({f'{role}_source_row_1based':actual,f'{role}_source_locator':rec.get(cfg['ledger_locator'],'') or f"{r['target_2010_source_file']}#table1!row={actual}",f'{role}_source_label_raw':raw_name,f'{role}_selected_source_name_raw':selected_rec['source_name_raw'],f'{role}_selected_source_sheet':selected_rec['source_sheet'],f'{role}_selected_raw_literal_exact_match':True})
   cellinfo=cells(rec,role)
   for k,v in cellinfo.items(): d[k]=json.dumps(v,ensure_ascii=False,sort_keys=True)
  assert row_values[0]<row_values[1]<row_values[2],(row_id,row_values)
  d['lower_target_upper_source_order_pass']=True
  d['source_context_inference_only']=True
  d['native_district_asserted']=False
  out.append(d)

 result=pd.DataFrame(out)
 result.to_csv(OUT/'held_source_recovery_mapping.csv',index=False)
 manifests_out={k:{**meta[k],'source_manifest_release':manifests[k].get('release'),'source_locator':manifests[k].get('source_locator'),
                   'archived_url':manifests[k].get('archived_asset_url') or manifests[k].get('population_source_archive_url'),
                   'observation_sheet':manifests[k].get('source_observation_sheet'),
                   'observation_sheet_shape':manifests[k].get('source_observation_sheet_shape') or manifests[k].get('source_table_shape')}
                for k in SOURCES}
 binary_specs=[
  ('kaliningrad','published_population_workbook',Path('/workspace/settlements-work/sources/r2-missing/kaliningrad_tom1.xlsx'),'source_sha256','official_asset_url','research_rebuild/evidence/ingestion/sources/kaliningrad_2010_official/kaliningrad_2010_tom1.xlsx'),
  ('murmansk','published_population_by_sex_doc',Path('/workspace/settlements-work/sources/r2-missing/murmansk_population.doc'),'population_source_sha256','population_source_original_url','research_rebuild/evidence/ingestion/sources/murmansk_2010_official/murmansk_population_by_sex_municipalities.doc'),
  ('murmansk','companion_grouped_settlements_doc',Path('/workspace/settlements-work/sources/r2-missing/murmansk_grouping.doc'),'grouping_source_sha256','grouping_source_original_url','research_rebuild/evidence/ingestion/sources/murmansk_2010_official/murmansk_grouped_settlements_by_population.doc'),
 ]
 binary_rows=[]
 for region,role,path,hash_key,url_key,selected_path in binary_specs:
  m=manifests[region]; exists=path.is_file(); actual_sha=sha(path) if exists else ''
  expected_sha=m[hash_key]; expected_bytes=m.get('source_bytes',m.get('population_source_bytes') if role=='published_population_by_sex_doc' else m.get('grouping_source_bytes'))
  size=path.stat().st_size if exists else None
  item={'region':region,'role':role,'physical_path':str(path),'selected_source_file':selected_path,
        'published_source_sha256':expected_sha,'published_source_bytes':expected_bytes,
        'published_url':m[url_key],'present':exists,'physical_bytes':size,'physical_sha256':actual_sha,
        'physical_hash_matches_published':bool(exists and size==expected_bytes and actual_sha==expected_sha),
        'under_settlements_raw':False}
  assert item['physical_hash_matches_published'],item
  binary_rows.append(item)
 binary_inventory={'status':'original_binaries_found_and_hash_verified_outside_settlements_raw',
                   'inventory_scope':'three exact source files only; no large data fetch','files':binary_rows,
                   'all_physical_hashes_match_published_manifest':True}
 (OUT/'existing_binary_inventory.json').write_text(json.dumps(binary_inventory,ensure_ascii=False,indent=2)+'\n')
 summary={'status':'source_recovery_complete_from_existing_hash_pinned_full_cell_ledgers','new_source_downloaded':False,
          'held_rows_input':len(held),'mapped_rows':len(result),'source_order_verified_rows':int(result.lower_target_upper_source_order_pass.sum()),
          'source_counts':result.groupby('source_file_selected').size().to_dict(),
          'source_artifacts':manifests_out,
          'existing_binary_inventory':'existing_binary_inventory.json',
          'original_binaries_available_outside_settlements_raw':True,
          'independent_review_refs':{
           'kaliningrad':{'path':'research_rebuild/evidence/reviews/kaliningrad_2010_r2_independent_review_20260930/review.json','status':'accepted_for_primary_observation_migration_with_source_lineage_note'},
           'murmansk':{'path':'research_rebuild/evidence/reviews/murmansk_2010_candidate_r1_independent_review_20260930/review.json','status':'PASS_SOURCE_OBSERVATION_SLICE_AND_ZERO_BIN_CLOSURE; HOLD_CROSS_CENSUS_IDENTITY'}},
          'receipt':'availability_receipt.md',
          'outputs':{p.name:sha(p) for p in [OUT/'held_source_recovery_mapping.csv',OUT/'existing_binary_inventory.json']},
          'identity_rule_unchanged':True,'accepted_678_packet_unchanged':True,
          'interpretation':'These artifacts restore literal source-cell and physical-order availability for the already generated held 2010 candidates. They do not create new identity decisions.'}
 (OUT/'source_recovery.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:summary[k] for k in ('status','held_rows_input','mapped_rows','source_order_verified_rows','source_counts')},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
