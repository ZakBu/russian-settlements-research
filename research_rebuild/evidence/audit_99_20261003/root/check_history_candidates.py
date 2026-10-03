from pathlib import Path
import pandas as pd, json,hashlib,re,csv,time
D=Path('/workspace/settlements-work/continuation_20261003/audit_99_20261003/wikidata_history_large');O=D.parent/'root'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def guid(s):return str(s).split('/')[-1].replace('$','-').lower()
t=time.monotonic();s=json.loads((D/'summary.json').read_text());f=pd.read_parquet(D/'candidate_long.parquet');z=pd.read_parquet(D/'candidate_tsv_long.parquet')
assert len(f)==4984 and len(z)==64483
for name,table in [('candidate_long.parquet',f),('candidate_tsv_long.parquet',z)]:
 assert sha(D/name)==s['output'][name]['sha256']
 assert table.population_admission.eq(False).all() and table.historical_identity_admission.eq(False).all()
 assert not table.statement_id.map(guid).duplicated().any()
 assert not any(c in table for c in ['latitude','longitude','census_year'])
assert set(f.statement_id.map(guid))<=set(z.statement_id.map(guid))
assert f['rank'].ne('deprecated').all()
for r in f.itertuples(index=False):
 claim=json.loads(r.raw_statement_json);assert claim['mainsnak']['property']=='P1082'
 assert json.loads(r.all_qualifiers_raw_json)==claim.get('qualifiers',{})
 assert json.loads(r.all_references_raw_json)==claim.get('references',[])
 assert r.references_count==len(claim.get('references',[]))
assert int(z.raw_duplicate_row_count.sum())==128309
for r in z.itertuples(index=False):assert len(json.loads(r.raw_matching_line_numbers_json))==r.raw_duplicate_row_count
# Duplicate raw rows may contain several date/code variants; preserve or flag them explicitly.
ids=set(z.qid); groups={}
source=Path(z.raw_source_file.iloc[0])
with source.open() as fh:
 reader=csv.reader(fh,delimiter='\t',quoting=csv.QUOTE_NONE);next(reader)
 for row in reader:
  if len(row)<6:continue
  qid=row[0].split('/')[-1].rstrip('>')
  if qid not in ids:continue
  k=guid(row[2].strip('<>'))
  if k:
   v=groups.setdefault(k,{'population':set(),'date':set(),'code':set(),'rank':set()})
   for field,val in [('population',row[3]),('date',row[4]),('code',row[1]),('rank',row[5])]:v[field].add(val)
variants={k:sum(len(v[k])>1 for v in groups.values()) for k in ['population','date','code','rank']}
assert variants=={'population':0,'date':4,'code':0,'rank':0}
assert int(z.date_literal_ambiguous.sum())==4
assert z.loc[z.date_literal_ambiguous,'date_literal_flat_tsv'].isna().all()
for r in z.itertuples(index=False):
 assert set(json.loads(r.date_literal_variants_json))==(groups[guid(r.statement_id)]['date']-{''})
 assert bool(r.rank_is_deprecated)==('DeprecatedRank' in str(r.rank_uri_flat_tsv))
 assert bool(r.rank_admissible_for_candidate_history)==(not bool(r.rank_is_deprecated))
assert int(z.rank_is_deprecated.sum())==17
assert int(z.rank_admissible_for_candidate_history.sum())==64466
receipt={'verdict':'PASS_CANDIDATE_HISTORY_INTEGRITY','full_rows':len(f),'tsv_raw_inventory_rows':len(z),'tsv_nondeprecated_rows':64466,'tsv_deprecated_rows_preserved_but_excluded_from_candidate_history':17,'same_statement_overlap':4984,'full_qualifiers_and_references_equal_raw_statements':True,'false_admission_flags':True,'unique_statement_guids':True,'raw_duplicate_rows_accounted_for':128309,'duplicate_variant_statement_counts':variants,'all_date_variants_preserved_and_ambiguous_scalar_dates_suppressed':True,'output_sha256':{name:sha(D/name) for name in ['candidate_long.parquet','candidate_tsv_long.parquet']},'seconds':round(time.monotonic()-t,3),'new_population_or_identity_admissions':0}
(O/'history_candidates_review.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
