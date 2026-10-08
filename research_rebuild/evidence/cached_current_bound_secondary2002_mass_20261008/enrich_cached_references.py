from pathlib import Path
import pandas as pd,json,gzip,re,hashlib
O=Path(__file__).parent;c=pd.read_csv(O/'cached_dated2002_claims.csv.gz',keep_default_na=False);needed={q for v in c.reference_ids_json for q in json.loads(v)};labels={};rows=[];pins={}
for p in [Path('/workspace/settlements-work/wikidata_actual_full3_mass_reserve_20261007/reference_batch_0.json.gz'),Path('/workspace/settlements-work/wikidata_actual_full3_mass_reserve_20261007/census_reference_items.json.gz'),Path('/workspace/settlements-work/wikidata_secondary_full3_expansion_20261007/reference_batch_0.json.gz'),Path('/workspace/settlements-work/continuation_20261004/regions/chechnya_top_residual_graph16_recheck_20261005/source_chain_followup/Q126687602.json')]:
 b=p.read_bytes();d=json.loads(gzip.decompress(b) if p.name.endswith('.gz') else b);hash=hashlib.sha256(b).hexdigest();pins[str(p)]=hash
 for q,z in d.get('entities',{}).items():
  if q not in needed:continue
  lab=z.get('labels',{}).get('ru',{}).get('value','');labels[q]=lab;rows.append({'reference_QID':q,'literal_label':lab,'raw_source_path':str(p),'raw_sha256':hash,'revision':z.get('lastrevid','')})
def explicit(t):return bool(re.search('перепис|census|vpn2002|впн',t,re.I)) and ('2002' in t or 'vpn2002' in t.lower())
for i,a in c.iterrows():
 ids=json.loads(a.reference_ids_json);labs=[labels.get(q,old) for q,old in zip(ids,json.loads(a.reference_item_labels_json))];c.loc[i,'reference_item_labels_json']=json.dumps(labs,ensure_ascii=False)
 if any(explicit(t) for t in labs):c.loc[i,'explicit_census2002_proof']=True
c.to_csv(O/'cached_dated2002_claims.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(rows).to_csv(O/'cached_reference_item_witness.csv',index=False);r=json.load(open(O/'receipt.json'));r['input_pins'].update(pins);r['cached_reference_item_labels_enriched']=len(rows);(O/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print('Cached reference labels',len(rows))
