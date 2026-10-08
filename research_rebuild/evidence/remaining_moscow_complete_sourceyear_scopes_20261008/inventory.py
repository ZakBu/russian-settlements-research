from pathlib import Path
import json,gzip,re,pandas as pd
D=Path(__file__).parent;E=D.parent;entities={};pages={};origins={}
for base,ef,pf in [(E/'moscow_large_residual_actionable_20261008','municipal_entities.json.gz','municipal_pages.json.gz'),(D,'missing_municipal_entities.json.gz','missing_municipal_pages.json.gz'),(D,'klenovskoye_entities.json.gz','klenovskoye_title_resolution_pages.json.gz')]:
 if not (base/ef).exists():continue
 for q,e in json.load(gzip.open(base/ef,'rt'))['entities'].items():entities[q]=e;origins[q]=(str(base/ef),str(base/pf))
 for p in json.load(gzip.open(base/pf,'rt'))['query']['pages'].values():
  if p.get('pageprops',{}).get('wikibase_item'):pages[p['pageprops']['wikibase_item']]=p
admitted={}
for folder in ['complete_transferred_municipal_scope_application_20261008','moscow_complete_scope_mass_application_20261008','sourceyear_scopes_followup_application_20261008']:
 for r in pd.read_csv(E/folder/'accepted_transferred_municipal_scope_observations.csv').drop_duplicates('municipal_entity').itertuples():admitted[r.municipal_entity]=(r.scope_id,folder,r.settlement_name)
# Sourceyear2021 New Moscow consists of21 municipal territories, not current2024successor districts.
all21=['Внуковское','Воскресенское','Десёновское','Кокошкино','Марушкинское','Московский','Мосрентген','Рязановское','Сосенское','Филимонковское','Щербинка','Троицк','Вороновское','Клёновское','Киевский','Краснопахорское','Михайлово-Ярцевское','Новофёдоровское','Первомайское','Роговское','Щаповское']
rows=[];rosters={}
for name in all21:
 qs=[q for q,e in entities.items() if name.lower().replace('ё','е') in e.get('labels',{}).get('ru',{}).get('value','').lower().replace('ё','е')]
 aq=[q for q,v in admitted.items() if name.lower().replace('ё','е') in v[2].lower().replace('ё','е')]
 q=aq[0] if aq else qs[0] if len(qs)==1 else ''
 row=dict(municipality_2021=name,qid=q,already_admitted=q in admitted,accepted_scope_id=admitted.get(q,[''])[0],candidate_only=True)
 if q in entities:
  e=entities[q];p=pages[q];t=p['revisions'][0]['slots']['main']['*'];claims={}
  for st in e.get('claims',{}).get('P1082',[]):
   for dt in st.get('qualifiers',{}).get('P585',[]):
    v=dt.get('datavalue',{}).get('value',{});y=int(v.get('time','+0000')[1:5])
    if y in [2002,2010,2021]:claims[y]=dict(population=float(st['mainsnak']['datavalue']['value']['amount']),time=v['time'],statement_id=st['id'],references=st.get('references',[]))
  section=re.search(r'^== (?:Насел[её]нные пункты|Состав поселения) ==\s*([\s\S]*?)(?=^== |\Z)',t,re.M)
  literal=[]
  if section:
   for mat in re.finditer(r'^\s*\|[\s%|]*\[\[([^\]]+)\]\][^|\n]*\|\s*([^|]+)\|',section.group(1),re.M):
    a,_,b=mat.group(1).partition('|');literal.append(dict(name=b or a,type=mat.group(2).strip().split(',')[0]))
  row.update(claims_json=json.dumps(claims,ensure_ascii=False),municipal_page_revision=p['revisions'][0]['revid'],literal_roster_count=len(literal),has_own_municipal_P625=bool(e.get('claims',{}).get('P625')),entity_source=origins[q][0],page_source=origins[q][1]);rosters[q]=literal
 rows.append(row)
pd.DataFrame(rows).to_csv(D/'all21_municipality_inventory.csv',index=False)
(D/'remaining_literal_rosters.json').write_text(json.dumps({q:v for q,v in rosters.items() if q not in admitted},ensure_ascii=False,indent=2))
print(pd.DataFrame(rows)[['municipality_2021','qid','already_admitted','literal_roster_count']].to_string(index=False))
for r in rows:
 if not r['already_admitted']:print(r['municipality_2021'],r.get('claims_json',''))
