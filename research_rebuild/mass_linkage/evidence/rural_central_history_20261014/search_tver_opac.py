"""Read-only public OPAC search; writes raw results to a new --output directory."""
import urllib.request,urllib.parse,re,pathlib,json,hashlib,argparse
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
p=pathlib.Path(args.output);p.mkdir(parents=True,exist_ok=False);base='https://opac.tverlib.ru'
html=urllib.request.urlopen(base+'/wlib/',timeout=30).read().decode();url=re.search(r'<script src="([^"]+/enter.js)',html)[1];ent=urllib.request.urlopen(base+url,timeout=30).read().decode();(p/'enter_books.js').write_text(ent);session=re.search(r'var numsean="(\d+)"',ent)[1];user=re.search(r'var identif="([^"]+)"',ent)[1]
queries=["(TI Сельские населенные пункты)","(TI Сельские населённые пункты)","(TI Сельские) AND (PY 1980)","(TI Сельские) AND (PY 1990)","(TI Калининской области) AND (PY 1980)","(TI Тверской области) AND (PY 1990)","(AH перепись) AND (PY 1980)","(AH перепись) AND (PY 1990)","(CA управление статистики) AND (PY 1980)","(TI Сельские) AND (PY 2004)"]
r=[]
for i,q in enumerate(queries):
 a=[('_service','opacfindd.FindView'),('_version','2.5.0'),('session',session),('_str',q),('_showstr',q),('start','0'),('length','100'),('iddb','21'),('query/body',q),('outformList[0]/outform','FULLFRM'),('outformList[1]/outform','LINEORD'),('outformList[2]/outform','UNIMARC'),('userId',user),('$solr','yes'),('_iddb','21'),('$typework','search'),('$typesearch','professional')]
 data={'_action':'execute','_html':'stat','_errorhtml':'error1','_numsean':session,'querylist':'[separator]'.join('<'+k+'>'+v for k,v in a)}
 (p/f'book_query_{i}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
 try:
  b=urllib.request.urlopen(base+'/request',data=urllib.parse.urlencode(data).encode(),timeout=30).read();(p/f'book_result_{i}.txt').write_bytes(b);s=b.decode();n=re.search(r'_size: "(\d+)"',s);ids=re.findall(r'_id: "([^"]+)"',s);row={'q':q,'url':base+'/find?'+urllib.parse.urlencode({'iddb':'21','query':q}),'version':'2.5.0','count':int(n[1]) if n else None,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'ids':ids};r.append(row);print(i,row['count'],ids,flush=True)
 except Exception as e:r.append({'q':q,'error':str(e)});print(i,e,flush=True)
(p/'book_queries_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
