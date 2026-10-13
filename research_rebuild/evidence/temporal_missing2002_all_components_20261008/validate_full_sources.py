"""Read-only whole-packet raw claim, date, census reference and own code/point checks."""
from pathlib import Path
import sys,json,gzip,re
import pandas as pd,duckdb
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from current_chain_state_20261007 import sha,distance_km
from report_helper import load_qualified
O=Path(__file__).parent

def raw_entities(path):
    raw=path.read_bytes()
    data=json.loads(gzip.decompress(raw) if path.name.endswith('.gz') else raw)
    return data.get('entities',data.get('payload',{}).get('entities',{}))
def value(snak):return snak.get('datavalue',{}).get('value')
def census2002(text):return bool(re.search(r'перепис|census|vpn2002|впн',text,re.I)) and ('2002' in text or 'vpn2002' in text.lower())
def validate():
    frame=load_qualified();cache={};reference_labels={};sources={}
    for row in pd.read_csv(O/'cached_reference_item_witness.csv',keep_default_na=False).to_dict('records'):
        path=Path(row['raw_source_path']);assert sha(path)==row['raw_sha256']
        if path not in cache:cache[path]=raw_entities(path)
        entity=cache[path][row['reference_QID']];literal=entity.get('labels',{}).get('ru',{}).get('value','');assert literal==row['literal_label'];reference_labels[row['reference_QID']]=literal
    selection=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet');receipt=json.load(open(O/'qualified_application_receipt.json'));assert sha(selection)==receipt['selected_source_sha256']
    con=duckdb.connect(config={'threads':1,'memory_limit':'500MB'});native=con.execute('select source_record_id,census_year,population,population_value_quality,oktmo,okato,is_additive_settlement_record from read_parquet(?)',[str(selection)]).fetchdf().set_index('source_record_id');con.close();checked=0
    for _,group in frame.groupby('trajectory_id'):
        old=group[group.year.eq(2002)].iloc[0];current=group[group.year.eq(2021)].iloc[0];qid=old.wikidata_id;path=Path(old.source_path);assert sha(path)==old.source_sha256
        if path not in cache:cache[path]=raw_entities(path)
        entity=cache[path][qid];statement=next(x for x in entity['claims']['P1082'] if x.get('id')==old.statement_id);assert statement.get('rank')!='deprecated' and not statement.get('qualifiers',{}).get('P518');assert float(value(statement['mainsnak'])['amount'])==old.population_source_value
        dates=[value(x) for x in statement.get('qualifiers',{}).get('P585',[])];assert any(x.get('time')==old.declared_date and int(x.get('precision',-1))==int(old.date_precision) for x in dates if isinstance(x,dict));assert old.declared_date.startswith('+2002')
        refs=statement.get('references',[]);titles=[value(x).get('text','') for ref in refs for x in ref.get('snaks',{}).get('P1476',[]) if isinstance(value(x),dict)];ids=[value(x).get('id','') for ref in refs for x in ref.get('snaks',{}).get('P248',[]) if isinstance(value(x),dict)];urls=[str(value(x)) for ref in refs for x in ref.get('snaks',{}).get('P854',[])];assert titles==json.loads(old.census_reference_titles_json) and ids==json.loads(old.P248_ids_json) and urls==json.loads(old.reference_urls_json)
        storedlabels=json.loads(old.P248_labels_json);actual_labels=[reference_labels.get(x,'') for x in ids];assert storedlabels==actual_labels;assert old.declared_date.startswith('+2002-10-09') or any(census2002(t) for t in titles+urls+actual_labels)
        point=json.loads(current.point_binding_json);target=native.loc[current.source_record_id];codes764=[value(x['mainsnak']) for x in entity.get('claims',{}).get('P764',[]) if x.get('rank')!='deprecated'];codes721=[value(x['mainsnak']) for x in entity.get('claims',{}).get('P721',[]) if x.get('rank')!='deprecated'];nativecodes=[str(int(target[k])) if pd.notna(target[k]) else '' for k in ['oktmo','okato']];direct=qid in re.findall(r'\bQ\d+\b',str(point.get('coordinate_source_record_id',''))+' '+str(point.get('point_origin_locator','')));exact=nativecodes[0] in codes764 or nativecodes[1] in codes721;coords=[value(x['mainsnak']) for x in entity.get('claims',{}).get('P625',[]) if x.get('rank')!='deprecated'];near=any(distance_km((current.latitude,current.longitude),(x['latitude'],x['longitude']))<=1 for x in coords if isinstance(x,dict) and 'latitude' in x);assert direct or exact and near
        for row in group[group.year.ne(2002)].to_dict('records'):
            source=native.loc[row['source_record_id']];assert source.census_year==row['year'] and source.population==row['population_source_value'] and source.population_value_quality==row['population_quality'] and source.is_additive_settlement_record
        checked+=1
    return {'series':checked,'raw_GUID_value_date_precision_subset_reference_checks':checked,'native_observations':int(frame.year.ne(2002).sum()),'status':'passed_readonly_raw_source_validation'}
if __name__=='__main__':print(json.dumps(validate()))
