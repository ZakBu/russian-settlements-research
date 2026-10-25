"""Fixed 2020 administrative contexts: change in historical raw-code footprint, not trips."""
from pathlib import Path
import pandas as pd,json,itertools,csv
R=Path(__file__).resolve().parents[4];O=Path(__file__).resolve().parent;B=R/'work/sources/research/ecommerce_settlement_20261024';K='source_record_id_2021'
ctx=pd.read_parquet(B/'history_stage_20261024/centres/settlement_admin_context_main2021.parquet').set_index(K);systems=pd.read_csv(B/'settlement_role_stage_20261024/system/centre_system_demography.csv');medium=set(systems.loc[systems.medium_primary2002,K]);assert len(medium)==1273
known=ctx.context_status_20200110.eq('accepted_administrative_parent_and_centre');parent='administrative_centre_source_record_id_2021_20200110';groups={c:set(g.index)for c,g in ctx.loc[known].groupby(parent)}
for c in medium:groups.setdefault(c,set()).add(c)
links=pd.read_parquet(B/'history_stage_20261024/wb_history_symmetric_links.parquet');links=links.loc[links.archive_date.ne('2026-10-21')].copy();links.source_object_id=links.source_object_id.astype(str)
raw={}
for f in (R/'work/ecommerce_extension_history').glob('wb_????-??-??.json'):
 date=f.stem[3:]
 for country in json.loads(f.read_text()):
  if country['country']=='ru':
   for x in country['items']:raw[date,str(x['id'])]=x
links['code_profile']=[raw[d,i].get('dtype')==0 and raw[d,i].get('isWb')is True and raw[d,i].get('pickupType')in [3,4]for d,i in zip(links.archive_date,links.source_object_id)]
links['fitted']=[(raw[d,i].get('fittingRooms')or 0)>=1 for d,i in zip(links.archive_date,links.source_object_id)]
profiles={};allsets={}
for radius in [1,5,10]:
 col=f'{K}_{radius}km'
 for date,g in links.groupby('archive_date'):
  allsets[date,radius]=set(g.loc[g[col].notna(),col])
  for prof,mask in [('raw_code_profile',g.code_profile),('raw_code_profile_fitted',g.code_profile&g.fitted)]:profiles[date,radius,prof]=set(g.loc[mask&g[col].notna(),col])
rows=[];individual=[]
for radius in [1,5,10]:
 for prof in ['raw_code_profile','raw_code_profile_fitted']:
  for d0,d1 in itertools.combinations(sorted(links.archive_date.unique()),2):
   a,b=profiles[d0,radius,prof],profiles[d1,radius,prof];stats=[]
   for c in sorted(medium):
    other=groups[c]-{c};n0=len(other&a);n1=len(other&b);retained=c in a and c in b;added_other=len(other&(b-allsets[d0,radius]));row={'date0':d0,'date1':d1,'radius_km':radius,'profile':prof,K:c,'other_members':len(other),'centre_positive0':c in a,'centre_positive1':c in b,'centre_positive_both':retained,'other_positive0':n0,'other_positive1':n1,'other_footprint_expands':n1>n0,'later_other_positive_without_any_earlier_catalogue':added_other}
    stats.append(row)
    if d0=='2022-09-29'and d1=='2024-03-11'and radius==5 and prof=='raw_code_profile':individual.append(row)
   q=pd.DataFrame(stats);rows.append({'date0':d0,'date1':d1,'radius_km':radius,'profile':prof,'fixed_medium_centres_denominator':len(medium),'contexts_with_other_members':int(q.other_members.gt(0).sum()),'centre_positive0':int(q.centre_positive0.sum()),'centre_positive1':int(q.centre_positive1.sum()),'centre_positive_both':int(q.centre_positive_both.sum()),'centre_positive_both_and_other_footprint_expands':int((q.centre_positive_both&q.other_footprint_expands).sum()),'centre_positive_both_and_later_other_without_any_earlier_catalogue':int((q.centre_positive_both&q.later_other_positive_without_any_earlier_catalogue.gt(0)).sum()),'centre_record_only_earlier':int((q.centre_positive0&~q.centre_positive1).sum()),'centre_record_only_later':int((~q.centre_positive0&q.centre_positive1).sum()),'centre_no_record_both':int((~q.centre_positive0&~q.centre_positive1).sum())})
pd.DataFrame(rows).to_csv(O/'wb_profile_medium_contexts_summary.csv',index=False);pd.DataFrame(individual).to_csv(O/'wb_profile_medium_contexts_2022_2024_5km.csv',index=False)
print(pd.DataFrame(rows).query("date0=='2022-09-29' and date1=='2024-03-11'").to_string(index=False))
