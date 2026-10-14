"""Reuse accepted1989 own-point identities for literal1979 source contexts; never copy counts."""
from pathlib import Path
import json,re,hashlib,collections
import pandas as pd
E=Path(__file__).resolve().parent;B=E.parent
p=E/'primary_bindings.parquet';s=B/'rsfsr1989_integration_20261013/population_1989_selected_long.parquet';a=B/'rsfsr1989_primary_binding_20261013/primary_bindings.parquet'
d=pd.read_parquet(p);old=pd.read_parquet(s);raw=pd.read_parquet(a);byuid={r['source_record_id']:r for r in old.to_dict('records')};index=collections.defaultdict(list)
def n(v):return ' '.join(re.sub(r'[^а-яa-z0-9]+',' ',str(v or '').lower().replace('ё','е')).split())
for _,r in raw.iterrows():
 z=byuid.get(r.source_record_id)
 if z:index[(n(r.source_name_parsed_for_binding),n(r.current_region_alias))].append((r,z))
add=[]
for ix,r in d.iterrows():
 if str(r.binding_status).startswith('bound'):continue
 cand=index[(n(r.source_name_parsed_for_binding),n(r.current_region_alias))]
 exact=[(v,z) for v,z in cand if n(v.administrative_heading_raw)==n(r.administrative_heading_raw)]
 if exact:cand=exact
 if len({z['root'] for _,z in cand})!=1:continue
 v,z=cand[0]
 for k,val in {'root':z['root'],'anchor_source_record_id':z['anchor_source_record_id'],'accepted_latitude':z['latitude'],'accepted_longitude':z['longitude'],'binding_status':'bound_accepted_1989_physical_place_literal_source_name_region_context','binding_rule':'literal1979_1989_name_region_unique_accepted1989_place_prefer_same_source_admin_context','coordinate_role':z['point_identity_grade'],'coordinate_source_url':z['coordinate_source_url'],'coordinate_source_sha256':z['coordinate_source_sha256'],'coordinate_source_locator':z['coordinate_source_locator'],'matched_1989_source_record_id':z['source_record_id'],'external_id':z['external_id'],'external_identity_asserted':z['external_identity_asserted']}.items():d.loc[ix,k]=val
 add.append({'source_record_id':r.source_record_id,'matched_1989_source_record_id':z['source_record_id'],'root':z['root'],'population1979':int(r.population_total)})
# Published homonym row in Inta context conflicts with the Koygorodsky own identity.
mask=d.source_record_id.eq('1979:demoscope:rus79_reg2.php:html_tr:108')
d.loc[mask,'binding_status']='held_source_homonym_conflicting_admin_context';d.loc[mask,'root']=None
out=E/'primary_bindings_augmented.parquet';d.to_parquet(out,index=False)
rec={'inputs':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in [p,s,a]},'added_from_accepted1989':add,'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'held_source_row_108_802':True}
(E/'augmentation_receipt.json').write_text(json.dumps(rec,ensure_ascii=False,indent=2));print('added',len(add),'population',sum(x['population1979'] for x in add))
