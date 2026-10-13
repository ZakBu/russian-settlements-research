"""Freeze native alias/type witnesses; never substitute secondary article counts."""
from pathlib import Path
import pandas as pd, json, hashlib, xlrd, gzip
O=Path(__file__).parent
S=Path('/workspace/scratch/residual-20261013/final')
RAW=Path('/workspace/settlements-raw')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
d=pd.read_parquet(S/'applied_state_observations.parquet'); b=d.set_index('source_record_id')
p=pd.read_parquet(S/'applied_core_point_snapshot.parquet').set_index('source_record_id')
cur=lambda n:'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'+str(n)
cases=[
 ('vostochnoe','2002:1_TOM_01_04.xls:0:10463','2010:009_81f8a0e73c_17._20ДВ_ФО_2010.xls:ДВ:2032',cur(118536),'Восточное_(Охинский_городской_округ)', ['восточный','восточное'], 'Explicit own article17June2004PGT Восточный→село Восточное; native2002 urbanbook Охинский branch, native2010 Oha flanks Колендо/Тунгор/Эхаби distinguish Makarov rival; current Oha ownleaf.'),
 ('ilyinskoe','2002:1_TOM_01_04.xls:0:10486','2010:009_81f8a0e73c_17._20ДВ_ФО_2010.xls:ДВ:2078',cur(118581),'Ильинское_(Сахалинская_область)', ['ильинский','ильинское'], 'Own article explicitly formerly PGT and1946Ильинский; same ownsite Tomarinsky county and native2010 flanks Красногорск/Айнское/Парусное; article2002 count904 supports but does not replace sourcecounts. No precise legalconversiondate claimed.'),
 ('udarnoe','2002:1_TOM_01_04.xls:0:10496','2010:009_81f8a0e73c_17._20ДВ_ФО_2010.xls:ДВ:2113',cur(118634),'Ударное_(Сахалинская_область)', ['ударный','ударное'], 'Own article formername Ударный until2004 and село since2004; Uglegorsky nativebranches and2010Тельновское/Приозерное/Ольховка flanks; ownsite and actual nativecount550 support continuity.'),
 ('sitseva','2002:061_e177b0a77d_Chel_abinskaja1.xls:Sheet1:1239','2010:003_eb441570b1_11._20Урал_ФО_2010.xls:Урал:5445',cur(160782),'Ситцева', ['ситцево','ситцева'], 'Native spelling variant Ситцево/Ситцева: same деревня ownsite and unique regionalltype pairedname leaves, Nязепетровский branch supported nativeflanks and ownarticle samecounty/currentname2002count959. No legalrename asserted.'),
 ('aev','2002:074_44f6c88636_Omskaja.xls:Sheet1:145','2010:008_342f3c208b_16._20Сиб_ФО_2010.xls:Sib:7751',cur(82533),None,['аев','аев аев'], 'Actual native2010 leaf explicitly Аев (Аёв); unique Omsk regionalltype pairedname ruralleaves and Большеуковский county2002/2010/current support writtenalias to accepted2002/current component.'),
 ('bereznik','2002:020_e4f979c6c7_02c_Arxang-new.xls:Sheet1:3358','ARK2010:archive20131022:html_table1_tr3365',cur(89732),'Березник_(муниципальное_образование_«Березницкое»)', ['березник'], '2002 ownnative деревня directly under Березницкий сельсовет with Вежа/Горылец/Задорье flanks; qualified ownarticle explicitly Березницкое administrativecenter and these same neighbors; accepted2010/current село ownsite and corrected OSM ownpoint distinguish distant Филинская деревня and locality rivals. Rural village/selo label difference retained as source terminology; no dated legaltypechange asserted.'),
]
proof=[];edges=[];points=[];pins={str(S/n):sha(S/n) for n in ['applied_state_observations.parquet','applied_core_point_snapshot.parquet']}
def native_raw(sid):
 r=b.loc[sid]; f=RAW/r.source_file
 if ':xls:' in sid:return None
 if '.xls:' not in sid:return None
 parts=sid.split('.xls:',1)[1].rsplit(':',1);sn,row=parts[0],int(parts[1]);w=xlrd.open_workbook(str(f));s=w.sheet_by_index(int(sn)) if sn.isdigit() else w.sheet_by_name(sn);pins[str(f)]=sha(f)
 rows=[{'row_1based':i+1,'cells':s.row_values(i)[:18]} for i in range(max(0,row-14),min(s.nrows,row+12))]
 return dict(source_file=str(f),source_sha256=sha(f),sheet=sn,selected_row_1based=row,selected_raw_cells=s.row_values(row-1)[:18],nearby_raw_rows=rows)
for key,a,z,c,article,names,rule in cases:
 ids=list(dict.fromkeys([a,z,c]));members=d[d.root.isin(b.loc[ids,'root'])];assert members.census_year.nunique()==3
 assert not members.census_year.duplicated().any(),(key,members)
 assert set(members.source_record_id)==set(ids)
 donors=[i for i in ids if i in p.index];assert donors,(key,'no ownpoint')
 region=b.loc[a,'region_norm'];rivals=d[(d.region_norm==region)&d.name_norm.isin(names)]
 art=None
 if article:
  f=O/(article+'.html.gz');assert f.exists();art=dict(path=str(f),sha256=sha(f),url='https://ru.wikipedia.org/wiki/'+article,locator='gzip decoded HTML: own infobox; introductory identity; history; population table',use_conditions='Wikipedia CC BY-SA; secondary identity support, no population replacement')
 prior=None
 if key=='bereznik':
  f=O.parent/'residual_northwest_20261013/bereznik_source_witness.json';pins[str(f)]=sha(f);prior=dict(path=str(f),sha256=sha(f),locators=['native2010_selected_leaf','native2021_selected_leaf','direct_ownprovider_capture_with_rivals'],original_archived_2010_HTML_not_reopened=True)
 if key=='ilyinskoe':
  f=O/'Ильинский_(Сахалинская_область).html.gz';pins[str(f)]=sha(f);prior=dict(path=str(f),sha256=sha(f),locator='gzip decoded HTML: wgTitle=Ильинское (Сахалинская область); canonical URL in returned ownarticle; source alias request Ильинский')
 flanks=[]
 for sid in [a,z]:
  if '.xls:' not in sid:continue
  prefix,row=sid.rsplit(':',1);row=int(row)
  q=d[d.source_record_id.str.startswith(prefix+':')].copy();q['raw_row']=q.source_record_id.str.rsplit(':',n=1).str[-1].astype(int);q=q[q.raw_row.between(row-12,row+12)&~q.source_record_id.eq(sid)]
  for rr in q.to_dict('records'):
   cm=d[(d.root==rr['root'])&(d.census_year==2021)]
   flanks.append(dict(native_sid=rr['source_record_id'],native_name=rr['settlement_name'],current_members=cm[['source_record_id','settlement_name','district_raw']].to_dict('records')))
 for missing in set(ids)-set(donors):
  donor=c if c in donors else donors[0];r=p.loc[donor].to_dict()
  points.append(dict(target_source_record_id=missing,coordinate_source_record_id=donor,latitude=r['latitude'],longitude=r['longitude'],coordinate_admission_status='reviewed_extension_rule_accepted',decision_status='checked_rule_accepted',own_locality_point=True,recipient_point_assigned_to_child=False,admission_allowed=True,point_origin_file=r['point_origin_file'],point_origin_sha256=r['point_origin_sha256'],point_origin_locator=r['point_origin_locator'],point_origin_kind=r['point_origin_kind'],admission_rule=rule+' Explicit reuse of already admitted ownlocality point after independently proved nativeidentity; no new providerIDbinding.',point_temporal_interpretation='Contemporary ownsite representative reused by retrospective continuity inference; exact censusday geometry and populationboundarycomparability unknown',historical_census_coordinate_asserted=False,population_boundary_comparability_asserted=False,external_provider_ID_binding_asserted=False,scope_id=key))
 proof.append(dict(case=key,admission_rule=rule,native_members=b.loc[ids].reset_index().to_dict('records'),raw_witnesses=[native_raw(i) for i in ids],whole_region_alltype_variant_screen=rivals.to_dict('records'),source_order_current_flanks=flanks,existing_ownpoints=p.loc[donors].reset_index().to_dict('records'),own_article=art,additional_frozen_witness=prior,point_reuse='Existing admitted ownsite representative points retained and missing sourceyear uses inferred explicitly; retrospective continuity inference, exact censusday geometry and boundarycomparability unknown',article_count_differences_preserved='Article figures are secondary; protected raw2010 values and raw2002 source values remain unchanged.'))
 component_sets=[set(members[members.root==r].source_record_id) for r in members.root.unique()]
 for left,right in [(a,z),(z,c)]:
  ll=next(g for g in component_sets if left in g);rr=next(g for g in component_sets if right in g)
  if ll is rr:continue
  component_sets.remove(ll);component_sets.remove(rr);component_sets.append(ll|rr)
  edges.append(dict(from_source_record_id=left,to_source_record_id=right,relation='same_place',decision_status='checked_rule_accepted',admission_rule=rule,case=key,source_witness_file=str(O/'identity_witnesses.json')))
(O/'identity_witnesses.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2,default=str))
for e in edges:e['evidence_file']=str(O/'identity_witnesses.json');e['evidence_sha256']=sha(O/'identity_witnesses.json')
pd.DataFrame(edges).to_csv(O/'accepted_identity_edge_delta.csv',index=False)
pd.DataFrame(points).to_csv(O/'accepted_point_use_delta.csv',index=False)
pd.DataFrame([{'case':q['case'],'members':len(q['native_members']),'new_edges':sum(e['case']==q['case'] for e in edges),'ownpoint_count':len(q['existing_ownpoints'])} for q in proof]).to_csv(O/'accepted_connected_series.csv',index=False)
(O/'manifest.json').write_text(json.dumps(dict(status='reviewed_native_alias_ruraltype_rule_accepted',cases=len(cases),new_identity_edges=len(edges),new_point_uses=len(points),input_pins=pins,output_pins={str(O/n):sha(O/n) for n in ['identity_witnesses.json','accepted_identity_edge_delta.csv','accepted_point_use_delta.csv','accepted_connected_series.csv']},no_population_or_quality_or_sourcevalue_changes=True),ensure_ascii=False,indent=2))
print('Accepted',len(cases),'series',len(edges),'actual native edges;',len(points),'explicit ownpoint reuse additions')
