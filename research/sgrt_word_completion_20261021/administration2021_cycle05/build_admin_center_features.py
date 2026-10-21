#!/usr/bin/env python3
"""Source-backed January2021 administrative-center roles; no2026backcast."""
from pathlib import Path
import re,json,hashlib,datetime
import numpy as np,pandas as pd
H=Path(__file__).resolve().parent;ROOT=H.parent
CSV=H/'sources/data-20210118-structure-20150128.csv';AXIS=ROOT/'axis/full_settlement_axis.parquet'
COLS=['TER','KOD1','KOD2','KOD3','KC','RAZDEL','NAME1','Centrum','NomDescr','NomAkt','Status','DateUtv','DateVved']
PREFIXES=['п ж/д ст','п ж/д станции','п ж/д рзд','ж/д станция','ж/д ст','ж/д разъезд','ж/д рзд','п при станции','п ст','п.ст','дп','кп','рп','гп','пгт','г','с','д','п','х','аул','а','ст-ца','стца','станица','ст','нп','м','к','сл','снп','ж/д будка','ж/д казарма','ж/д блокпост','разъезд','заимка','зимовье','кордон','починок','выселок','остров','маяк','платформа']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s):return re.sub('[^а-яa-z0-9]+',' ',str(s).casefold().replace('ё','е')).strip()
def basename(s):
 raw=str(s).strip()
 for pref in sorted(PREFIXES,key=len,reverse=True):
  if re.match('^'+re.escape(pref)+r'[.\s]+',raw,flags=re.I):return norm(re.sub('^'+re.escape(pref)+r'[.\s]+','',raw,count=1,flags=re.I))
 return norm(raw)
def sourceclass(suffix):
 n=int(suffix)
 return 'urban_city'if 1<=n<=49 else'urban_pgt'if 51<=n<=99 else'rural'if 101<=n<=999 else'undefined_code_series'
def explicit_source_class(name):
 text=str(name).strip().casefold()
 if re.match(r'^г[.\s]+',text):return 'urban_city'
 if re.match(r'^(пгт|рп|кп|дп|гп)[.\s]+',text):return 'urban_pgt'
 if re.match(r'^(с|д|х|аул|к|м|сл|ст-ца|станица|ж/д)[.\s]+',text):return 'rural'
 return 'unspecified'
def axisclass(t):
 t=norm(t)if pd.notna(t)else''
 if t in {'город','г'}:return 'urban_city'
 if t in {'пгт','поселок городского типа','рабочий поселок','курортный поселок','дачный поселок','городской поселок'}:return 'urban_pgt'
 if t in {'','нп','населенный пункт','неизвестно','unknown','поселок'}:return 'unspecified'
 return 'rural'
def main():
 protocol=json.loads((H/'protocol.json').read_text());before={p:sha(Path(p))for p in protocol['source_sha256']};assert before==protocol['source_sha256']
 d=pd.read_csv(CSV,sep=';',encoding='cp1251',header=None,names=COLS,dtype='string');d['raw_CSV_row_1based']=np.arange(1,len(d)+1);assert d[COLS[:6]].notna().all().all();assert pd.to_datetime(d.DateVved,dayfirst=True).max()<=pd.Timestamp('2021-01-18')
 d['code8']=d.TER+d.KOD1+d.KOD2;d['code11']=d.code8+d.KOD3;d['source_sha256']=sha(CSV);d['source_snapshot']='2021-01-18'
 n=d[d.RAZDEL.eq('2')&d.KOD3.ne('000')].copy();assert n.code11.is_unique;n['typed_name_normalized']=n.NAME1.map(norm);n['basename_normalized']=n.NAME1.map(basename);n['source_normative_code_series_class']=n.KOD3.map(sourceclass);n['source_explicit_name_type_class']=n.NAME1.map(explicit_source_class);n['source_explicit_name_vs_code_series_disagreement']=n.source_explicit_name_type_class.ne('unspecified')&n.source_explicit_name_type_class.ne(n.source_normative_code_series_class);n['source_urban_rural_class']=n.source_explicit_name_type_class.where(n.source_explicit_name_type_class.ne('unspecified'),n.source_normative_code_series_class);n.to_parquet(H/'official20210118_native_np_roster.parquet',index=False)
 seats=d[d.RAZDEL.eq('1')&d.Centrum.notna()&d.Centrum.str.strip().ne('')].copy();seats['municipal_level']=np.where(seats.KOD2.eq('000'),'upper_municipality','lower_settlement_municipality');seats['explicit_municipal_district_name']=seats.NAME1.str.contains('муниципальный район',case=False,na=False);seats['Centrum_typed_normalized']=seats.Centrum.map(norm)
 byreg=n.groupby(['TER','typed_name_normalized']).groups;links=[]
 for _,r in seats.iterrows():
  indices=byreg.get((r.TER,r.Centrum_typed_normalized));g=n.loc[indices]if indices is not None else n.iloc[:0];within=g[g.code8.eq(r.code8)]if r.municipal_level=='lower_settlement_municipality'else g[g.code11.str[:5].eq(r.code8[:5])]
  if len(within)==1:chosen=within.iloc[0];status='exact_typed_Centrum_unique_within_native_municipality_scope'
  elif len(within)>1:chosen=None;status='ambiguous_typed_Centrum_within_municipality'
  elif len(g)==1:chosen=g.iloc[0];status='exact_typed_Centrum_unique_in_native_subject_may_lie_outside_municipality'
  elif len(g)==0:chosen=None;status='Centrum_not_found_as_exact_typed_native_NP'
  else:chosen=None;status='ambiguous_typed_Centrum_in_native_subject'
  row=r.to_dict();row.update(center_np_link_status=status,n_native_NP_typed_name_candidates_in_subject=len(g),n_native_NP_typed_name_candidates_in_own_scope=len(within),center_np_code11=chosen.code11 if chosen is not None else None,center_np_typed_name=chosen.NAME1 if chosen is not None else None,center_np_basename_normalized=chosen.basename_normalized if chosen is not None else None,center_np_source_class=chosen.source_urban_rural_class if chosen is not None else None,center_np_raw_CSV_row_1based=int(chosen.raw_CSV_row_1based)if chosen is not None else None);links.append(row)
 roster=pd.DataFrame(links);roster.to_parquet(H/'official20210118_municipality_center_to_native_NP.parquet',index=False)
 a=pd.read_parquet(AXIS);native=a.source_record_id_2021.notna()&a.is_additive_source_unit.fillna(False);a['code2021_raw']=a.oktmo_2021.astype('string');validcode=a.code2021_raw.str.fullmatch(r'\d{10,11}',na=False);a['code2021_normalized11']=a.code2021_raw.where(validcode).str.zfill(11);a['leading_zero_restored_from_numeric_10digit_native_NP_field']=a.code2021_raw.str.len().eq(10).fillna(False);a['axis_name_normalized']=a.name.map(norm);a['axis_urban_rural_class']=a.type.map(axisclass);axisbycode=a[native&validcode].groupby('code2021_normalized11').groups;accepted=[]
 for _,r in roster.iterrows():
  row=r.to_dict();indices=axisbycode.get(r.center_np_code11);g=a.loc[indices]if indices is not None else a.iloc[:0];row['n_axis_native2021_candidates_for_source_code']=len(g);row['axis_id']=None;row['axis_name']=None;row['axis_native_type']=None;row['axis_link_status']='source_NP_unresolved'if pd.isna(r.center_np_code11)else'no_axis_native2021_exact_code_match'
  if len(g)>1:row['axis_link_status']='ambiguous_axis_native2021_exact_code'
  elif len(g)==1:
   q=g.iloc[0];namesame=q.axis_name_normalized==r.center_np_basename_normalized or q.axis_name_normalized==norm(r.center_np_typed_name);classsame=q.axis_urban_rural_class=='unspecified'or q.axis_urban_rural_class==r.center_np_source_class
   row.update(axis_candidate_id=q.id,axis_candidate_name=q['name'],axis_candidate_type=q.type,source_axis_basename_equal=bool(namesame),source_axis_class_compatible=bool(classsame),leading_zero_restored=bool(q.leading_zero_restored_from_numeric_10digit_native_NP_field))
   if not namesame:row['axis_link_status']='source2021Jan_vs_axis2021_name_conflict_not_backcast'
   elif not classsame:row['axis_link_status']='source2021Jan_vs_axis2021_urban_rural_class_conflict_not_backcast'
   else:row.update(axis_link_status='accepted_exact_native2021_NP_code_literal_name_compatible_class',axis_id=q.id,axis_name=q['name'],axis_native_type=q.type)
  accepted.append(row)
 bridge=pd.DataFrame(accepted);bridge.to_parquet(H/'administrative_center_axis_linkage.parquet',index=False);bridge[bridge.axis_link_status.ne('accepted_exact_native2021_NP_code_literal_name_compatible_class')].to_csv(H/'unresolved_or_conflicting_admin_centers.csv',index=False)
 f=a[['id']].copy();oks=bridge[bridge.axis_id.notna()];upper=set(oks.loc[oks.municipal_level.eq('upper_municipality'),'axis_id']);district=set(oks.loc[oks.explicit_municipal_district_name,'axis_id']);lower=set(oks.loc[oks.municipal_level.eq('lower_settlement_municipality'),'axis_id']);anyseat=set(oks.axis_id)
 for name,ids in [('upper_municipal',upper),('district',district),('settlement_municipality',lower),('any_municipal',anyseat)]:f[f'admin2021_{name}_center_evidence']=pd.array([True if v in ids else None for v in f.id],dtype='boolean')
 f['admin2021_source_snapshot']='2021-01-18';f['admin2021_source_sha256']=sha(CSV);f['admin2021_role_is_not_count_of_physical_institutions']=True;f['admin2021_missing_role_means_unknown_not_no_administration']=True;f['admin2021_role_2021Jan_not_asserted_unchanged_to_censusOctober']=True;f['admin2021_accepted_role_witness_rows']=f.id.map(oks.groupby('axis_id').size()).fillna(0).astype('int32');f.to_parquet(H/'administration2021_settlement_features.parquet',index=False)
 scopes=[]
 for level,g in bridge.groupby('municipal_level'):
  scopes.append({'municipal_level':level,'source_role_rows':len(g),'source_role_rows_resolved_to_native_NP':int(g.center_np_code11.notna().sum()),'role_rows_accepted_axis_native2021':int(g.axis_id.notna().sum()),'unique_axis_NP_role_centers':g.axis_id.nunique(),'source_link_statuses':g.center_np_link_status.value_counts().to_dict(),'axis_link_statuses':g.axis_link_status.value_counts().to_dict()})
 cover=a[['id','region','type','population_2021']].merge(f,on='id',validate='one_to_one');cover['rural_urban_class']=cover.type.map(axisclass);cover['population_size']=pd.cut(cover.population_2021,[-1,0,99,499,1999,9999,np.inf],labels=['zero','1-99','100-499','500-1999','2000-9999','10000+']).astype('object').fillna('unknown')
 for dim in ['region','rural_urban_class','population_size']:
  z=cover.groupby(dim,dropna=False).agg(axis_rows=('id','size'),positive_upper_centers=('admin2021_upper_municipal_center_evidence','sum'),positive_district_centers=('admin2021_district_center_evidence','sum'),positive_lower_centers=('admin2021_settlement_municipality_center_evidence','sum'));z.to_csv(H/f'coverage_by_{dim}.csv')
 assert f.id.is_unique and len(f)==len(a)==173527;assert len(d)==197743 and len(n)==155627;assert all(sha(Path(k))==v for k,v in before.items())
 receipt={'status':'ACTUAL_OFFICIAL_JANUARY2021_ADMIN_CENTER_ROLES_LINKED_PENDING_INDEPENDENT_REVIEW','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha256':before,'inputs_unchanged':True,'code_sha256':sha(Path(__file__)),'source_snapshot':'2021-01-18','latest_source_DateVved':'2021-01-01','all_CSV_rows':len(d),'native_NP_rows':len(n),'municipality_source_rows_with_explicit_Centrum':len(seats),'summary_by_municipal_level':scopes,'positive_upper_role_unique_axis_NP':len(upper),'positive_district_role_unique_axis_NP':len(district),'positive_lower_role_unique_axis_NP':len(lower),'positive_any_role_unique_axis_NP':len(anyseat),'axis_rows':len(f),'source_explicit_type_vs_normative_series_disagreements':int(n.source_explicit_name_vs_code_series_disagreement.sum()),'explicit_primary_NAME1_type_overrides_normative_code_series_for_published_exceptions':True,'source_role_vs_native_NP_not_assumed_from_municipality_name':True,'crossyear_or_codechange_equivalence_inferred':False,'centroid_or_geonames2026_used':False,'population_used_to_choose_identity':False,'source2021_role_not_assumed_october2021_unchanged':True,'role_is_not_physical_institution_count':True,'raw_Status_retained_without_reinterpreting_as_current_annulment_filter':True,'output_files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size}for p in sorted(H.glob('*.parquet'))}|{p.name:{'sha256':sha(p),'bytes':p.stat().st_size}for p in sorted(H.glob('coverage*.csv'))}}
 (H/'administrative_center_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in receipt.items()if k not in ['source_sha256','output_files']},ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
