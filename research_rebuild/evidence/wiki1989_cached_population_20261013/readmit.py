exec(open(__file__.replace('readmit.py','extract_cached.py')).read().split('rows=[];pages=0')[0])
df=pd.read_parquet(OUT/'candidate_facts.parquet')
def regnorm(v):
 s=norm(v)
 s=re.sub(r'\b(?:республика|область|край|автономный|автономная|округ|город)\b',' ',s)
 s=re.sub(r'\s+',' ',s).strip()
 return {'чувашия':'чувашская','удмуртия':'удмуртская','еврейская автономная':'еврейская'}.get(s,s)
cache={}
roots_lookup={k:g for k,g in core[core.accepted_point_present.eq(True)&core.is_additive_settlement_record.eq(True)].groupby("root")}
for f,idx in df.groupby(df.source_locator.str.split('#').str[0]).groups.items():
 x=json.load(gzip.open(f,'rt'));pages={p['title']:p for p in x.get('payload',{}).get('query',{}).get('pages',[])}
 validvals={}
 for ii in idx:
  zz=df.loc[ii];ss=pages[zz.article_title].get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('content','');pos=int(zz.source_locator.rsplit('character=',1)[1]);left=ss[:pos];inref=left.rfind('<ref')>max(left.rfind('</ref>'),left.rfind('/>'))
  if not inref:validvals.setdefault(zz.article_title,set()).add(zz.population)
 for i in idx:
  z=df.loc[i];p=pages[z.article_title];s=p.get('revisions',[{}])[0].get('slots',{}).get('main',{}).get('content','');accepted=False;reason='candidate_insufficient_independent_identity'
  pos=int(z.source_locator.rsplit('character=',1)[1]); left=s[:pos]; op=left.rfind('<ref'); cl=max(left.rfind('</ref>'),left.rfind('/>')); inref=op>cl
  if inref:reason='literal_in_reference_not_settlement_population'
  elif len(validvals.get(z.article_title,set()))>1:reason='contradictory_population_values'
  elif z.root and re.search(r'\{\{\s*НП',s,re.I):
   g=roots_lookup.get(z.root,core.iloc[:0])
   for _,c in g.iterrows():
    literal=norm(z.historical_name)==norm(c.name_norm);reg=regnorm(z.region_raw)==regnorm(c.region_norm) and regnorm(c.region_norm) not in {"крым","севастополь"}
    d=None
    if z.latitude and z.longitude and pd.notna(c.accepted_latitude):d=math.hypot((z.latitude-c.accepted_latitude)*111,(z.longitude-c.accepted_longitude)*111*math.cos(math.radians(z.latitude)))
    if literal and reg and (z.article_oktmo==z.oktmo or d is not None and d<=5):accepted=True;reason='literal_name_region_unique_root_independent_article_point_within5km_or_identifier';break
  df.at[i,'decision_status']='accepted' if accepted else 'candidate';df.at[i,'binding_status']=reason
for k,v in {'population_scope':'settlement','population_basis':'UNKNOWN_literal_1989_secondary_article','status_date_basis':'UNKNOWN'}.items():df[k]=v
anchors=core[core.accepted_point_present.eq(True)&core.is_additive_settlement_record.eq(True)].sort_values('census_year',ascending=False).drop_duplicates('root').set_index('root')
df['anchor_source_record_id']=df.root.map(anchors.source_record_id)
df['current_region']=df.root.map(anchors.region_norm)
df['accepted_core_latitude']=df.root.map(anchors.accepted_latitude)
df['accepted_core_longitude']=df.root.map(anchors.accepted_longitude)
df['raw_row']=df.raw_row.map(lambda x:' '.join(x.split()[:89]))
df['source_record_id']=df.source_locator.map(lambda x:'wiki1989:'+hashlib.sha256(x.encode()).hexdigest()[:24])
df.to_parquet(OUT/'candidate_facts.parquet',index=False)
a=df[df.decision_status.eq('accepted')&~df.already_selected].drop_duplicates('root');a['article_to_anchor_distance_km']=a.apply(lambda z:math.hypot((z.latitude-z.accepted_core_latitude)*111,(z.longitude-z.accepted_core_longitude)*111*math.cos(math.radians(z.latitude))),axis=1)
a.to_parquet(OUT/'accepted_additional_facts.parquet',index=False)
summary=dict(candidate_articles=df.article_title.nunique(),accepted_articles=int(df.decision_status.eq('accepted').sum()),accepted_additional_roots=len(a),accepted_additional_population=int(a.population.sum()),scope='NP infobox only for acceptance; exact literal name and region plus unique root plus own article coordinates <=5km or explicit article OKTMO',population_basis='UNKNOWN_literal_1989_secondary_article',gain_status='Provisional; root must reproduce current coverage baseline and anti-join refreshed selected ledger.')
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(summary)
