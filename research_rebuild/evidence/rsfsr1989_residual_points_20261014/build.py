import pandas as pd,json,hashlib,urllib.request,urllib.parse,re,concurrent.futures
from pathlib import Path
from html.parser import HTMLParser
E=Path(__file__).resolve().parent;S=Path('/workspace/shared/rsfsr1989_residual_points');B=E.parent
class Text(HTMLParser):
 def __init__(self):super().__init__();self.a=[]
 def handle_data(self,d):self.a.append(d)
def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
aliases=[('Халтурин','Орлов','Орлов_(город)','кировская'),('Куйбышев','Болгар','Болгар','татарстан'),('Курловский','Курлово','Курлово','владимирская'),('Даровское','Даровской','Даровской','кировская'),('Красногородское','Красногородск','Красногородск','псковская'),('Абатский','Абатское','Абатское','тюменская'),('Омутинский','Омутинское','Омутинское','тюменская'),('Обьячево','Объячево','Объячево','коми'),('Бельтырский','Бельтирское','Бельтирское','хакасия'),('Кумылженский','Кумылженская','Кумылженская','волгоградская'),('Нижнебаканский','Нижнебаканская','Нижнебаканская','краснодарский')]
def fetch(z):
 old,new,title,reg=z;u='https://ru.wikipedia.org/wiki/'+urllib.parse.quote(title);p=S/(title+'.html')
 try:
  if not p.exists():p.write_bytes(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=45).read())
  t=Text();t.feed(p.read_text());txt=' '.join(' '.join(t.a).split());(S/(title+'.txt')).write_text(txt)
  tokens=[old,new];clips=[]
  for token in tokens:
   for m in list(re.finditer(re.escape(token),txt,re.I))[:12]:clips.append(txt[max(0,m.start()-160):m.end()+250])
  return dict(old=old,new=new,title=title,region=reg,url=u,path=str(p),sha256=h(p),clips=clips)
 except Exception as ex:return dict(old=old,new=new,error=str(ex))
sources=list(concurrent.futures.ThreadPoolExecutor(8).map(fetch,aliases));(E/'published_alias_evidence.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2))
a=pd.read_parquet(B/'rsfsr1989_primary_binding_20261013/primary_bindings.parquet');b=pd.read_parquet(B/'rsfsr1989_integration_20261013/population_1989_selected_long.parquet');ov=json.loads((B/'rsfsr1989_integration_20261013/overlapping_observations.json').read_text());ids=set(b.source_record_id)|{x['alternative_source_record_id']for x in ov};r=a[~a.source_record_id.isin(ids)].copy();r.to_parquet(S/'residual.parquet');c=pd.read_parquet('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet');out=[];candidates=[]
for s in sources:
 if 'error'in s:continue
 q=r[r.source_name_parsed_for_binding==s['old']]
 for _,x in q.iterrows():
  cs=c[(c.settlement_name==s['new'])&(c.region_norm==s['region'])&c.accepted_point_present].copy()
  if x.settlement_type_raw=='г.':cs=cs[cs.settlement_type=='город']
  if s['new']=='Курлово':cs=cs[cs.settlement_type=='город']
  if len(set(cs.root))!=1: candidates.append(dict(source_record_id=x.source_record_id,evidence=s,candidate_roots=sorted(set(cs.root))));continue
  z=cs.sort_values('census_year',ascending=False).iloc[0];d=x.to_dict();d.update(root=z.root,anchor_source_record_id=z.source_record_id,anchor_census_year=int(z.census_year),current_name=z.settlement_name,current_type=z.settlement_type,accepted_latitude=float(z.accepted_latitude),accepted_longitude=float(z.accepted_longitude),binding_status='candidate_published_alias_accepted_core_ownpoint',binding_rule='published_alias_plus_region_and_object_type',identity_evidence_url=s['url'],identity_evidence_sha256=s['sha256'],identity_evidence_locator='Lead/history excerpts in published_alias_evidence.json',coordinate_source_record_id=z.source_record_id,coordinate_source_sha256=z.source_sha256,coordinate_source_locator=z.source_locator,coordinate_source_url='',external_identity_asserted=False,retrospective_current_point_inference=True,historical_boundary_comparability='unknown',decision_status='candidate_pending_excerpt_review');out.append(d)
pd.DataFrame(out).to_parquet(E/'alias_point_candidates.parquet');pd.DataFrame(out).to_csv(E/'alias_point_candidates.csv',index=False);(E/'unresolved_alias_candidates.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2));(E/'receipt.json').write_text(json.dumps(dict(primary_sha256=h(B/'rsfsr1989_primary_binding_20261013/primary_bindings.parquet'),selected_sha256=h(B/'rsfsr1989_integration_20261013/population_1989_selected_long.parquet'),overlap_sha256=h(B/'rsfsr1989_integration_20261013/overlapping_observations.json'),residual_rows=len(r),residual_population=int(pd.to_numeric(r.population_total).sum()),candidate_rows=len(out),candidate_population=sum(int(x['population_total'])for x in out)),indent=2));print([(s['old'],s.get('error','OK'))for s in sources]);print([(x['source_name_parsed_for_binding'],x['root'])for x in out])
