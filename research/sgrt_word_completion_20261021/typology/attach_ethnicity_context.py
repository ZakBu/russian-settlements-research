#!/usr/bin/env python3
"""Attach disclosed aggregate census attributes by independently checked source signatures."""
from pathlib import Path
import hashlib,json,re
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;REPO=ROOT.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е')).strip()
def region(x):return norm(re.sub(r'область|республика|край|автономный округ|автономная|ао|г\.', '',str(x).lower()))
def code(x):
 if pd.isna(x):return None
 s=str(x).strip().removesuffix('.0');return s.zfill(11) if s.isdigit() and len(s) in [10,11] else None
def run():
 source=HERE/'sources/allsettlements_20260925/data_allsettlements_anon_156_v20260925.parquet'
 cols=['object_level','object_name','oktmo','region','mun_upper','mun_lower','population','latitude','longitude','Указавшие национальную принадлежность','Русские (русаки, сибиряки)']
 new=pd.read_parquet(source,columns=cols);new['source_row_1based']=np.arange(len(new))+1
 new=new[new.object_level.eq('Населенный пункт')].copy();new['join_code']=new.oktmo.map(code);new['name_norm']=new.object_name.map(norm);new['region_norm']=new.region.map(region)
 old=pd.read_parquet(REPO/'research/sgrt_national_integration_20261019/core/feature_master.parquet',columns=['id','settlement_name_2021','oktmo_2021','population_2021'])
 a=pd.read_parquet(ROOT/'axis/full_settlement_axis.parquet');a=a.merge(old[['id','settlement_name_2021','oktmo_2021']].rename(columns={'oktmo_2021':'old_code'}),on='id',how='left',validate='one_to_one')
 a['join_code']=a.old_code.fillna(a.oktmo_2021).map(code);a['name_norm']=a.settlement_name_2021.fillna(a.name).map(norm);a['region_norm']=a.region.map(region)
 # Only unique native11-digit code candidates; never trust the old version's row number after content drift.
 unique=new[new.join_code.notna()&~new.join_code.duplicated(False)]
 b=a[['id','join_code','name_norm','region_norm','population_2021']].merge(unique,on='join_code',how='left',suffixes=('_axis','_source'),validate='many_to_one')
 b['population_signature_matches']=b.population_2021.eq(b.population)
 b['name_signature_matches']=[bool(x and y and re.search(r'(?:^| )'+re.escape(x)+r'(?:$| )',y)) for x,y in zip(b.name_norm_axis,b.name_norm_source.fillna(''))]
 b['region_signature_matches']=[bool(x and y and (x in y or y in x)) for x,y in zip(b.region_norm_axis,b.region_norm_source.fillna(''))]
 b['attachment_accepted']=b.population_signature_matches&b.name_signature_matches&b.region_signature_matches&b.source_row_1based.notna()
 joined=b[b.attachment_accepted].set_index('id')
 features=pd.read_parquet(HERE/'settlement_features.parquet');assert features.id.equals(a.id)
 features['ethnicity_context_attachment_verified']=features.id.isin(joined.index)
 for dst,src in [('ethnicity_declared_persons2021_raw','Указавшие национальную принадлежность'),('ethnicity_russian_responses2021_raw','Русские (русаки, сибиряки)')]:
  features[dst]=features.id.map(joined[src]);features[dst.removesuffix('_raw')]=features[dst].where(features[dst]>=0)
 features['ethnicity_suppressed2021']=features.ethnicity_declared_persons2021_raw.eq(-9)|features.ethnicity_russian_responses2021_raw.eq(-9)
 den=features.ethnicity_declared_persons2021.replace(0,np.nan);rus=features.ethnicity_russian_responses2021
 features['share_declared_not_russian_response2021']=1-rus/den
 # Disclosure inconsistencies do not become usable rates.
 invalid=features.share_declared_not_russian_response2021.lt(0)|features.share_declared_not_russian_response2021.gt(1)
 features.loc[invalid,'share_declared_not_russian_response2021']=np.nan
 features['ethnic_nonrussian_majority_among_declared2021']=pd.array(np.where(features.share_declared_not_russian_response2021.notna(),features.share_declared_not_russian_response2021>.5,None),dtype='boolean')
 features['ethnicity_source_date']='2021 census;sourcefile20260925retrieved20261021'
 features['ethnic_composition_explains_demographic_change']=pd.array([pd.NA]*len(features),dtype='boolean')
 features.to_parquet(HERE/'settlement_features.parquet',index=False)
 b[['id','join_code','source_row_1based','population_signature_matches','name_signature_matches','region_signature_matches','attachment_accepted']].to_parquet(HERE/'ethnicity_attachment_ledger.parquet',index=False)
 unused=new[~new.source_row_1based.isin(joined.source_row_1based)].copy();unused.to_parquet(HERE/'latest_source_np_not_attached.parquet',index=False)
 receipt={'status':'SOURCE_CONTEXT_ATTACHED_BY_VERIFIED_SIGNATURE','source_bytes':source.stat().st_size,'source_sha256':sha(source),'source_total_rows':176215,'source_np_rows':len(new),'axis_rows':len(a),'accepted_attachments':len(joined),'usable_declared_response_rates':int(features.share_declared_not_russian_response2021.notna().sum()),'suppressed_attachments':int(features.ethnicity_suppressed2021.sum()),'source_np_not_attached':len(unused),'nonrussian_majority_among_declared2021_positive':int(features.ethnic_nonrussian_majority_among_declared2021.fillna(False).sum()),'inconsistent_rates_held':int(invalid.sum()),'source_version_check':'retrievedParquetSHA7abd7f...matchesstoredlatestSHA;176215actualrowsvs176131catalogdescription;noinplacebytechangeestablished;attachmentstillindependentlysignatureverified','join_rule':'unique11digitnativeOKTMO(+explicit10digitzeropad)+unchangedpopulation+literalname+region;notnewidentityunion','suppression':'raw-9retained;usablesuppressedNaN;unknownnotzero','multiple_ethnic_answers':'categoriesnotadded;ratioRussianrespondentstoallpersonswhodeclaredanynationality;notlanguageorspeech','causal_scope':'onesnapshotethniccompositiondoesnotestablishethnoculturalcause,migrationmechanismorbirthdifference'}
 (HERE/'ethnicity_attachment_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':run()
