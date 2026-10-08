import pandas as pd,json,re,urllib.request,urllib.parse,hashlib,concurrent.futures,datetime
from pathlib import Path
O=Path(__file__).parent;d=pd.read_csv(O/'source_binding_screen.csv',dtype={'old_raw_code':str});p=pd.read_csv(O/'existing_full3_point_conflicts.csv');todo=[]
for z in d.to_dict('records'):
 cur=p[(p.root==z['root'])&(p.year==2021)].iloc[0];w=json.loads(z['independent_witnesses'])
 if len(w)==1 and w[0]['name_exact'] and not w[0]['competition'] and z['old_raw_code'] in json.loads(w[0]['okato']):
  todo.append((z,w[0],json.loads(cur.point_json)))
def fetch(t):
 z,w,p=t;url=json.loads(w['url'])[0]
 try:
  body=urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'settlement-research/1.0'}),timeout=12).read();html=body.decode();m=re.search(r'"latitude":"([0-9.-]+)","longitude":"([0-9.-]+)"',html);mov=[re.sub('<[^>]+>',' ',html[max(0,x.start()-150):x.end()+250]) for x in re.finditer('перенес[её]н|пересел[её]н|затоплен',html,re.I)]
  return {**z,'article_url':url,'article_sha256':hashlib.sha256(body).hexdigest(),'article_latitude':float(m[1]) if m else None,'article_longitude':float(m[2]) if m else None,'retrieved_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'possible_movement_snippets_json':json.dumps(mov[:8],ensure_ascii=False),'current_point_kind':p.get('point_origin_kind'),'qid':w['qid']}
 except Exception as e:return {**z,'article_url':url,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as e:r=list(e.map(fetch,todo))
f=pd.DataFrame(r);f.to_csv(O/'own_article_coordinate_checks.csv',index=False);print(f[['name','article_latitude','article_longitude','current_point_kind','possible_movement_snippets_json']].to_string(index=False))
