from pathlib import Path
import json,hashlib
import pandas as pd
import fitz
R=Path.cwd();D=R/'delivery/cycle07_current_primary_v1/report_v2';B=R/'maps/cycle07_current_primary_binding_v1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
c=json.loads((D/'report_inputs.json').read_text());u=pd.read_parquet(B/'all_units.parquet');ev=pd.read_parquet(B/'all_trajectory.parquet');labels=u[c['view_column']].astype(str).map(lambda k:c['view_semantics'][k]['label']);ev['view_label']=ev.unit_id.map(dict(zip(u.unit_id,labels)))
keys=['view_label','object','period','state'];expected=ev.groupby(keys,dropna=False).size().reset_index(name='n_unit_periods');got=pd.read_csv(D/'all_views_objects_periods_state_counts.csv');pd.testing.assert_frame_equal(expected.sort_values(keys).reset_index(drop=True),got.sort_values(keys).reset_index(drop=True),check_exact=True)
assert got.view_label.nunique()==9 and got.period.nunique()==3
assert sum(got.n_unit_periods)==len(ev)
checks=0
for name,expected_pages in [('SGRT_RESEARCH_REPORT',25),('SUPERVISOR_BRIEF',1)]:
 doc=fitz.open(D/(name+'.pdf'));assert len(doc)==expected_pages
 for p in doc:
  for block in p.get_text('dict')['blocks']:
   for line in block.get('lines',[]):
    for s in line['spans']:
     b=fitz.Rect(s['bbox']);assert b.x0>=-.5 and b.y0>=-.5 and b.x1<=p.rect.width+.5 and b.y1<=p.rect.height+.5;checks+=1
r={'status':'ACCEPTED_ACTUAL_REPORT_AGGREGATE_AND_PAGE_BOUNDS','all_checks_passed':True,'source_object_period_rows':len(ev),'complete_state_count_rows':len(got),'all9views_all3periods_exact':True,'pdf_text_spans_in_page':checks,'scope':'Independent root readback of entire aggregate from admitted raw object-period parquet and bound unit/view metadata, without report producer import. Checks PDF page counts and text bounds, not a substitute for actual visual review.','source_and_output_sha256':{str(p.relative_to(R)):sha(p)for p in [B/'all_units.parquet',B/'all_trajectory.parquet',D/'all_views_objects_periods_state_counts.csv',D/'report_inputs.json',D/'SGRT_RESEARCH_REPORT.pdf',D/'SUPERVISOR_BRIEF.pdf',D/'report_receipt.json']}}
(R/'reviews/cycle07_report_root_readback_v2/admission.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r,ensure_ascii=False))
