import sys,json,re,collections
from pathlib import Path
import pandas as pd,xlrd
O=Path(__file__).parent;sys.path.insert(0,str(O));from scan import cn,normalize,sha
f=pd.read_csv(O/'actual_native_raw_source_checks.csv.gz',keep_default_na=False);out=[]
for p,group in f.groupby('source_file'):
 if not p.endswith('.xls'):continue
 b=xlrd.open_workbook(p,on_demand=True)
 for locator,g in group.groupby(group.source_locator.str.extract(r'^sheet=(.*);row1based=',expand=False)):
  sh=b.sheet_by_name(locator);heads=[]
  for rn in range(sh.nrows):
   for v in sh.row_values(rn):
    if not isinstance(v,str):continue
    n=normalize(v)
    if not re.search(r'\bрайон\b|\bмуниципальный округ\b|\bгородской округ\b',n) or re.match(r'^(?:сельсоветы|сельские советы|населенные пункты|село|деревня|поселок|посёлок|хутор)\b',n):continue
    n=re.sub(r'\s*[-–—]\s*(?:все|всего|сельское|городское).*$', '',n);heads.append((rn+1,cn(n),v))
  for z in g.to_dict('records'):
   expected=cn(z.get('selected_sourcecounty_raw',''));rn=int(z['source_locator'].rsplit('=',1)[1]);h=[v for v in heads if v[0]<rn]
   if not expected or not h:continue
   hrn,key,literal=h[-1];out.append({'source_record_id':z['source_record_id'],'source_sha256':z['source_sha256'],'source_file':p,'source_locator':z['source_locator'],'nearest_true_county_caption_row':hrn,'nearest_true_county_caption':literal,'nearest_true_county_key':key,'selected_sourcecounty_key':expected,'nearest_true_county_matches_selected':key==expected})
 b.release_resources()
p=O/'nearest_true_county_hierarchy_checks.csv.gz';pd.DataFrame(out).to_csv(p,index=False,compression={'method':'gzip','mtime':0});bad=[z for z in out if not z['nearest_true_county_matches_selected']];print(json.dumps({'rows':len(out),'mismatches':len(bad),'examples':bad[:5]},ensure_ascii=False));(O/'county_hierarchy_audit_receipt.json').write_text(json.dumps({'rows':len(out),'mismatches':len(bad),'output_sha256':sha(p)},indent=2)+'\n')
