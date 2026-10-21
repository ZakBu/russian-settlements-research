"""Independent actual atlas byte, PDF bounds, index and page-source checks."""
import json,hashlib,sys
from pathlib import Path
import pandas as pd,numpy as np,fitz
B=Path(__file__).resolve().parents[2];O=Path(__file__).parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
atlas=Path(sys.argv[1]);receipt=json.loads((atlas/'atlas_receipt.json').read_text());expected=json.loads((O/'expected_source_counts.json').read_text());views={x['view_id']:x for x in expected['views']};checks=[];failed=[];pages=[]
def ck(k,v):
 checks.append(k)
 if not bool(v):failed.append(k)
ck('source_config_same_as_independent_expected',receipt['config_sha256']==expected['config_sha256']);ck('all_watched_sources_match',all(sha(p)==v for p,v in receipt['sources'].items()));ck('main_budget',receipt['main_page_budget_met'])
for vol,r in receipt['volumes'].items():
 d=atlas/vol;pdf=fitz.open(d/'atlas_cycle07.pdf');index=pd.read_csv(d/'machine_map_index.csv');ck(vol+'_page_counts',len(pdf)==len(index)==r['page_count']==len(r['pages']));ck(vol+'_all_files_exact',all(sha(d/p)==s for p,s in r['files'].items()));ck(vol+'_consecutive_index',index.page.tolist()==list(range(1,len(index)+1)));tc=pd.read_csv(d/'type_counts.csv');ck(vol+'_type_counts_table_present',len(tc)>0)
 for page in r['pages']:
  pp=pdf[page['page']-1];idx=index[index.page.eq(page['page'])].iloc[0];ck(vol+str(page['page'])+'_PNGhash',sha(d/page['png'])==page['sha256']);ck(vol+str(page['page'])+'_titleboundsflag',page['title_bbox_within_page']);ck(vol+str(page['page'])+'_indexpng',idx.png==page['png']);badbounds=[];fonts=[]
  for block in pp.get_text('dict')['blocks']:
   for line in block.get('lines',[]):
    for span in line['spans']:
     if not span['text'].strip():continue
     x0,y0,x1,y1=span['bbox'];fonts.append(span['size'])
     if x0 < -1 or y0 < -1 or x1>pp.rect.width+1 or y1>pp.rect.height+1:badbounds.append({'text':span['text'][:90],'bbox':span['bbox']})
  ck(vol+str(page['page'])+'_allPDFtextwithinpage',not badbounds)
  v=page.get('resolution');pagechecks={}
  if v:
   ex=views[v];meta=ex['metadata'];pagechecks['index_kind']=idx.resolution_kind==meta['resolution_kind'];pagechecks['index_sourceSHA']=idx.source_sha256==meta['source_sha256'];pagechecks['index_partition']=idx.partition_role==meta['partition_role']
   if 'n_membership_rows' in page:pagechecks['all_members_retained']=page['n_membership_rows']==ex['n_membership_rows'];pagechecks['coordinate_missing_exact']=page['missing_coordinates']==ex['missing_coordinates']
   for key in ['territorial_visual_group_counts','atomic_visual_group_counts','atomic_source_frame_counts']:
    if key in page:pagechecks[key]=page[key]==ex[key]
   if 'selections' in page:
    for z in page['selections']:
     zz=next(q for q in expected['city_zooms'] if q['anchor_id']==z['anchor_id']);pagechecks[z['anchor_name']+'_exact_membership']=all(z[k]==zz[k] for k in ['anchor_name','unit_id','n_members']);cr=z['cartographic_reference'];pagechecks[z['anchor_name']+'_true_scale']=np.isclose(cr['distance_km'],cr['measured_geodesic_km'],rtol=1e-8,atol=1e-8)
   for k,val in pagechecks.items():ck(vol+str(page['page'])+'_'+k,val)
  pages.append({'volume':vol,'page':page['page'],'title':page['title'],'png':str(d/page['png']),'png_sha256':page['sha256'],'kind':page['kind'],'source_checks':pagechecks,'pdf_text_outside_page':badbounds,'smallest_font_points':min(fonts) if fonts else None,'visual_personally_inspected':False})
 pdf.close()
r={'status':'SOURCE_AND_PDF_BOUNDS_PASS_PENDING_PERSONAL_EVERY_PAGE_VISUAL' if not failed else 'REJECTED_PRESENTATION_OR_BINDING','all_checks_passed':not failed,'n_checks':len(checks),'n_failed':len(failed),'checks':checks,'failures':failed,'atlas_receipt_sha256':sha(atlas/'atlas_receipt.json'),'expected_source_counts_sha256':sha(O/'expected_source_counts.json'),'n_pages':len(pages),'pages':pages,'code_sha256':sha(__file__)};(O/'source_and_pdf_bounds_audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2,default=lambda x:x.item()));print(r['status'],len(checks),failed)
