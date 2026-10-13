import json,csv,re,html,math,hashlib,collections,urllib.parse
from pathlib import Path
from html.parser import HTMLParser
import pyarrow as pa,pyarrow.parquet as pq
E=Path(__file__).resolve().parent
class Box(HTMLParser):
 def __init__(self):super().__init__();self.depth=0;self.template='';self.raw=[];self.text=[];self.links=[];self.done=False
 def handle_starttag(self,t,a):
  d=dict(a)
  if t=='table':
   if self.depth:self.depth+=1
   elif not self.done and 'infobox'in d.get('class',''):self.depth=1;self.template=d.get('data-name','')
  if self.depth:
   if t=='a'and 'href'in d:self.links.append(d['href'])
 def handle_data(self,d):
  if self.depth:self.text.append(d)
 def handle_endtag(self,t):
  if t=='table'and self.depth:
   self.depth-=1
   if not self.depth:self.done=True
def norm(s):return' '.join(re.sub('[^а-я0-9]+',' ',s.lower().replace('ё','е')).split())
def namekey(s):
 s=re.sub(r'^(?:город|г\.|село|с\.|деревня|д\.|станица|ст\.|хутор|пос[её]лок(?: городского типа)?|пгт|рп|п\.)\s*','',s.lower().strip());return norm(s.split(' (')[0])
def km(a,b):
 v=list(map(math.radians,[a[0],a[1],b[0],b[1]]));return 6371*2*math.asin(min(1,math.sqrt(math.sin((v[2]-v[0])/2)**2+math.cos(v[0])*math.cos(v[2])*math.sin((v[3]-v[1])/2)**2)))
def coord(href):
 qs=urllib.parse.parse_qs(urllib.parse.urlsplit(html.unescape(href)).query);p=qs.get('params',[''])[0];m=re.match(r'([0-9._]+)_([NS])_([0-9._]+)_([EW])',p)
 if not m:return None
 def dms(s):
  a=[float(z)for z in s.strip('_').split('_')];return a[0]+(a[1]/60 if len(a)>1 else 0)+(a[2]/3600 if len(a)>2 else 0)
 lat=dms(m[1])*(-1 if m[2]=='S'else 1);lon=dms(m[3])*(-1 if m[4]=='W'else 1);return(lat,lon)
rows=json.load(open(E/'residual_filtered.json'));snap=json.load(open(E/'selected_point_snapshot.json'));qids=set(json.load(open(E/'selected_qids.json')));articles=json.load(open(E/'article_receipts.json'));out=[];checks=[]
for x in rows:
 n=x['source_name_parsed_for_binding'];opts=[a for a in articles if a['source_name']==n and 'path'in a and not a.get('already_selected_qid')];accepted=[]
 for a in opts:
  s=(E/a['path']).read_text();q=a.get('qid_matches',[None])[0];b=Box();b.feed(s);box=' '.join(' '.join(b.text).split());text=' '.join(html.unescape(re.sub('<[^>]+>',' ',s)).split());article_links=re.findall(r'href=["\']([^"\']+)',s);own_geo=[u for u in article_links if 'geohack'in u and 'pagename='in u]
  pts=sorted({z for u in own_geo for z in [coord(u)]if z and all(math.isfinite(v)for v in z)and -90<=z[0]<=90 and -180<=z[1]<=180});physical=any(z in box.lower()for z in ['село','посёлок','поселок','город','населённый пункт','населенный пункт','микрорайон'])and not any(z in b.template.lower()for z in ['река','улица','станция','учёный']);former='упразднённый'in text or 'упраздненный'in text or 'бывший посёлок'in text or 'бывший поселок'in text or ('придан статус посёлка городского типа'in text and 'посёлок окончательно вошёл в состав'in text);nameproof=norm(n)in norm(text);region=x['current_region_alias'];stem={'ярославская':'ярославск','москва':'москв','иркутская':'иркутск','липецкая':'липецк','хакасия':'хакаси','чукотский':'чукот','саха якутия':'якут','коми':'коми','бурятия':'бурят','башкортостан':'башкортостан','удмуртская':'удмурт','приморский':'приморск'}.get(region,region);regionproof=stem in norm(box+' '+text[:40000]);maxdist=max([km(p,t)for p in pts for t in pts],default=0);currenttype='село'if 'село'in box.lower()else'поселок'if 'посёлок'in box.lower()or'поселок'in box.lower()else'город'if 'город'in box.lower()else'unknown';source_rural='rus89_reg3'in x['source_record_id'];type_conflict=source_rural and currenttype!='село'and 'станица'not in box.lower();collision=[]
  if len(pts)==1:
   for y in snap:
    if y['latitude']is None or y['longitude']is None:continue
    dd=km(pts[0],(y['latitude'],y['longitude']))
    if dd<0.1 or (dd<=5 and (namekey(y['name'])==namekey(n)or namekey(y['name'])==namekey(a['title'].split(' (')[0]))):collision.append(dict(root=y['root'],qid=y['qid'],name=y['name'],distance_km=dd))
  ok=b.done and physical and ('район'not in b.template.lower()or former)and nameproof and regionproof and len(pts)==1 and not type_conflict and not collision and q not in qids
  if n=='Матырский':ok=False # Valid former-NP point, but parent integration verified this NP already represented by ROOT.
  note=dict(source_record_id=x['source_record_id'],source_name=n,title=a['title'],provider_candidate_id=q,infobox_found=b.done,infobox_template=b.template,infobox_excerpt=box[:1500],own_infobox_points=pts,physical_subject=physical,name_publication_proof=nameproof,region_publication_proof=regionproof,explicit_former_place=former,source_rural_type_conflict=type_conflict,represented_point_collisions=collision,parent_verified_already_represented_root=n=='Матырский',status='accepted'if ok else'held');checks.append(note)
  if ok:accepted.append((a,q,pts[0],note,text))
 if len(accepted)!=1:continue
 a,q,c,note,text=accepted[0];z={k:v for k,v in x.items()if not k.startswith('cached_candidates_')};j=text.lower().find(n.lower(),10000);z.update(root='historical:1989:published-point:'+hashlib.sha256(x['source_record_id'].encode()).hexdigest()[:20],anchor_source_record_id=None,anchor_census_year=None,binding_status='bound_published_np_infobox_physical_point_provider_identity_candidate_only',coordinate_role='published_own_np_infobox_point_historical_reference',accepted_latitude=c[0],accepted_longitude=c[1],external_id='',external_id_candidate=q,external_identity_asserted=False,current_name=a['title'].split(' (')[0],current_region=x['current_region_alias'],individual_2021_census_status='no_individual_2021_census_asserted',binding_rule='primary_np_population+unique_own_physical_np_infobox_point+qualified_publication+no_selected_QID_or_point_collision',coordinate_source_url=a['url'],coordinate_source_sha256=a['sha256'],coordinate_source_locator='own physical-NP article coordinate banner GeoHack params; associated physical infobox',point_identity_grade='published_np_infobox_point_provider_identity_candidate_only',population_basis='present',historical_boundary_comparability='unknown',retrospective_current_point_inference=True,history_source_url=a['url'],history_source_sha256=a['sha256'],history_quote=text[max(0,j-130):j+400]if j>=0 else'');out.append(z)
fields=list(dict.fromkeys(k for z in out for k in z))
with(E/'external_point_delta5.csv').open('w')as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(out)
pq.write_table(pa.Table.from_pylist([{k:z.get(k)for k in fields}for z in out]),E/'external_point_delta5.parquet',compression='zstd');(E/'publication_validation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2));r=dict(rows=len(out),population_total=sum(int(z['population_total'])for z in out),basis='present',population_source='Demoscope only',root_duplicates=len(out)-len({z['root']for z in out}),source_uid_duplicates=len(out)-len({z['source_record_id']for z in out}),selected_QID_overlap=sum(z['external_id_candidate']in qids for z in out),selected_same_name_or_exact_point_collisions=0,provider_identity_asserted=False,outputs={f:hashlib.sha256((E/f).read_bytes()).hexdigest()for f in ['external_point_delta5.csv','external_point_delta5.parquet']},held=[z for z in checks if z['status']=='held']);(E/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in r.items()if k!='held'},ensure_ascii=False,indent=2));print('accepted',[(z['source_name_parsed_for_binding'],z['population_total'])for z in out]);print('held',[(z['source_name'],z['provider_candidate_id'],len(z['own_infobox_points']),z['source_rural_type_conflict'],len(z['represented_point_collisions']))for z in checks if z['status']=='held'])
