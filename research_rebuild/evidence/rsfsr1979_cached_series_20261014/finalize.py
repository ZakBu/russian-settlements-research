from pathlib import Path
import pandas as pd,json,hashlib,glob
OUT=Path('/workspace/shared/rsfsr1979_cached_series');E=Path(__file__).parent
w=pd.read_parquet(OUT/'wiki/candidate_facts.parquet');w=w[w.decision_status.eq('accepted')].copy();w['raw_row']=w.population.astype(str)+' (1979)';w['source_tier']='secondary';w['population_scope']='individual_named_settlement';w['historical_boundary_comparability']='UNKNOWN';w['source_record_id']='wikipedia:'+w.article_title+':1979';w['population_value_quality']='literal_published_integer';w['current_region']=w.region_raw
w.to_parquet(OUT/'wiki/accepted_additional_facts.parquet',index=False)
c=pd.read_parquet(OUT/'wiki/candidate_facts.parquet');c['raw_row']=c.population.astype(str)+' (1979)';c.to_parquet(OUT/'wiki/candidate_facts.parquet',index=False)
a=pd.read_parquet(OUT/'encyclopedia_accepted_facts.parquet');a['population_value_quality']='literal_published_integer'
d=pd.concat([a,w],ignore_index=True);conf=d.groupby('root').population.nunique();held=set(conf[conf.gt(1)].index)
d[d.root.isin(held)].to_parquet(OUT/'conflicting_observations.parquet',index=False)
d=d[~d.root.isin(held)].drop_duplicates('root');d.to_parquet(OUT/'population_1979_selected_long.parquet',index=False)
core=Path('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
receipt={'core_input':{'path':str(core),'sha256':hashlib.sha256(core.read_bytes()).hexdigest()},'year':1979,'accepted_encyclopedia_observations':len(a),'accepted_wikipedia_observations':len(w),'conflicting_roots_held':len(held),'selected_roots':len(d),'selected_population':int(d.population.sum()),'no_new_downloads':True,'all_selected_secondary':bool(d.source_tier.eq('secondary').all()),'no_fake_zero':bool(d.population.gt(0).all()),'source_kinds':d.source_kind.value_counts().to_dict(),'output_files':[],'wiki_raw_manifest':[]}
for f in sorted(glob.glob('/workspace/shared/wiki1989-cached/data/raw/wikipedia_articles/*.gz')):receipt['wiki_raw_manifest'].append({'path':f,'sha256':hashlib.sha256(Path(f).read_bytes()).hexdigest()})
for f in OUT.rglob('*.parquet'):receipt['output_files'].append({'path':str(f),'rows':len(pd.read_parquet(f)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
(E/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print({k:v for k,v in receipt.items() if k not in ['output_files','wiki_raw_manifest']})
