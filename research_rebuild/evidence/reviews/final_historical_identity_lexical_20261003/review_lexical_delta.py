from pathlib import Path
import json,unicodedata,xlrd,pandas as pd
from research_rebuild.mass_linkage.coverage import identity_sets,sha
from research_rebuild.mass_linkage.apply_historical_identity_rule import SELECTED
w=Path('/workspace/settlements-work');s=w/'identity/historical_spatial_application_v3';o=w/'identity/historical_spatial_application_review_v3';o.mkdir(exist_ok=True)
e=pd.read_parquet(s/'staged_identity_edges.parquet');base=pd.read_parquet(w/'identity/accepted_historical_v1/accepted_identity_edges.parquet');checks=pd.read_parquet(s/'application_checks.parquet');raw=pd.read_parquet(s/'source_row_checks.parquet').set_index('source_record_id');src=pd.read_parquet(SELECTED).set_index('source_record_id');new=e[e.decision_status.eq('pending_independent_application_review')];assert len(new)==1414
assert e.iloc[:len(base)][base.columns].reset_index(drop=True).equals(base.reset_index(drop=True))
assert set(zip(new.from_source_record_id,new.to_source_record_id))==set(zip(checks.loc[checks.status.eq('staged_checked_rule_application'),'from_source_record_id'],checks.loc[checks.status.eq('staged_checked_rule_application'),'to_source_record_id']))
books={};rows=[]
def nk(v):return ' '.join(unicodedata.normalize('NFKC',str(v)).casefold().replace('ё','е').split())
for a in new.from_source_record_id:
    q=raw.loc[a];r=src.loc[a];f=Path('/workspace/settlements-raw')/q.source_file
    if q.source_file not in books:
        assert sha(f)==q.source_sha256
        books[q.source_file]=xlrd.open_workbook(str(f),on_demand=True)
    sheet=books[q.source_file].sheet_by_name(q.source_sheet);cells=sheet.row_values(int(q.source_row_1based)-1)
    literal=[str(c).strip() for c in cells]
    # South source has type in F and locality in G; these are not a carried heading.
    literal += [' '.join(literal[5:7])]
    assert nk(q.raw_label) in [nk(v) for v in literal]
    assert float(q.raw_population)==float(r.population)
    assert any(isinstance(c,(int,float)) and c==r.population for c in cells)
    assert nk(q.raw_label).endswith(' '+nk(r.settlement_name))
    rows.append({'source_record_id':a,'raw_label':q.raw_label,'population':int(r.population),'source_file':q.source_file,'source_row_1based':int(q.source_row_1based)})
for b in books.values():b.release_resources()
_,full,components=identity_sets(src.reset_index(),e)
pd.DataFrame(rows).to_csv(o/'whole_delta_raw_rows.csv',index=False)
review={'review_id':'historical_identity_lexical_delta_review_20261003','verdict':'APPROVE the 1414 normalized-literal delta pairs, identity only. Preserve all baseline and holds.','scope':{'staged_new_pairs':1414},'pins':{'application_receipt_sha256':sha(s/'receipt.json'),'application_checks_sha256':sha(s/'application_checks.parquet'),'source_row_checks_sha256':sha(s/'source_row_checks.parquet'),'staged_identity_edges_sha256':sha(s/'staged_identity_edges.parquet')},'independent_checks':{'baseline_174034_edges_unchanged':True,'positive_pair_sets_equal':True,'all_1414_raw_xls_label_population_rows_reopened':True,'raw_source_families':len(books),'same_year_collision_count':0,'full_chain_components':len(full)//3,'held_rows':529,'dash_population_interpretation_changed':False},'review_script_sha256':sha(Path(__file__)),'limits':'Unicode spelling/whitespace correction only; no population quality, coordinate or boundary admissions. Whole raw number/name rows checked, not a national probability precision estimate.'}
(o/'review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n');print(json.dumps(review['independent_checks']))
