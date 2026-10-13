import json,csv,re,math,hashlib,collections,gzip
from pathlib import Path
import pyarrow as pa,pyarrow.parquet as pq
E=Path(__file__).resolve().parent
primary=E.parent/'rsfsr1989_primary_binding_20261013/primary_bindings.csv'
raw=list(csv.DictReader(open(primary)));unbound=[x for x in raw if not x['binding_status'].startswith('bound')]; byname={x['source_name_parsed_for_binding']:x for x in unbound if x['qualified_historical_region']=='Санкт-Петербург'}
selected=json.load(open(E/'selected_search_candidates.json'));out=[];checks=[]
def values(d,k):return[x['mainsnak'].get('datavalue',{}).get('value')for x in d.get('claims',{}).get(k,[])if x.get('rank')!='deprecated']
def ids(d,k):return[v.get('id')for v in values(d,k)if isinstance(v,dict)]
contexts={}
for p in E.glob('context_Q*.json'):
 contexts.update(json.load(open(p))['entities'])
for name,q in selected.items():
 f=E/('entity_'+q+'.json')
 if not f.exists():continue
 d=json.load(open(f))['entities'][q];historic='Петродворец'if name=='Петергоф'else name;x=byname.get(historic)
 if not x:continue
 label=d.get('labels',{}).get('ru',{}).get('value','');aliases=[z['value']for z in d.get('aliases',{}).get('ru',[])];desc=d.get('descriptions',{}).get('ru',{}).get('value','');classes=ids(d,'P31');admins=ids(d,'P131');coords=values(d,'P625');coord=[z for z in coords if isinstance(z,dict)and z.get('globe','').endswith('/Q2')and all(math.isfinite(z[k])for k in ['latitude','longitude'])]
 region_proof='Q656'in admins or any('Q656'in ids(contexts.get(a,{}),'P131')for a in admins)
 physical_proof=bool(set(classes)&{'Q515','Q21130185','Q2514025','Q15078955','Q486972'})
 rule='literal_current_name'if name==historic else 'explicit_historical_name_alias_Petrodvorets_Peterhof'
 match=label==name and (historic==name or historic in aliases)
 status='accepted'if match and region_proof and physical_proof and len(coord)==1 else 'held'
 checks.append(dict(source_record_id=x['source_record_id'],qid=q,current_label=label,aliases=aliases,P31=classes,P131=admins,description=desc,literal_or_alias_match=match,region_chain_to_Q656=region_proof,physical_place_class=physical_proof,finite_coordinate_count=len(coord),status=status))
 if status!='accepted':continue
 z=dict(x);c=coord[0];z.update(root='historical:1989:demoscope:'+q,anchor_source_record_id=None,anchor_census_year=None,binding_status='bound_external_physical_point_historical_entity',coordinate_role='external_physical_settlement_point_reused_for_historical_1989_entity',accepted_latitude=c['latitude'],accepted_longitude=c['longitude'],external_id=q,current_name=label,current_region='санкт петербург',individual_2021_census_status='no_individual_2021_census_match',binding_rule=rule+'+physical_P31+region_P131_to_Q656+unique_P625',coordinate_source_url='https://www.wikidata.org/wiki/Special:EntityData/'+q+'.json',coordinate_source_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),coordinate_source_locator='entities.'+q+'.claims.P625',point_identity_grade='qualified_external_physical_place_current_point_historical_continuity_inferred',population_basis='present',historical_boundary_comparability='unknown',retrospective_current_point_inference=True);out.append(z)
fields=list(dict.fromkeys(k for x in out for k in x))
with(E/'external_point_delta.csv').open('w')as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
pq.write_table(pa.Table.from_pylist(out),E/'external_point_delta.parquet',compression='zstd');(E/'entity_validation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
r=dict(rows=len(out),population_total=sum(int(x['population_total'])for x in out),population_basis='present',population_source='Demoscope1989 only; no external population values',distinct_roots=len({x['root']for x in out}),distinct_source_uids=len({x['source_record_id']for x in out}),no_state_graph_mutation=True,no_fake_2021_census=True,validation_held=[x for x in checks if x['status']=='held'],outputs={n:hashlib.sha256((E/n).read_bytes()).hexdigest()for n in ['external_point_delta.csv','external_point_delta.parquet']},primary_input_sha256=hashlib.sha256(primary.read_bytes()).hexdigest());(E/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2))
