from pathlib import Path
import pandas as pd,json,gzip,hashlib
O=Path(__file__).parent;B=O.parent;sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
a=pd.read_csv(B/'batch2_lifecycle_homonyms/all111_dispositions_after_batch2.csv');statuses=[];w=[]
cases=[('Пограничный (Московская область)','own_wikipedia_batch3.json.gz',69890,'historically_existing_locality_1959_named_Pogranichny_2012; not_born_2012'),('Орешково (Луховицкий район)','own_wikipedia_batch1.json.gz',68202,'post_2011_03_22_merger_receiver_scope; earlier_individual_predecessors_not_same_scope')]
for title,fn,row,ctx in cases:
 p=next(p for p in json.load(gzip.open(B/fn,'rt'))['query']['pages'].values()if p.get('title')==title);r=a[a.source_record_id.str.endswith(':'+str(row))].iloc[0];assert r.after_ownpoint
 text=p['revisions'][0]['slots']['main']['*'];w.append(dict(source_record_id=r.source_record_id,title=title,pageid=p['pageid'],revision=p['revisions'][0]['revid'],source_path=str(B/fn),source_sha256=sha(B/fn),literal_own_article_text=text,lifecycle_context=ctx))
 for year in [2002,2010,2021]:statuses.append(dict(scope_id='available_lifecycle_'+r.source_record_id,source_record_id=r.source_record_id,year=year,status='actual_native_ownpoint_observation_with_documented_lifecycle_context'if year==2021 else'UNKNOWN_individual_count_on_this_scope; historical_existence_not_population_observation',native_population=r.population if year==2021 else'',own_point=year==2021,lifecycle_context=ctx,boundary_comparability='UNKNOWN',unknown_is_zero=False,ordinary_full3_claim=False,is_additive_to_original_final_mixed_census_axis=False))
 a.loc[a.source_record_id.eq(r.source_record_id),'disposition']='accepted_single_available_observation_documented_lifecycle_context'
t=Path('research_rebuild/evidence/over1000_moscow_inner_territories_20261009');territ=pd.read_csv(t/'available_year_statuses.csv');territ.to_csv(O/'accepted_typed_territorial_available_year_statuses.csv',index=False);a.loc[a.source_record_id.isin(territ.source_record_id),'disposition']='accepted_typed_Moscow_child_territorial_available_route_nonadditive'
pd.DataFrame(statuses).to_csv(O/'accepted_single_observation_lifecycle_available_year_statuses.csv',index=False);pd.DataFrame(w).to_csv(O/'literal_lifecycle_context_witnesses.csv',index=False)
a.to_csv(O/'all111_dispositions_after_available_context.csv',index=False);a[a.disposition.str.startswith('held')].to_csv(O/'remaining_assigned_holds.csv',index=False)
paths=[t/'README.md',t/'available_year_statuses.csv',t/'accepted_2002_locality_point_uses.csv']+[B/x[1]for x in cases];(O/'available_context_source_manifest.json').write_text(json.dumps([dict(path=str(p),sha256=sha(p))for p in paths],ensure_ascii=False,indent=2));print(a.disposition.value_counts().to_json(force_ascii=False))
