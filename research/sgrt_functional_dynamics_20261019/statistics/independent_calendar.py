#!/usr/bin/env python3
"""Independent full calendar audit, resumable by source SHA. No author imports."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
import pyarrow.parquet as pq
R=Path(__file__).resolve().parents[1];B=R.parent;O=Path(__file__).resolve().parent/'wave2';O.mkdir(exist_ok=True)
PIN='bde9b8b129a8be582b66de4e30ed79c9187a8515'
GROUPS={'retail47':('G',{'47'}),'food56':('I',{'56'}),'education85':('P',{'85'}),'health86':('Q',{'86'}),'social8788':('Q',{'87','88'}),'repair95':('S',{'95'}),'personal96':('S',{'96'}),'accommodation55':('I',{'55'}),'finance64to66':('K',{'64','65','66'}),'admin84':('O',{'84'})}
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for v in iter(lambda:f.read(2**20),b''):h.update(v)
 return h.hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def norm(s):
 z=s.astype('string').str.strip();return z.where(z.str.fullmatch(r'[0-9]{10,11}',na=False)).str.zfill(11)
def year_compute(y,axis):
 source=R/f'economy/remote_selected/rfsd_{y}_identity_function_selected.parquet';receipt=R/f'economy/remote_selected/{y}_acquisition.json'
 if not source.exists() or not receipt.exists():return False
 meta=json.loads(receipt.read_text());digest=sha(source)
 if meta.get('pinned_dataset_commit')!=PIN or not meta.get('whole_selected_table_readback'):return False
 assert digest==meta['selected_file_sha256']
 out=O/f'calendar_{y}.parquet';audit=O/f'calendar_{y}_audit.json'
 if out.exists() and audit.exists():
  previous=json.loads(audit.read_text())
  if previous.get('source_sha256')==digest and previous.get('method')=='bounded_batch_relational_v2':return True
 code_to_id=axis.set_index('code').id;columns=list(GROUPS);nraw=0;nvalid=0;nmissing=0;exact=0;inn_arrays=[]
 f=pd.DataFrame(0,index=pd.Index(axis.id,name='id'),columns=columns+['legal_entities'],dtype='int64')
 for batch in pq.ParquetFile(source).iter_batches(batch_size=120000,columns=['inn','oktmo','okved','okved_section','filed']):
  d=batch.to_pandas();nraw+=len(d);valid=d.inn.astype('string').str.fullmatch('[0-9]{10}',na=False);d=d[valid].copy();nvalid+=len(d);inn_arrays.append(d.inn.to_numpy().astype(np.uint64))
  prefix=d.okved.astype('string').str.extract(r'^(\d{2})',expand=False);nmissing+=int((prefix.isna()|d.okved_section.isna()|d.okved_section.eq('')).sum())
  d['id']=norm(d.oktmo).map(code_to_id);d=d[d.id.notna()];exact+=len(d)
  for g,(sec,ps) in GROUPS.items():d[g]=(prefix.loc[d.index].isin(ps)&d.okved_section.eq(sec)).fillna(False)
  d['legal_entities']=1
  counts=d.groupby('id')[columns+['legal_entities']].sum()
  f.loc[counts.index,columns+['legal_entities']]+=counts
 inn=np.concatenate(inn_arrays);assert len(np.unique(inn))==nvalid
 f['diversity']=(f[list(GROUPS)[:7]]>0).sum(axis=1);f=f.reset_index();f['year']=y;f.to_parquet(out,index=False)
 stats={'year':y,'source_sha256':digest,'source_rows':nraw,'valid_inn_rows':nvalid,'invalid_syntax_inn':nraw-nvalid,'missing_classification':nmissing,'exact_entities':exact,'points_with_legal_witness':int(f.legal_entities.gt(0).sum()),'points_with_direct_service_witness':int(f.diversity.gt(0).sum()),'points_with_ge2_direct_groups':int(f.diversity.ge(2).sum()),'points_with_ge3_direct_groups':int(f.diversity.ge(3).sum()),'pin':PIN,'result_sha256':sha(out),'all_142570_axis_rows_preserved':len(f)==142570 and f.id.is_unique,'legal_witness_not_physical_function':True,'method':'bounded_batch_relational_v2'}
 dump(audit,stats);print('Independent year',y,stats['source_rows'],stats['points_with_direct_service_witness'],flush=True);return True
def main():
 axis=pd.read_parquet(B/'anchor_research_20261019/data/point_axis.parquet',columns=['id','oktmo_2021','population_2010','population_2021']);axis['code']=norm(axis.oktmo_2021)
 complete=[y for y in range(2011,2026) if year_compute(y,axis)];summary=[json.loads((O/f'calendar_{y}_audit.json').read_text()) for y in complete];pd.DataFrame(summary).to_csv(O/'independent_calendar_coverage.csv',index=False)
 authorpath=R/'economy/pinned_calendar/point_exact_code_witnesses_2011_2025.parquet';checks=[]
 if authorpath.exists():
  for y in complete:
   a=pd.read_parquet(authorpath,filters=[('year','=',y)]).set_index('id').reindex(axis.id);f=pd.read_parquet(O/f'calendar_{y}.parquet').set_index('id').reindex(axis.id)
   for g in GROUPS:checks.append({'name':f'exact_count_{y}_{g}','pass':bool(np.array_equal(f[g],a[g+'_legal_entities']))})
   checks.append({'name':f'legal_count_{y}','pass':bool(np.array_equal(f.legal_entities,a.legal_entities))});checks.append({'name':f'diversity_{y}','pass':bool(np.array_equal(f.diversity,a.direct_consumer_function_diversity))})
  # Independently classify all fifteen-bit presence/profile trajectories.
  if len(complete)==15:
   masks=[]
   for y in complete:
    f=pd.read_parquet(O/f'calendar_{y}.parquet').set_index('id').reindex(axis.id)
    mask=sum((f[g].gt(0).to_numpy().astype(np.uint16)*(2**i)) for i,g in enumerate(list(GROUPS)[:7]));masks.append(mask)
   masks=np.column_stack(masks);present=masks>0;state=[]
   for profile,pres in zip(masks,present):
    obs=np.flatnonzero(pres);changes=np.count_nonzero(pres[1:]!=pres[:-1]);pc=np.count_nonzero(profile[1:]!=profile[:-1])
    if len(obs)==0:s='no_accepted_service_witness_any_year'
    elif len(obs)==15:s='witness_all_years_unchanged_profile' if pc==0 else 'witness_all_years_changed_profile'
    elif obs[0]>0 and obs[-1]==14 and changes==1:s='first_appearance_without_later_dropout'
    elif obs[0]==0 and obs[-1]<14 and changes==1:s='last_disappearance_without_return'
    elif obs[0]>0 and obs[-1]<14 and changes==2:s='one_internal_witness_episode'
    else:s='intermittent_witness_evidence'
    state.append(s)
   tr=pd.read_parquet(R/'economy/pinned_calendar/point_witness_trajectories_2011_2025.parquet').set_index('id').reindex(axis.id)
   checks.append({'name':'all_point_trajectory_labels','pass':bool(np.array_equal(state,tr.witness_trajectory.to_numpy()))})
   pd.Series(state).value_counts().rename_axis('trajectory').rename('n').reset_index().to_csv(O/'independent_trajectory_summary.csv',index=False)
 dump(O/'CALENDAR_AUDIT.json',{'status':'PASS' if len(complete)==15 and checks and all(x['pass'] for x in checks) else 'PARTIAL_NOT_FINAL','complete_years':complete,'missing_years':sorted(set(range(2011,2026))-set(complete)),'n_checks':len(checks),'checks':checks,'author_result_sha256':sha(authorpath) if authorpath.exists() else None,'independent_code_sha256':sha(Path(__file__)),'scope':'Exact legal point-code observations, fixed 2021 code dictionary; not historical service sites, jobs, catchments or physical closures.'})
 print('Calendar complete inputs',complete,'checks',len(checks),flush=True)
if __name__=='__main__':main()
