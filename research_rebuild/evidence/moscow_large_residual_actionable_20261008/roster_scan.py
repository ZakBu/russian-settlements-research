from pathlib import Path
import json,gzip,re,sys,collections
import pandas as pd
R=Path('/workspace/russian-settlements-research');O=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha
s=load(24);repo=R/'research_rebuild/evidence/working_full_chain_20261007';credit=set();pins={str(p):sha(p) for p in s.inputs}
for fn in ['qualified_scope_source_id_credit_union.csv','named_merger_lineage_constituents.csv','complete_publisher_partition_members.csv']:
 p=repo/fn;f=pd.read_csv(p,dtype=str).fillna('');credit.update(f.source_record_id);pins[str(p)]=sha(p)
for r in s.obs.itertuples():
 root=s.uf.find(r.source_record_id);members=s.obs[s.obs.root==root] if False else None
 if s.years[root]=={2002,2010,2021}:pass
# Ordinary final mixed coverage needs all3ownpoints and finitecounts, not a single pointed row.
for root,g in s.obs.groupby('root'):
 if set(g.census_year)=={2002,2010,2021} and all(sid in s.point_rows for sid in g.source_record_id) and g.population.notna().all():credit.update(g.source_record_id)
entities=json.loads(gzip.open(O/'municipal_entities.json.gz','rt').read())['entities'];pages=json.loads(gzip.open(O/'municipal_pages.json.gz','rt').read())['query']['pages'];old=s.obs[s.obs.region_norm.eq('московская')&s.obs.census_year.isin([2002,2010])].copy();old['n']=old.settlement_name.map(normalize);raw2010=Path('/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls');raw2002=Path('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls');pins[str(raw2010)]=sha(raw2010);pins[str(raw2002)]=sha(raw2002)
val=lambda sn:sn.get('datavalue',{}).get('value');rosters=[];member=[];group=[]
# Exact explicitly printed source-name variants; no fuzzy or prefix similarity admission.
alias={'Завода Мосрентген':['завода "мосрентген"','завода мосрентген'],'института полиомиелита':['института полиомиелита и вирусных энцефалитов','института полиомиелита'],'Ульяновского лесопарка':['ульяновского лесопарка'],'Московский':['московский'],'Воскресенское':['подсобного хозяйства "воскресенское"','подсобного хозяйства воскресенское'],'Ерино':['санатория "ерино"','санатория ерино','ерино'],'Знамя Октября':['знамя октября'],'Щапово':['щапово']}
counties={'Q462784':'Ленинский район','Q4373595':'Ленинский район','Q4373597':'Ленинский район','Q4373611':'Ленинский район','Q4373600':'Ленинский район','Q4373601':'Наро-Фоминский район','Q4373603':'Наро-Фоминский район','Q5470559':'Подольский район','Q4373613':'Подольский район'}
for page in pages.values():
 q=page.get('pageprops',{}).get('wikibase_item')
 if q not in entities:continue
 text=page['revisions'][0]['slots']['main']['*'];m=re.search(r'^== (?:Насел[её]нные пункты|Состав поселения) ==\s*([\s\S]*?)(?=^== |\Z)',text,re.M)
 if not m:continue
 sec=m.group(1);rows=[]
 for match in re.finditer(r'^\|[\s%|]*\[\[([^\]]+)\]\]\s*\|\s*([^|]+)\|',sec,re.M):
  link=match.group(1);target,_,display=link.partition('|');name=display or target;typ=match.group(2).split(',')[0].strip();rows.append((name,target,typ))
 expected=re.search(r'(?:входят|входило|вошло|вошли)\s+(\d+)\s+насел',sec);num=int(expected.group(1)) if expected else len(rows);assert len(rows)==num,(page['title'],num,len(rows));rosters.append({'qid':q,'municipality':page['title'],'roster_NP_count':len(rows),'roster_section':sec,'article_revision':page['revisions'][0]['revid'],'article_pageid':page['pageid'],'source_path':str(O/'municipal_pages.json.gz'),'source_sha256':sha(O/'municipal_pages.json.gz')})
 claims={}
 for st in entities[q].get('claims',{}).get('P1082',[]):
  am=val(st.get('mainsnak',{}));
  if not isinstance(am,dict):continue
  for dt in st.get('qualifiers',{}).get('P585',[]):
   d=val(dt)
   if not isinstance(d,dict):continue
   y=int(d.get('time','+0000')[1:5]);
   if y in [2010,2021]:claims[y]={'population':float(am['amount']),'declared_date':d.get('time'),'precision':d.get('precision'),'statement_id':st.get('id'),'references_json':json.dumps(st.get('references',[]),ensure_ascii=False)}
 sums={2002:0,2010:0};net={2002:0,2010:0};missing={2002:[],2010:[]};allids=set()
 for name,target,typ in rows:
  names={normalize(name)}|{normalize(n) for n in alias.get(name,[])};typnorm=normalize(typ);typnorm={'дачный поселок':'пгт','рабочий поселок':'пгт'}.get(typnorm,typnorm)
  for y in [2002,2010]:
   cand=old[(old.census_year==y)&old.n.isin(names)]
   if y==2002 and len(cand)>1:cand=cand[cand.district_raw.eq(counties[q])]
   if name=='Санино' and q=='Q4373603' and y==2002:cand=old[(old.census_year==y)&old.n.isin(names)&old.district_raw.eq('Одинцовский район')]
   # Explicit town↔pgt/poselok status changes allowed; other NP types must match.
   compat={'город','пгт','поселок'} if typnorm in {'город','пгт','поселок'} else {typnorm}
   cand=cand[cand.settlement_type.map(normalize).isin(compat)]
   if len(cand)==1:
    r=cand.iloc[0];ids=[r.source_record_id];sums[y]+=float(r.population);net[y]+=0 if r.source_record_id in credit else float(r.population);allids.add(r.source_record_id);status='candidate_unique_name_type_native_row; literal_roster_county_and_sourcecontext_binding_review_pending'
   else:ids=cand.source_record_id.tolist();r=None;missing[y].append(name);status='missing_or_ambiguous_native_source_binding'
   member.append({'municipality':page['title'],'qid':q,'member_name':name,'member_article':target,'member_type':typ,'year':y,'preferred_source_record_id':ids[0] if len(ids)==1 else '', 'candidate_source_IDs_json':json.dumps(ids),'native_population':float(r.population) if r is not None else '', 'population_quality':r.population_value_quality if r is not None else '', 'native_county':r.district_raw if r is not None else '', 'source_file':r.source_file if r is not None else '', 'source_locator':r.source_record_id if r is not None else '', 'already_in_final_mixed_ID_union':bool(r is not None and r.source_record_id in credit),'binding_status':status})
 # Any merger/removal stated in history requires explicit historical roster expansion, so completeness is not inferred from current roster.
 history='\n'.join(l for l in text.splitlines() if re.search('200[0-9]|201[0-2]|объедин|упразд|включ|перевед',l));changes=[]
 if q=='Q4373600':changes.append('2011sanatoria33/14mergers require formerNP source members beyond publishedcurrentroster')
 if q=='Q4373603':changes.append('Sanino transferred2010 fromOdintsovo; oldercounty specialbinding explicitly required')
 group.append({'qid':q,'municipality':page['title'],'published_roster_NPs':len(rows),'unique_native2002_sum_conditional':sums[2002],'unique_native2010_sum_conditional':sums[2010],'net_new_selected2002_conditional':net[2002],'net_new_selected2010_conditional':net[2010],'missing_or_ambiguous2002_json':json.dumps(missing[2002],ensure_ascii=False),'missing_or_ambiguous2010_json':json.dumps(missing[2010],ensure_ascii=False),'municipal2010_secondary_census_claim':claims.get(2010,{}).get('population',''),'municipal2021_secondary_census_claim':claims.get(2021,{}).get('population',''),'municipal_census_claim_witness_json':json.dumps(claims,ensure_ascii=False),'native_sum2010_minus_secondary_municipal':sums[2010]-claims.get(2010,{}).get('population',0),'historical_roster_change_flags':';'.join(changes),'history_excerpt':history[:3500],'all_current_roster_native_rows_uniquely_found_bothyears':not missing[2002] and not missing[2010],'candidate_only':True,'admitted_gain':0})
pd.DataFrame(rosters).to_csv(O/'literal_municipal_rosters.csv',index=False);pd.DataFrame(member).to_csv(O/'municipal_roster_native_member_candidates.csv',index=False);pd.DataFrame(group).to_csv(O/'municipal_closed_scope_feasibility.csv',index=False);pins[str(O/'municipal_pages.json.gz')]=sha(O/'municipal_pages.json.gz');pins[str(O/'municipal_entities.json.gz')]=sha(O/'municipal_entities.json.gz');(O/'source_manifest.json').write_text(json.dumps(pins,indent=2,ensure_ascii=False));print(pd.DataFrame(group)[['municipality','published_roster_NPs','net_new_selected2002_conditional','net_new_selected2010_conditional','missing_or_ambiguous2002_json','missing_or_ambiguous2010_json','municipal2021_secondary_census_claim']].to_string(index=False))
