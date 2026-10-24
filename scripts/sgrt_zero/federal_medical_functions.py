#!/usr/bin/env python3
"""Classify dated, address-specific federal F034 care rows using NSI enums.

Inputs must already preserve current registry validity and exact F038 care
addresses. Legal addresses are not a substitute. Every raw care row survives;
service offers are a separate, auditable table. No population or capacity mass.
"""
import argparse,hashlib,json,re,sys
from functools import lru_cache
from pathlib import Path
import xml.etree.ElementTree as ET
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.sgrt_zero.health import explicit_restricted_scope,named_child_only_unit,primary_unit_scope_flags as primary_scope_flags

def clean(v):return '' if v is None or (not isinstance(v,(list,dict)) and pd.isna(v)) else str(v).strip()
def code(v):
 s=clean(v)
 return s[:-2] if s.endswith('.0') else s

def read_enum(path,asof):
 rows=[]
 for e in ET.parse(path).getroot():
  r=dict(e.attrib)
  if r.get('DATE_BEG','0000')<=asof and (not r.get('DATE_END') or r['DATE_END']>=asof):rows.append(r)
 d=pd.DataFrame(rows)
 if d.ID.duplicated().any():raise ValueError('Ambiguous active NSI code: '+str(path))
 return dict(zip(d.ID,d.NAME))

def dictionaries(root,asof='2026-10-23'):
 d={n:read_enum(Path(root)/(n+'.xml'),asof) for n in ['V008','V006','V002']}
 required={'V008':{'11':'первичная доврачебная','12':'первичная врачебная','13':'первичная специализированная','32':'высокотехнологичная'},'V006':{'1':'Стационар','2':'Дневной стационар','3':'Поликлиника'},'V002':{'42':'лечебному делу','57':'общей врачебной практике','58':'общей практике','97':'терапии'}}
 for n,mapping in required.items():
  for k,label in mapping.items():
   if not d[n].get(k,'').startswith(label):raise ValueError('Unexpected NSI semantics '+n+':'+k)
 return d

def classify_row(row,enums):
 vid,condition,profile=[code(row.get(k)) for k in ['MPVID','MPUSL','MPROF']]
 out={'care_type_literal':enums['V008'].get(vid,''),'care_conditions_literal':enums['V006'].get(condition,''),'care_profile_literal':enums['V002'].get(profile,''),'enum_codes_resolved':all([vid in enums['V008'],condition in enums['V006'],profile in enums['V002']])}
 unit_name=clean(row.get('NAM_SPMO'));unit_type=clean(row.get('VID_SPMO'))
 name=' '.join([unit_name,unit_type]);org=clean(row.get('organization_name')) or clean(row.get('NAM_MOP'))
 flags=primary_scope_flags({'subdivision_name':unit_name,'care_profile_literal':out['care_profile_literal']})
 typeflags=primary_scope_flags({'subdivision_name':unit_type,'care_profile_literal':out['care_profile_literal']}) if unit_type else None
 if typeflags:
  for k in ['school_or_preschool_medical_scope_signal','restricted_access_signal','pediatric_only_signal']:
   flags[k]|=typeflags[k]
  # A generic taxonomy is not a positive unit function and cannot overrule a
  # clear named GP. A literal narrow/child type is a contradictory unit scope.
  type_narrow=typeflags['literal_narrow_primary_unit_scope']
  explicit_specialist_type=typeflags['narrow_clinical_domain_literal']
  strong_type=bool(re.search(r'\b(?:фап|фп|овп|воп|цовп|ва|сва)\b|фельдшерско.?акушерск|фельдшерский\s+пункт|амбулатори|общ(?:ая|ей)\s+(?:врачебн[а-я]*\s+)?практик',unit_type,re.I))
  neutral_name=not unit_name or bool(re.fullmatch(r'\s*(?:подразделение|отделение)\s*(?:№\s*)?\d*\s*',unit_name,re.I))
  positive=flags['positive_general_primary_unit_literal'] or (typeflags['positive_general_primary_unit_literal'] and (strong_type or neutral_name))
  flags['positive_general_primary_unit_literal']=positive
  flags['universal_primary_unit_function_unknown']=not positive
  flags['narrow_unit_name_ambiguity_signal']=flags['literal_narrow_primary_unit_scope'] or type_narrow or explicit_specialist_type or not positive
 # Licence profile may aggregate an institution. A children's named unit is
 # not made universally accessible by a family-practice profile on its licence.
 child_only=named_child_only_unit(unit_name) or named_child_only_unit(unit_type)
 restricted=explicit_restricted_scope(name,org) or flags['restricted_access_signal']
 oms_ended=clean(row.get('organization_oms_participation_ended_asof')).lower() in ['true','1']
 narrow=flags['narrow_unit_name_ambiguity_signal']
 flags.update(organization_oms_participation_ended_asof=oms_ended,universal_hospital_suitability_verified=False,medical_need_scope=out['care_profile_literal'] or 'profile_unknown',general_adult_profile_evidence=profile in ['57','58','97'] and not child_only and not restricted,named_child_only_contingent=child_only,explicit_restricted_scope=restricted,restriction_scope_unknown=not bool(org),telemedicine_only=vid in ['14','23','33'])
 general=profile in ['42','57','58','97'];physician_general=profile in ['57','58','97'];fap=bool(re.search(r'фельдшерско.?акушерск|фельдшерский пункт|\bФАП\b',name,re.I))
 services=[]
 def add(k,b):services.append((k,b))
 if vid in enums['V008'] and condition in enums['V006'] and not restricted and not oms_ended and not flags['telemedicine_only']:
  primary_allowed=not (child_only or flags['pediatric_only_signal'] or narrow)
  if primary_allowed and condition=='3' and profile in enums['V002']:
   if (vid in ['1','11','12'] and general) or (fap and vid=='11'):add('medical_basic_primary','NSI_primary_ambulatory_general_profile_or_explicit_FAP')
   if vid=='12' and physician_general:add('medical_physician_primary','NSI_12_ambulatory_adult_therapy_or_general_practice')
  if condition=='1':add('medical_inpatient','NSI_V006_1_explicit_inpatient_condition')
  if condition=='2':add('medical_day_hospital','NSI_V006_2_explicit_day_hospital_condition')
  if vid in ['3','31','32']:add('medical_specialized','NSI_explicit_specialized_not_primary_specialized13')
  if vid=='32':add('medical_hightech_licensed','NSI_V008_32_explicit_hightechnology_not_aggregate3')
 out.update(flags);out['service_codes']='|'.join(k for k,b in services);out['service_bases_json']=json.dumps(dict(services),ensure_ascii=False)
 return out

def classify_frame(frame,enums):
 cols=[c for c in ['MPVID','MPUSL','MPROF','NAM_SPMO','VID_SPMO','organization_name','NAM_MOP','organization_oms_participation_ended_asof'] if c in frame]
 @lru_cache(maxsize=200000)
 def classify_key(key):return classify_row(dict(zip(cols,key)),enums)
 extra=pd.DataFrame([classify_key(tuple(clean(v) for v in values)) for values in frame[cols].itertuples(index=False,name=None)],index=frame.index)
 return pd.concat([frame.drop(columns=[c for c in extra if c in frame]),extra],axis=1)

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--codebooks',type=Path,required=True);p.add_argument('--asof',default='2026-10-23');p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 raw=pd.read_parquet(a.input);enums=dictionaries(a.codebooks,a.asof);d=classify_frame(raw,enums);d.to_parquet(a.output/'care_rows_classified.parquet',index=False)
 ev=[]
 for i,r in d.iterrows():
  for service,basis in json.loads(r.service_bases_json).items():ev.append(dict(source_row_index=i,UIDSPMO=r.UIDSPMO,IDADDRESS=r.IDADDRESS,service_code=service,service_basis=basis,source_year=2026,source_id='FEDERAL_F034_F038_20261023',restriction_scope_unknown=bool(r.restriction_scope_unknown),named_child_only_contingent=bool(r.named_child_only_contingent),medical_need_scope=r.medical_need_scope,general_adult_profile_evidence=bool(r.general_adult_profile_evidence),universal_hospital_suitability_verified=False,observed_flow=False))
 e=pd.DataFrame(ev,columns=['source_row_index','UIDSPMO','IDADDRESS','service_code','service_basis','source_year','source_id','restriction_scope_unknown','named_child_only_contingent','medical_need_scope','general_adult_profile_evidence','universal_hospital_suitability_verified','observed_flow']);e.to_parquet(a.output/'service_evidence_by_care_address.parquet',index=False)
 summary={'asof':a.asof,'care_rows':len(d),'unresolved_enum_rows':int((~d.enum_codes_resolved).sum()),'restricted_rows':int(d.explicit_restricted_scope.sum()),'child_named_rows':int(d.named_child_only_contingent.sum()),'unknown_operator_scope_rows':int(d.restriction_scope_unknown.sum()),'service_rows':e.service_code.value_counts().to_dict(),'source_sha256':hashlib.sha256(a.input.read_bytes()).hexdigest(),'codebook_sha256':{n:hashlib.sha256((a.codebooks/(n+'.xml')).read_bytes()).hexdigest() for n in enums},'NSI_primary_specialized13_not_higher_specialized':True,'NSI_aggregate3_not_hightech':True,'all_raw_care_rows_retained':len(raw)==len(d)}
 (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
