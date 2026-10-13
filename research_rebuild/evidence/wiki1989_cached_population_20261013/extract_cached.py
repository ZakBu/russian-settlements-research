import glob,gzip,json,re,hashlib,math,urllib.parse
from pathlib import Path
import pandas as pd
OUT=Path(__file__).parent
core=pd.read_parquet('/workspace/scratch/tochno-enrichment-20261013/applied/integrated_spatial_temporal_records.parquet')
selected=pd.read_parquet('/workspace/russian-settlements-research/research_rebuild/evidence/rsfsr1989_integration_20261013/population_1989_selected_long.parquet')
covered=set(selected.root)
def norm(s):return re.sub(r'[^а-яa-z0-9]+',' ',str(s).lower().replace('ё','е')).strip()
def param(s,k):
 m=re.search(r'\|\s*'+k+r'\s*=([^\n|}]*)',s,re.I);return m.group(1).strip() if m else ''
def coord(s,p):
 try:return sum(float(param(s,p+'_'+k) or 0)/d for k,d in [('deg',1),('min',60),('sec',3600)])
 except:return None
rows=[];pages=0
patterns=[('year_template',r'\|\s*1989\s*=\s*([\d][\d \u00a0]*)(?=\s*(?:\||\n|}|<))'),('year_dash',r'(?<!\d)1989\s*(?:\]\])?\s*(?:году?|г\.)?\s*(?:\]\])?\s*[—–-]\s*([\d][\d \u00a0]*)(?=\s*(?:[;,<]|чел|жител|\n|\bв\b))'),('number_year',r'(?<!\d)(\d[\d \u00a0]*)\s*\(1989(?:\s*год)?\s*[,)]'),('year_people',r'(?<!\d)1989\s*(?:\]\])?\s*(?:году?|г\.)?\s*(?:проживало|осталось|насчитывалось|жило)\s*([\d][\d \u00a0]*)\s*(?:чел|жител)')]
patterns.append(('year_named_narrative',r'(?<!\d)1989[^\d\n]{0,260}?(?:прожива(?:л[аои]?|ло)|здесь)\s*(\d[\d \u00a0]*)\s*(?:чел|жител)'))
lookup={k:g for k,g in core[core.oktmo.notna()].groupby('oktmo')}
for f in sorted(glob.glob('/workspace/shared/wiki1989-cached/data/raw/wikipedia_articles/*.gz')):
 x=json.load(gzip.open(f,'rt'));req={r['article_title']:r for r in x.get('requested',[])};sha=hashlib.sha256(Path(f).read_bytes()).hexdigest()
 for p in x.get('payload',{}).get('query',{}).get('pages',[]):
  pages+=1
  for r in p.get('revisions',[]):
   s=r.get('slots',{}).get('main',{}).get('content',''); hits=[]
   if '1989' not in s:continue
   for method,pat in patterns:
    for m in re.finditer(pat,s):
     v=int(re.sub(r'\s','',m.group(1)));context=s[max(0,m.start()-200):m.end()+200]
     if v<=0 or v>15000000:continue
     if method=='number_year' and not re.search('населен|числен|жител|человек',s[max(0,m.start()-1000):m.end()],re.I):continue
     hits.append((v,method,m.start(),context))
   for tm in re.finditer(r'\{\|[\s\S]*?\|}',s):
    table=tm.group(0)
    if '1989' not in table or not re.search('населен|количество жителей',table,re.I):continue
    parts=re.split(r'\n\|-.*\n',table)
    for j,part in enumerate(parts[:-1]):
     headers=re.findall(r'(?<!\d)(?:18|19|20)\d{2}(?!\d)',re.sub(r'<ref[^>]*>.*?</ref>|<ref[^>]*/>','',part,flags=re.S))
     if '1989' not in headers or len(headers)<2:continue
     nxt=parts[j+1];clean=re.sub(r'<ref[^>]*>.*?</ref>|<ref[^>]*/>','',nxt,flags=re.S)
     cells=[]
     for line in clean.splitlines():
      if not line.startswith('|') or line.startswith(('|-','|}')):continue
      for cell in line[1:].split('||'):
       val=cell.rsplit('|',1)[-1].strip()
       if re.fullmatch(r'\d[\d \u00a0]*',val):cells.append(int(re.sub(r'\s','',val)))
     if len(cells)==len(headers):
      value=cells[headers.index('1989')]
      if value>0:hits.append((value,'wikitable_year_column',tm.start(),table[:1500]))
   if not hits:continue
   vals=set(h[0] for h in hits);item=req.get(p['title'],{});oktmo=item.get('settlement_id','').replace('RU-OKTMO-','');g=lookup.get(oktmo);name=param(s,'русское название') or re.sub(r'\s*\(.*','',p['title']);lat=coord(s,'lat');lon=coord(s,'lon');articleoktmo=param(s,'ОКТМО') or param(s,'oktmo');region=param(s,'регион');roots=set() if g is None else set(g.root.dropna());accepted=False;reason='requested_identifier_only_candidate';root=next(iter(roots)) if len(roots)==1 else None
   if len(vals)>1:reason='contradictory_population_values'
   elif root and re.search(r'\{\{\s*НП',s,re.I):
    gg=g[g.root.eq(root)&g.accepted_point_present.eq(True)]
    for _,c in gg.iterrows():
     literal=norm(name)==norm(c.name_norm)
     reg=norm(region)==norm(c.region_norm)
     d=None
     if lat and lon and pd.notna(c.accepted_latitude):
      d=math.hypot((lat-c.accepted_latitude)*111,(lon-c.accepted_longitude)*111*math.cos(math.radians(lat)))
     if literal and reg and (articleoktmo==oktmo or d is not None and d<=5):accepted=True;reason='literal_name_region_unique_root_independent_article_point_or_identifier';break
   for v,method,pos,context in hits:
    rows.append(dict(root=root,article_title=p['title'],historical_name=name,region_raw=region,oktmo=oktmo,article_oktmo=articleoktmo,population=v,year=1989,population_scope='settlement',population_basis='UNKNOWN_literal_1989_secondary_article',status_date_basis='UNKNOWN',source_kind='wikipedia_cached_literal',source_url='https://ru.wikipedia.org/w/index.php?oldid='+str(r['revid']),source_locator=f+'#pageid='+str(p['pageid'])+';character='+str(pos),source_sha256=sha,revision_sha1=r.get('sha1'),raw_row=context,extraction_method=method,latitude=lat,longitude=lon,decision_status='accepted' if accepted else 'candidate',binding_status=reason,already_selected=root in covered,retrospective_current_point_inference=True))
df=pd.DataFrame(rows).drop_duplicates(['article_title','population']);df.to_parquet(OUT/'candidate_facts.parquet',index=False)
a=df[df.decision_status.eq('accepted')&~df.already_selected].drop_duplicates('root');a.to_parquet(OUT/'accepted_additional_facts.parquet',index=False)
summary=dict(pages_scanned=pages,candidate_articles=df.article_title.nunique(),candidate_population=int(df.population.sum()),accepted_additional_roots=len(a),accepted_additional_population=int(a.population.sum()),decisions=df.decision_status.value_counts().to_dict(),note='Gain is provisional: current coverage baseline reproduction remains root responsibility. Wikipedia secondary evidence; census provenance not individually verified.')
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(summary)
