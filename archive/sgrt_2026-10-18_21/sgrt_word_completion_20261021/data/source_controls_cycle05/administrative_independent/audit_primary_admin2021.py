#!/usr/bin/env python3
from pathlib import Path
import pandas as pd,numpy as np,re,hashlib,json
H=Path(__file__).resolve().parent;R=H.parents[2];D=R/'administration2021_cycle05';P=D/'sources/data-20210118-structure-20150128.csv'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(v):return ' '.join(re.findall('[а-яa-z0-9]+',str(v).casefold().replace('ё','е')))
raw=pd.read_csv(P,header=None,sep=';',encoding='cp1251',dtype=str,keep_default_na=False);raw['row']=np.arange(len(raw))+1;raw['code']=raw[0]+raw[1]+raw[2]+raw[3];raw['code8']=raw[0]+raw[1]+raw[2];raw['namekey']=raw[6].map(norm)
bridge=pd.read_parquet(D/'administrative_center_axis_linkage.parquet');features=pd.read_parquet(D/'administration2021_settlement_features.parquet');axis=pd.read_parquet(R/'axis/full_settlement_axis.parquet');npraw=raw[raw[5].eq('2')&raw[3].ne('000')];seats=raw[raw[5].eq('1')&raw[7].str.strip().ne('')];groups=npraw.groupby([0,'namekey']).groups;checks=[]
def ck(k,v):checks.append(dict(check=k,passed=bool(v)))
ck('raw197743NP155627seatrows_exact',len(raw)==197743 and len(npraw)==155627 and len(seats)==len(bridge))
ck('everyexplicitCentrum_seat_source_row_once',set(seats.row)==set(bridge.raw_CSV_row_1based) and bridge.raw_CSV_row_1based.is_unique)
fail=[];linked=bridge[bridge.center_np_code11.notna()]
for b in bridge.itertuples():
 s=raw.iloc[b.raw_CSV_row_1based-1];ix=groups.get((s[0],norm(s[7])));g=npraw.loc[ix] if ix is not None else npraw.iloc[:0];within=g[g.code8.eq(s.code8)] if b.municipal_level=='lower_settlement_municipality' else g[g.code.str[:5].eq(s.code8[:5])]
 expected=within.iloc[0] if len(within)==1 else (g.iloc[0] if len(within)==0 and len(g)==1 else None)
 if (expected is None)!=(pd.isna(b.center_np_code11)) or (expected is not None and (expected.code!=b.center_np_code11 or expected.row!=b.center_np_raw_CSV_row_1based)):fail.append(b.raw_CSV_row_1based)
ck('independentrawCentrum_typed_subject_and_municipal_scope_choice_allrows',not fail)
rawchecks=[]
for b in linked.itertuples():
 q=raw.iloc[int(b.center_np_raw_CSV_row_1based)-1];rawchecks.append(q[5]=='2' and q[3]!='000' and q.code==b.center_np_code11 and q[6]==b.center_np_typed_name and q[0]==b.TER)
ck('everylinkedNP_actual_rawrow_code_name_subject',all(rawchecks))
accepted=bridge[bridge.axis_id.notna()];am=accepted.merge(axis,left_on='axis_id',right_on='id',suffixes=('_b','_a'),validate='many_to_one');codes=am.oktmo_2021.astype('string');ck('acceptedaxis_native2021NPonly_exact10or11digit_code',am.source_record_id_2021.notna().all() and am.is_additive_source_unit.all() and codes.str.fullmatch(r'\d{10,11}').all() and codes.str.zfill(11).eq(am.center_np_code11).all())
# Read names ourselves: exact normalized full name or removal of a documented NP prefix.
prefs=['п ж/д станции','п ж/д ст','п ж/д рзд','ж/д станция','ж/д разъезд','ж/д ст','ж/д рзд','п при станции','п.ст','п ст','пгт','рп','кп','дп','гп','г','с','д','п','х','аул','а','ст-ца','стца','станица','ст','нп','м','к','сл','снп','ж/д будка','ж/д казарма','ж/д блокпост','разъезд','заимка','зимовье','кордон','починок','выселок','остров','маяк','платформа']
pat=r'^(?:'+ '|'.join(re.escape(v) for v in sorted(prefs,key=len,reverse=True))+r')[.\s]+'
ind_names=[norm(an) in {norm(tn),norm(re.sub(pat,'',str(tn),count=1,flags=re.I))} for an,tn in zip(am['name'],am.center_np_typed_name)]
ck('allaccepted_literalaxisname_independent_sourceprefix_read',all(ind_names))
# Primary NAME1 explicit urban prefixes supersede suffix exceptions, independently.
strongurban={'город':'urban_city','г':'urban_city','пгт':'urban_pgt','поселок городского типа':'urban_pgt','рабочий поселок':'urban_pgt','курортный поселок':'urban_pgt','дачный поселок':'urban_pgt','городской поселок':'urban_pgt'}
classok=[]
for an,tn,code in zip(am.type,am.center_np_typed_name,am.center_np_code11):
 at=norm(an);prefix=str(tn).split()[0];sf=int(str(code)[-3:]);sc='urban_city' if prefix=='г' else ('urban_pgt' if prefix in {'пгт','рп','кп','дп','гп'} else ('urban_city' if 1<=sf<=49 else ('urban_pgt' if 51<=sf<=99 else 'rural')))
 ac=strongurban.get(at,'unspecified' if at in {'','нп','населенный пункт','неизвестно','unknown','поселок'} else 'rural');classok.append(ac=='unspecified' or ac==sc)
ck('allacceptedclass_independent_actual_primaryprefix_first',all(classok))
ck('all173527featureIDs_exact_order',features.id.equals(axis.id) and features.id.is_unique)
for field,mask in [('upper_municipal',accepted.municipal_level.eq('upper_municipality')),('district',accepted.explicit_municipal_district_name),('settlement_municipality',accepted.municipal_level.eq('lower_settlement_municipality')),('any_municipal',pd.Series(True,index=accepted.index))]:
 f=features[f'admin2021_{field}_center_evidence'];ids=set(accepted.loc[mask,'axis_id']);ck(field+'_positiveexact_evidence_no_unknown_asfalse',set(features.loc[f.fillna(False),'id'])==ids and not f.eq(False).any())
ck('featurewitnesscounts_actualacceptedrawseatrows',features.admin2021_accepted_role_witness_rows.equals(features.id.map(accepted.groupby('axis_id').size()).fillna(0).astype('int32')))
ck('rawdates_no_post2021Janstatus_backcast',pd.to_datetime(raw[12],dayfirst=True).max()<=pd.Timestamp('2021-01-01') and features.admin2021_role_2021Jan_not_asserted_unchanged_to_censusOctober.all())
ck('roles_not_physicalinstitutioncounts',features.admin2021_role_is_not_count_of_physical_institutions.all())
result=dict(status='PRIMARY_RAW_ADMIN_ROLE_INDEPENDENTLY_VERIFIED' if all(x['passed'] for x in checks) else 'FIX_REQUIRED',checks=checks,n_failed=sum(not x['passed'] for x in checks),source_sha256=sha(P),raw_CSV_rows=len(raw),raw_typed_NP_rows=len(npraw),explicit_Centrum_rows=len(seats),resolved_NP_role_rows=len(linked),accepted_axis_role_rows=len(accepted),unique_axis_role_NP=accepted.axis_id.nunique(),upper_accepted_role_rows=int(accepted.municipal_level.eq('upper_municipality').sum()),upper_uniqueNP=accepted.loc[accepted.municipal_level.eq('upper_municipality'),'axis_id'].nunique(),scope_choice_mismatches=fail,scope='Independent actual CSV row/name/code/subject/scope and output evidence readback. No physical institution count or October status continuity inferred.',input_hashes={p.name:sha(p) for p in [P,D/'build_admin_center_features.py',D/'administrative_center_axis_linkage.parquet',D/'administration2021_settlement_features.parquet']},audit_code_sha256=sha(Path(__file__)))
(H/'primary_admin2021_independent_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
