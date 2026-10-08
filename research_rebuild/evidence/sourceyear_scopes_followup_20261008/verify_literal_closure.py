from pathlib import Path
import json,gzip,re
import pandas as pd
O=Path(__file__).parent;p=json.load(gzip.open(O/'municipal_pages.json.gz','rt'))['query']['pages'];m=pd.read_csv(O/'candidate_native_scope_constituents.csv').fillna('');obs=pd.read_csv(O/'candidate_scope_observations.csv');rows=[]
def norm(t):return re.sub(r'[^а-я0-9]','',t.lower().replace('ё','е'))
for scope,g in m[m.year.eq(2010)].groupby('scope_id'):
 q=obs[obs.scope_id.eq(scope)].municipal_entity.iloc[0];page=next(x for x in p.values() if x.get('pageprops',{}).get('wikibase_item')==q);t=page['revisions'][0]['slots']['main']['*'];sec=re.search(r'^== (?:Насел[её]нные пункты|Состав поселения) ==\s*([\s\S]*?)(?=^== |\Z)',t,re.M).group(1);literal=[]
 for match in re.finditer(r'^\|[\s%|]*\[\[([^\]]+)\]\]\s*\|\s*([^|]+)\|',sec,re.M):
  target,_,display=match.group(1).partition('|');literal.append((display or target,match.group(2).strip()))
 assert len(literal)==len(g),(scope,len(literal),len(g));d={(norm(a),b.split(',')[0].strip()):(a,b) for a,b in literal};assert len(d)==len(literal)
 for r in g.itertuples():
  rawname=re.sub(r'^(деревня|посёлок|село)\s+','',r.raw_label.strip());rawtype=r.raw_label.strip().split()[0];rawtype={'посёлок':'посёлок при станции'}.get(rawtype,rawtype) if rawname.startswith('станции ') else rawtype;n=(norm(rawname),rawtype);assert n in d,(scope,rawname,list(d));name,typ=d[n];rows.append(dict(scope_id=scope,year=2010,raw_row_1based=r.raw_row_1based,raw_label=r.raw_label,published_member_name=name,published_member_type=typ,article_revision=page['revisions'][0]['revid'],binding_rule='Exact literal member after e/yo and printed quote/whitespace normalization; whole two-sided raw municipal block',source_record_id=r.source_record_id,raw_count_unknown=r.native_population_quality=='raw_count_blank_unknown_not_zero'))
pd.DataFrame(rows).to_csv(O/'exact_literal2010_roster_to_raw_bindings.csv',index=False)
for fn in ['candidate_scope_observations.csv','sourceyear_scope_changes.csv','legal_literal_rosters_and_scope_changes.txt','generate.py']:
 x=O/fn;x.write_text(x.read_text().replace('Fourraw2010NPcountsareblank','Threeraw2010NPcountsareblank'))
print('verified',len(rows),'whole2010rawmembers; unknowncounts',sum(r['raw_count_unknown'] for r in rows))
