#!/usr/bin/env python3
"""Extract all 2023 Ozon tariff rows using actual drawn row borders.

Uses Poppler word boxes for correct spaces, and PyMuPDF vector rectangles for
actual cell boundaries. Wrapped lines join within their own cell, not by nearest
postal index. A 2022/2023 shared name is a retrieval key, not proven continuity.
Raw PDF/XML and the complete extracted table stay in ignored work/.
"""
import argparse,bisect,collections,csv,hashlib,json,re,subprocess,unicodedata,xml.etree.ElementTree as ET
from pathlib import Path
import pymupdf
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
SHA='2914616d3ca4874ad2e69b2ea31302147088559d02fb46f0f46b152ed2aa30f0'
NS={'x':'http://www.w3.org/1999/xhtml'}
def norm(v):return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',v).casefold().replace('ё','е')).strip()
PREFIXES=['железнодорожная станция','поселок железнодорожной станции','посёлок железнодорожной станции','поселок станции','посёлок станции','поселок городского типа','посёлок городского типа','рабочий поселок','рабочий посёлок','населенный пункт','населённый пункт','сельское поселение','дачный поселок','дачный посёлок','поселок','посёлок','деревня','станица','станция','хутор','село','аул','город','ж/д станция','ж/д ст.','пгт','рп','п.','д.','с.','х.','ст.']
def split_type(name):
 for typ in PREFIXES:
  if norm(name).startswith(norm(typ)+' '):return name[:len(typ)],name[len(typ):].strip()
 return '',name

def join_words(words):
 lines=[]
 for w in sorted(words,key=lambda q:(q['y0'],q['x0'])):
  if not lines or abs(w['y0']-lines[-1][0])>2:lines.append((w['y0'],[w]))
  else:lines[-1][1].append(w)
 return '\n'.join(' '.join(q['text'] for q in sorted(line,key=lambda q:q['x0'])) for _,line in lines)
def write_csv(path,rows,fields=None):
 if fields is None:fields=list(dict.fromkeys(k for r in rows for k in r))
 with path.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--pdf',type=Path,default=ROOT/'work/ecommerce_operations_20261104/sources/tariff_20230906185652.pdf')
 p.add_argument('--pilot',type=Path,default=ROOT/'research/ecommerce_cloud/next_direction_20261103/programme_pilot_row_disposition.csv')
 p.add_argument('--work',type=Path,default=ROOT/'work/ecommerce_operations_20261104')
 p.add_argument('--output',type=Path,default=HERE)
 args=p.parse_args();args.work.mkdir(parents=True,exist_ok=True);args.output.mkdir(parents=True,exist_ok=True)
 assert hashlib.sha256(args.pdf.read_bytes()).hexdigest()==SHA
 xml=args.work/'tariff2023_bbox.html'
 if not xml.exists():subprocess.run(['pdftotext','-bbox-layout',str(args.pdf),str(xml)],check=True)
 doc=pymupdf.open(args.pdf);pages=ET.parse(xml).getroot().findall('.//x:page',NS)
 assert len(doc)==len(pages)==491
 rows=[];audit=[];unassigned=[]
 for page_n,(pdf_page,xml_page) in enumerate(zip(doc,pages),1):
  horizontal=[d['rect'] for d in pdf_page.get_drawings() if d['rect'].height<1 and 145<d['rect'].width<156]
  # The narrow left cell is 85.49..237.94pt across every page. Other two
  # columns' borders are independently checked for the same row boundaries.
  assert all(abs(r.x0-85.49)<.1 and abs(r.x1-237.94)<.1 for r in horizontal)
  edges=sorted(set(round(r.y0,2) for r in horizontal))
  for lo,hi in [(238,486),(485,552)]:
   other=sorted(set(round(d['rect'].y0,2) for d in pdf_page.get_drawings() if d['rect'].height<1 and lo<d['rect'].x0<lo+1 and hi-1<d['rect'].x1<hi))
   assert other==edges,(page_n,lo,'row borders differ')
  bins=[[[],[],[]] for _ in edges[:-1]]
  for w in xml_page.findall('.//x:word',NS):
   q={'text':w.text or '',**{k:float(w.attrib[src]) for k,src in [('x0','xMin'),('x1','xMax'),('y0','yMin'),('y1','yMax')]}}
   cx=(q['x0']+q['x1'])/2;cy=(q['y0']+q['y1'])/2;i=bisect.bisect_right(edges,cy)-1
   if i<0 or i>=len(bins) or cx<85 or cx>552:unassigned.append((page_n,q));continue
   col=0 if cx<238.18 else 1 if cx<485.24 else 2
   bins[i][col].append(q)
  count=0
  for i,cols in enumerate(bins):
   cells=[join_words(c) for c in cols];region,name,postal=[re.sub(r'\s+',' ',x).strip() for x in cells]
   if not any(cells) and edges[i+1]-edges[i]<1:continue  # double header-border fill
   if region=='Регион' and name=='Город':continue
   assert region and name and re.fullmatch(r'\d{6}',postal),(page_n,i,cells)
   typ,base=split_type(name)
   rows.append({'row2023_n':len(rows)+1,'pdf_page':page_n,'row_on_page':i+1,'row_y_min':edges[i],'row_y_max':edges[i+1],'region2023':region,'name2023':name,'type_wording2023':typ,'name_without_type2023':base,'postal_index2023':postal,'name_cell_lines':cells[1].count('\n')+1,'name_cell_text':cells[1]});count+=1
  audit.append({'page':page_n,'table_rows':len(bins),'data_rows':count,'region_border_count':len(edges)})
 assert not unassigned,unassigned[:5]
 write_csv(args.work/'ozon_tariff_geography2023_all.csv',rows)
 write_csv(args.work/'ozon_tariff2023_page_audit.csv',audit)
 with args.pilot.open(newline='') as f:old=list(csv.DictReader(f))
 assert len(old)==258
 keys=collections.defaultdict(list)
 for r in rows:keys[(norm(r['region2023']),norm(r['name_without_type2023']))].append(r)
 matches=[];dispositions=[]
 for o in old:
  rs=keys.get((norm(o['region_source']),norm(o['name_source'])),[])
  dispositions.append({'row2022_n':o['row_n'],'region2022':o['region_source'],'name2022':o['name_source'],'old_candidate_status':o['status'],'old_candidate_type':o['candidate_type'],'matches2023_n':len(rs),'postal_indices2023':'|'.join(sorted(set(r['postal_index2023'] for r in rs))),'match_meaning':'shared normalized name within same source region, after explicit leading-type removal; no automatic 2022 identity or temporal continuity'})
  for r in rs:matches.append({'row2022_n':o['row_n'],'pdf_page2022':o['pdf_page'],'region2022':o['region_source'],'name2022':o['name_source'],'old_candidate_status':o['status'],'old_candidate_type':o['candidate_type'],**r,'identity2022_confirmed':False})
 write_csv(args.output/'pilot_old_names_postal2023.csv',matches)
 write_csv(args.output/'pilot_old_names_postal2023_disposition.csv',dispositions)
 type_comparison=[]
 for r in matches:
  if r['old_candidate_status']=='single_exact_name_candidate_only':
   oldtype=norm(r['old_candidate_type']);newtype={'х.':'хутор','рп':'рабочий поселок'}.get(norm(r['type_wording2023']),norm(r['type_wording2023']))
   type_comparison.append({k:r[k] for k in ['row2022_n','region2022','name2022','old_candidate_type','row2023_n','name2023','type_wording2023','postal_index2023']}|{'type_wording_differs':oldtype!=newtype,'different_wording_is_not_proven_identity_error':True})
 write_csv(args.output/'old_single_name_type_comparison2023.csv',type_comparison)
 postalcounts=collections.Counter(r['postal_index2023'] for r in rows)
 summary={'source_snapshot':'2023-09-06T18:56:52Z','source_pdf_sha256':SHA,'source_pages':len(doc),'extracted_rows':len(rows),'distinct_region_labels':len(set(r['region2023'] for r in rows)),'multiline_name_rows':sum(r['name_cell_lines']>1 for r in rows),'max_name_cell_lines':max(r['name_cell_lines'] for r in rows),'unique_region_name_postal_triples':len(set((r['region2023'],r['name2023'],r['postal_index2023']) for r in rows)),'unassigned_words_n':len(unassigned),'distinct_postal_indices':len(postalcounts),'postal_indices_on_multiple_rows':sum(n>1 for n in postalcounts.values()),'rows_sharing_postal_index':sum(n for n in postalcounts.values() if n>1),'max_rows_sharing_one_postal_index':max(postalcounts.values()),'pilot_old_rows':len(old),'pilot_2023_match_records':len(matches),'pilot_old_rows_match_counts':dict(collections.Counter('zero' if r['matches2023_n']==0 else 'one' if r['matches2023_n']==1 else 'multiple' for r in dispositions)),'old_single_candidate_match_counts':dict(collections.Counter('zero' if r['matches2023_n']==0 else 'one' if r['matches2023_n']==1 else 'multiple' for r in dispositions if r['old_candidate_status']=='single_exact_name_candidate_only')),'parser':'Actual drawn horizontal cell borders and Poppler word boxes; concatenate lines inside each name cell; no nearest-postal assignment.','pymupdf_version':pymupdf.VersionBind,'old_single_name_with_2023_type_wording_difference':sum(r['type_wording_differs'] for r in type_comparison),'source2022_identity_automatically_confirmed':False}
 (args.output/'postal_geography2023_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
