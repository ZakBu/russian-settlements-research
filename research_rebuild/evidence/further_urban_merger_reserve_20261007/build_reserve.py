"""Bounded reserve only: recovered Kemerovo act roster, not accepted output."""
from pathlib import Path
import json,hashlib,gzip,sys
import pandas as pd,duckdb
ROOT=Path(__file__).resolve().parents[3];O=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from measure_event_aware_path_union_20261005 import SELECTED

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 names=['Кемерово','Боровой','Кедровка','Пионер','Промышленновский','Ягуновский']
 d=duckdb.connect().execute('select * from read_parquet(?) where region_norm=? and settlement_name in (select unnest(?))',[str(SELECTED),'кемеровская',names]).fetchdf()
 rows=[];series=[]
 for y in [2002,2010,2021]:
  picked=[]
  for n in names if y==2002 else ['Кемерово']:
   f=d[(d.census_year==y)&d.settlement_name.eq(n)&d.settlement_type.isin(['город'] if n=='Кемерово' else ['пгт'])]
   assert len(f)==1,(y,n,len(f));r=f.iloc[0];p=Path('/workspace/settlements-raw')/r.source_file
   if y==2002:
    assert p.name=='1_TOM_01_04.xls';raw=pd.read_excel(p,header=None).iloc[int(r.source_row)-1];assert int(raw[1])==int(r.population) and n.lower().replace('ё','е') in str(raw[0]).lower().replace('ё','е')
   row={'group':'Kemerovo_2004_named','census_year':y,'source_record_id':r.source_record_id,'settlement_name':n,'settlement_type':r.settlement_type,'population':int(r.population),'source_file':r.source_file,'source_file_sha256':sha(p),'source_row_locator':f'{r.source_sheet}!row={r.source_row}','region_norm':r.region_norm,'district_raw':r.district_raw,'candidate_only':True,'source_population_unmodified':True,'ordinary_same_place':False,'exclusive_source_ID_credit':True,'separate_population_credit_in_addition_to_group':False}
   rows.append(row);picked.append(row)
  series.append({'group':'Kemerovo_2004_named','census_year':y,'population':sum(x['population'] for x in picked),'constituent_count':len(picked),'source_record_ids_json':json.dumps([x['source_record_id'] for x in picked]),'roster_complete':True,'boundary_comparability':'UNKNOWN','ordinary_same_place':False,'candidate_only':True,'status':'HOLD_RECEIVING_CITY_EVENT_CORROBORATION_AND_POINT_REVIEW'})
 text=(O/'kemerovo64_archive.txt').read_text();i=text.index('Статья 1.');j=text.index('Статья 2.',i)
 witness={'key':'kemerovo64_archived_actual_act','source_path':str(O/'kemerovo64_archive.html'),'source_sha256':sha(O/'kemerovo64_archive.html'),'source_url':'https://web.archive.org/web/20170901195900id_/https://docs.cntd.ru/document/990304789','plaintext_path':str(O/'kemerovo64_archive.txt'),'plaintext_sha256':sha(O/'kemerovo64_archive.txt'),'exact_excerpt':text[i:j],'kemerovo_roster':names[1:],'source_class':'secondary_archived_actual_act_body','official_act_verified':False,'interpretation':'Law deletes complete five named Kemerovo pgt; receiving-city inclusion must be corroborated independently.'}
 (O/'source_witnesses.json').write_text(json.dumps([witness],ensure_ascii=False,indent=2)+'\n')
 pd.DataFrame(rows).to_csv(O/'candidate_kemerovo_constituents.csv',index=False);pd.DataFrame(series).to_csv(O/'candidate_kemerovo_group_observations.csv',index=False)
 receipt={'status':'reserve_complete_kemerovo_act_roster_recovered_not_admitted','candidate_only':True,'admission_allowed':False,'kemerovo_named_2002_roster_count':6,'candidate_observations':3,'candidate_constituents':8,'boundary_comparability':'UNKNOWN','kemerovo_hold':'Receiving-city inclusion and representative point review pending; no accepted ledger and no gain credit emitted.','voronezh_hold':'WHOLE_GROUP_HOLD_COMPLETE_24_PLUS_PARENT_ROSTER_AND_NATIVE_BINDINGS; direct2011 law106027129 still503; no partial sum emitted.','inputs_sha256':{str(SELECTED):sha(SELECTED)},'outputs':{p.name:sha(p) for p in O.glob('*') if p.is_file() and p.name!='receipt.json'}}
 (O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(series))
if __name__=='__main__':main()
