from pathlib import Path
import pandas as pd,numpy as np,json,hashlib,math,xlrd
Z=Path(__file__).parent;A=Z.parent/'main_axis_residual_application68_20261008'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
o=pd.read_parquet(A/'applied_state_observations.parquet').set_index('source_record_id',drop=False);p=pd.read_parquet(A/'applied_point_snapshot.parquet').set_index('target_source_record_id',drop=False);co=pd.read_csv(A/'applied_component_snapshot.csv.gz');D=pd.read_csv(Z/'all58_actual68_residual_membership.csv');rawpath=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet');raw=pd.read_parquet(rawpath);rawsha=sha(rawpath)
cur=lambda i:f'2021:data_allsettlements_anon_156_v20251217.parquet:parquet:{i}'
# Explicit source-local identities: row numbers are publication locators, not classifier codes.
def old(reg,year,n):
 pre={('k',2002):'2002:036_81b258bc42_02c_Krasnodarski-krai.xls:11:',('k',2010):'2010:005_888282bccc_13._20Краснодарский_край_2010.xls:КК:',('r',2002):'2002:040_95a4475637_02c_Rostov_obl.xls:Sheet1:',('r',2010):'2010:004_486e984bdc_12._20Астр_Волгог_Ростов.xls:Южный:',('d',2002):'2002:029_fe8710371d_02c_Dagestan.xls:2002:',('d',2010):'2010:018_8eadc2d6b9_7._20Dag_2010.xls:2010:'}
 return pre[(reg,year)]+str(n)
G=[]
def group(label,reg,olds,current,q,basis):G.append(dict(label=label,ids=[old(reg,y,n) for y,n in olds]+[cur(current)],qid=q,basis=basis))
group('Зональный→Лорис','k',[(2002,36),(2010,1571)],46721,'Q4267064','literal own article 2011 decree534 former-name; printed Krasnodar subordinate proper NP')
group('Заречный Белореченск','k',[(2002,66),(2010,1597)],44983,'Q16016870','printed Belorechensk subordinate city/parish context; same literal typed proper NP and own current county')
group('Первомайский Горячий Ключ','k',[(2002,128),(2010,1647)],46853,'Q4349337','printed Goryachiy Klyuch subordinate Chernomorsky rural district; own coded NP')
group('Барановка Хостинская','k',[(2002,272),(2010,1768)],46904,'Q3326723','printed Hostinsky Baranovsky rural district + 2010 neighboring Hostinsky source block; distinct Lazarev rival retained')
group('Барановка Лазаревская','k',[(2002,225),(2010,1734)],46905,'Q12156079','printed Lazarevsky Kirov rural district + 2010 neighboring source block; distinct Hostinsky rival retained')
group('Октябрьский Краснодар','k',[(2002,32),(2010,1568)],46730,'Q16016961','printed Krasnodar subordinate locality context; exact named hutor and current own native code')
group('Саукдере→Саук-Дере','k',[(2002,1169),(2010,652)],45573,'Q9074815','literal hyphen formatting + own Krymsky M oldavansky parish proper settlement')
group('Уташ поселок','k',[(2002,352),(2010,51)],46792,'Q4478781','proper poselok own coded physical Wiki; distinct hutor Utash retained all source years')
group('Бичевой→Бичевый','k',[(2002,1404),(2010,826)],45778,'Q4087602','own article/coded physical poselok Leningradsky Vostochny parish; native orthographic adjective ending')
group('Северный Петропавловский','k',[(2002,1245),(2010,709)],45627,'Q4412261','printed Petropavlovsky rural district + modern own parish code; all Northern rivals retained')
group('Трудовой Зверево','r',[(2002,29),(2010,4258)],111471,'Q4464377','printed Zverevo Krasnopartizansky selsovet; own proper hutor distinct from prison facility, source counts/quality unchanged')
group('Хуторской→Хуторский','r',[(2002,943),(2010,2630)],109465,'Q4502583','own physical article/coded hutor Kirov parish Zimovnikovsky; literal source spelling suffix')
group('Россошинский1-й→1-йРоссошинский','r',[(2002,898),(2010,2596)],109424,'Q4027962','identical ordinal lexemes reordered + printed Rossoshinsky parish; distinct second hutor retained')
group('Новоселый-1→Новоселый1-й','r',[(2002,2571),(2010,3854)],110912,'Q4325324','identical ordinal lexemes + literal own source Salsky Krucheno-Balkovsky parish')
# Older urban census captions independently distinguish the rural namesake.
G.append(dict(label='пгтМанаскент→пгтМанас',ids=['2002:1_TOM_01_04.xls:0:3541',cur(17341)],qid='Q4280155',basis='urban2002 caption separate rural Manaskent; own Manas dated2002 P1082 claim4872 with source refs; actual current code82635155051; administrative split2005 not asserted boundary equivalence'))
G.append(dict(label='Ачису→Ачи-Су',ids=['2002:1_TOM_01_04.xls:0:3449',cur(17339)],qid='Q4073351',basis='own urban NP literal documented name variants + own current coded physical PGT; source former Izberbash subordinate context'))
for label,n,i,q,b in [
('Гоцатль Большое',2405,18209,'Q4147134','adjective gender source form; own Khunzakh proper selo with small Gotsatl rival excluded'),('Араблинское',719,16748,'Q4068378','actual raw2002 Arab lyar within Derbent own county; already interpreted annotated source name and independent own physical article; Kurakh Arab lyar remains distinct'),('Цияб-Цолода',237,16312,'Q4506016','literal former name Gerzel-Kutan in native source and own physical article; pre2002 relocation context not modern move'),('Гельбах',978,16968,'Q1499222','literal former Verkhny Chir yurt alias + own Kizilyurt county typed village'),('Банайюрт',1549,17446,'Q4077183','own article returned name Banayurt2002; old northern physical village distinct newly formed Akhar, no population transfer'),('Новососитли',2266,18084,'Q4325560','literal native parenthetical spelling Novosasitli + own Kh asavyurt typed physical village'),('Уллутеркеме',781,16801,'Q4474794','literal hyphen formatting + own Derbent typed proper village'),('Львовский1',297,16358,'Q3268255','same ordinal Nr1 + own Babayurt typed NP; numbered siblings excluded'),('Новокрестьяновский',1128,17074,'Q4324286','adjective gender literal source form + own Kizlyar parish typed proper selo'),('Ямансу',1578,17469,'Q4537591','own old northern article former-name Shushiya until2002, dated renaming resolution; newly built Shushiya distinct native code and physical entity'),('Шодрода',394,16440,'Q4525910','literal annotated Shadroda variant + own Botlikh typed proper selo'),('КурортТалги',52,18503,'Q4450385','printed Makhachkala subordinate actual counted NP; own modern physical selo not spa-facility point')]:group(label,'d',[(2002,n)],i,q,b)
group('Дучи старое→Зориотар','d',[(2002,1555),(2010,875)],17451,'Q4193935','literal old village Duchi renamed Zoriotar2013; own dated2002 population claim444/reference; distinct new2013Duchi explicitly excluded')
group('2-еОтделениеСовхозаГерейханова','d',[(2002,1822),(2010,1036)],17700,None,'literal source second department proper published selo + actual own current native/provider code82647425106 FIAS6; parent Gereykhanovskoye different proper source NP and parish retained')
# Wiki property bytes and complete source-native rival observations remain separate immutable witnesses.
es={};ep={};pages={}
for f in sorted(Z.glob('wiki*json')):
 j=json.loads(f.read_text())
 for q,e in j.get('entities',{}).items():es[q]=e;ep[q]=f
 for v in j.get('query',{}).get('pages',[]):
  q=v.get('pageprops',{}).get('wikibase_item')
  if q and not v.get('missing') and 'disambiguation' not in v.get('pageprops',{}):pages[q]=(f,v)
def vals(q,k):return [c.get('mainsnak',{}).get('datavalue',{}).get('value') for c in es.get(q,{}).get('claims',{}).get(k,[])]
def normcode(x):
 try:return str(int(float(x))).zfill(11)
 except:return str(x)
def km(a,b):
 la,lo=map(math.radians,a);lb,lob=map(math.radians,b);h=math.sin((la-lb)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lo-lob)/2)**2;return 6371*2*math.asin(min(1,math.sqrt(h)))
books={};sourcew=[];edges=[];points=[];witness=[];holds=[];dis={};parent={x:x for x in o.root.unique()}
def find(x):
 while parent[x]!=x:x=parent[x]
 return x
def union(a,b):a,b=find(a),find(b);parent[b]=a
# Exact explicit baseline rejection. Root must rebuild this two-node component before these bridges.
badold=old('d',2002,1555);badnew=cur(17471);baseline=Path('/workspace/settlements-work/continuation_20261004/accepted_graph25_bounded_cases_20261005/accepted_identity_edges.parquet');be=pd.read_parquet(baseline,columns=['decision_id','relation','from_source_record_id','to_source_record_id','decision_status','decision_rule']);bad=be[be.from_source_record_id.eq(badold)&be.to_source_record_id.eq(badnew)];assert len(bad)==1
rej=bad.to_dict('records')[0];rej.update(rejection_status='reviewed_rejected_identity_claim_only',reason='Actual named northern Duchi2002 is old Zoriotar; new southern Duchi formed2013. Two distinct physical villages/codes. Exact same-name baseline edge contradicts own dated article.',origin_ledger_path=str(baseline),origin_ledger_sha256=sha(baseline),actual68_component_root=o.loc[badold,'root'],source_witness_file=str(Z/'wiki_own_entities_00.json'),source_witness_sha256=sha(Z/'wiki_own_entities_00.json'))
pd.DataFrame([rej]).to_csv(Z/'reviewed_identity_edge_rejection.csv',index=False)
# Model specific approved split in projection only (no State mutation).
splitroot=o.loc[badold,'root'];assert set(o[o.root.eq(splitroot)].index)=={badold,badnew};o.loc[badnew,'root']=badnew;parent[badnew]=badnew
for g in G:
 ids=set(g['ids']);current=next(i for i in ids if i.startswith('2021:'));assert ids<=set(o.index)
 # Include earlier accepted native members of these exact components; no new endpoints inferred from proximity.
 roots=set(o.loc[list(ids),'root']);members=o[o.root.isin(roots)];ids=set(members.index)
 if members.groupby('census_year').size().max()>1:
  holds.append({'group':g['label'],'reason':'same-year source competitors in proposed component','ids':json.dumps(sorted(ids))});continue
 q=g['qid'];rawrow=int(current.rsplit(':',1)[1]);r=raw.iloc[rawrow-1];code=normcode(o.loc[current,'oktmo']);coded=q and code in [normcode(v) for v in vals(q,'P764')];exactraw=normcode(r.get('oktmo_dadata'))==code and str(r.get('fias_level_dadata'))=='6'
 donor=p.loc[current].to_dict() if current in p.index else None
 if donor:
  anchor=(float(donor['latitude']),float(donor['longitude']));route='actual68 accepted own-point donor; raw current and independent named typed physical article/code retained'
 elif exactraw:
  anchor=(float(r.latitude_dadata),float(r.longitude_dadata));route='actual fullraw2021 exact own native/provider code + proper typed locality FIAS6'
 elif coded and vals(q,'P625'):
  v=vals(q,'P625')[0];anchor=(v['latitude'],v['longitude']);route='independent own physical Wiki entity P764 exact published code + P625'
 else:holds.append({'group':g['label'],'reason':'no independently owned modern physical point','ids':json.dumps(sorted(ids))});continue
 active=p[p.index.isin(ids)];dist=max([km(anchor,(float(x.latitude),float(x.longitude))) for x in active.itertuples()] or [0])
 if dist>5:
  holds.append({'group':g['label'],'reason':'known component own-point disagreement >5km requiring explicit source resolution','distance_km':dist,'ids':json.dumps(sorted(ids))});continue
 for i in sorted(ids):
  dis[i]=(g['label'],'accepted_ordinary_source_identity_and_ownpoint')
  if i!=current and o.loc[i,'root']!=o.loc[current,'root']:
   edges.append(dict(decision_id='SOUTH69-'+hashlib.sha256((i+current).encode()).hexdigest()[:20],relation='same_place',from_source_record_id=i,to_source_record_id=current,from_year=int(o.loc[i,'census_year']),to_year=2021,decision_status='checked_rule_accepted',decision_class='source_typed_alias_and_literal_county_context',decision_rule=g['basis'],evidence_uri=str(Z/'identity_source_witnesses.csv.gz'),population_scope_interpretation='identity only; native populations/quality unchanged; boundary comparability UNKNOWN',qid=q or ''))
   union(o.loc[i,'root'],o.loc[current,'root'])
  if i not in p.index:
   rec=donor.copy() if donor else {};rec.update(target_source_record_id=i,latitude=anchor[0],longitude=anchor[1],coordinate_admission_status='reviewed_extension_rule_accepted',admission_rule='own_modern_representative_point_retrospective_on_independently_source_bound_physical_NP; census-day measurement NOT asserted',coordinate_provenance='retrospective physical continuity inference; historical point measurement UNKNOWN',source_record_id=current,donor_target_source_record_id=current,donor_point_ledger_path=donor.get('point_ledger_path','') if donor else '',donor_point_snapshot_sha256=sha(A/'applied_point_snapshot.parquet'),population_boundary_comparability_asserted=False)
   if not donor:rec.update(point_origin_file=str(rawpath) if exactraw else str(ep[q]),point_origin_sha256=rawsha if exactraw else sha(ep[q]),point_origin_locator=f'raw_parquet_row_1based={rawrow}' if exactraw else f'entities.{q}.claims.P625',point_origin_kind='raw2021_own_coded_typedNP' if exactraw else 'own_physical_Wikidata_P764_P625')
   points.append(rec)
  witness.append(dict(group=g['label'],source_record_id=i,current_source_record_id=current,identity_basis=g['basis'],qid=q or '',wikidata_P764_literal_json=json.dumps(vals(q,'P764'),ensure_ascii=False),wikidata_P31_literal_json=json.dumps(vals(q,'P31'),ensure_ascii=False),wikidata_P131_literal_json=json.dumps(vals(q,'P131'),ensure_ascii=False),wikidata_P1082_claims_json=json.dumps(es.get(q,{}).get('claims',{}).get('P1082',[]),ensure_ascii=False),wiki_source_file=str(ep[q]) if q else '',wiki_source_sha256=sha(ep[q]) if q else '',source_population_preserved=o.loc[i,'population'],source_population_quality_preserved=o.loc[i,'population_value_quality'],current_native_code=code,current_raw_provider_code=str(r.get('oktmo_dadata')),current_raw_provider_name=str(r.get('settlement_dadata')),current_raw_FIAS_level=str(r.get('fias_level_dadata')),current_raw_parish=str(r.get('mun_lower')),current_raw_point_json=json.dumps({'lat':r.get('latitude_dadata'),'lon':r.get('longitude_dadata')},default=str),point_binding_route=route,active_component_max_point_distance_km=dist,boundary_comparability='UNKNOWN',historical_point_measurement='UNKNOWN'))
  if int(o.loc[i,'census_year'])!=2021 and str(o.loc[i,'source_file']).lower().endswith('.xls'):
   x=o.loc[i];f=Path('/workspace/settlements-raw')/x.source_file;parts=i.split(':');sn=parts[-2];rn=int(parts[-1]);bk=books.setdefault(str(f),xlrd.open_workbook(f));s=bk.sheet_by_name(sn) if sn in bk.sheet_names() else bk.sheet_by_index(int(sn));sourcew.append(dict(source_record_id=i,source_file=str(f),source_sha256=sha(f),sheet=s.name,row_1based=rn,literal_cells_json=json.dumps(s.row_values(rn-1),ensure_ascii=False),neighbor_rows_json=json.dumps([{'row':j+1,'cells':s.row_values(j)} for j in range(max(0,rn-6),min(s.nrows,rn+2))],ensure_ascii=False),header_path_json=json.dumps([{'row':j+1,'cells':s.row_values(j)} for j in range(rn-1) if any(t in str(s.row_values(j)) for t in ['район','сельсов','сельский округ','подчин','город'])][-12:],ensure_ascii=False)))
# New Duchi actual modern point: exact current own code + physical article. Reject only its old northern point, retain old2002 own northern point.
q='Q4171378';v=vals(q,'P625')[0];assert normcode(o.loc[badnew,'oktmo']) in [normcode(c) for c in vals(q,'P764')];bp=p.loc[badnew].to_dict();pr=dict(bp);pr.update(rejection_status='reviewed_rejected_coordinate_claim_only',reason='Geo2011 northern old Duchi/Zoriotar physical point applied to new2013 southern Duchi; fullraw Dadata explicitly resolves OTHER published Zoriotar code82639433107',active_point_ledger_sha256=sha(bp['point_ledger_path']));pd.DataFrame([pr]).to_csv(Z/'point_use_rejections.csv.gz',index=False,compression={'method':'gzip','mtime':0})
points.append(dict(target_source_record_id=badnew,latitude=v['latitude'],longitude=v['longitude'],coordinate_admission_status='reviewed_extension_rule_accepted',point_origin_file=str(ep[q]),point_origin_sha256=sha(ep[q]),point_origin_locator=f'entities.{q}.claims.P625',point_origin_kind='own_physical_Wikidata_P764_P625',admission_rule='exact own published code82639498101 + physical village P31/own article explicit formation2013; provider wrong old-Zoriotar binding rejected',coordinate_provenance='modern representative point; date and boundaries UNKNOWN'))
pd.DataFrame(edges).to_csv(Z/'accepted_identity_edge_delta.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(points).to_csv(Z/'accepted_point_use_delta.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(witness).to_csv(Z/'identity_source_witnesses.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(sourcew).drop_duplicates('source_record_id').to_csv(Z/'literal_native_source_support_rows.csv.gz',index=False,compression={'method':'gzip','mtime':0});pd.DataFrame(holds).to_csv(Z/'group_holds.csv',index=False)
# Whole native current rows preserve all literal provider properties used in binding; full regional same-name/type rivals already captured.
used={int(g['ids'][-1].rsplit(':',1)[1]) for g in G}|{17471};rr=raw.iloc[[i-1 for i in sorted(used)]].copy();rr.insert(0,'native2021_source_record_id',[cur(i) for i in sorted(used)]);rr.to_json(Z/'literal_current_raw_binding_rows.json',orient='records',force_ascii=False)
# All58 dispositions. Unlocated old source-year cannot become zero or new-formation claim.
DD=D.copy();DD['disposition']=[dis.get(i,('', 'HOLD_UNRESOLVED_SOURCE_IDENTITY_OR_EVENT'))[1] for i in DD.source_record_id];DD['accepted_group']=[dis.get(i,('', ''))[0] for i in DD.source_record_id];DD['hold_reason']=['' if i in dis else 'No complete positive own source identity/event/point proof in bounded batch; preserve native observation and UNKNOWN missing years' for i in DD.source_record_id];DD.to_csv(Z/'all58_UID_disposition.csv',index=False)
# Read-only finite native union projection; exact specific Duchi split included. No State replay or shared metrics changed.
newpointids={x['target_source_record_id'] for x in points};o['projected_root']=o.root.map(find);touched={find(o.loc[i,'root']) for i in dis};gain=[]
remaining=set(pd.read_csv(A/'applied_remaining_primary.csv.gz',usecols=['source_record_id']).source_record_id)
for rt in touched:
 mm=o[o.projected_root.eq(rt)]
 if set(mm.census_year)!={2002,2010,2021} or len(mm)!=3:continue
 if not mm.is_additive_settlement_record.fillna(False).astype(bool).all() or not np.isfinite(pd.to_numeric(mm.population,errors='coerce')).all():continue
 if not all(i in p.index or i in newpointids for i in mm.index):continue
 for i,x in mm.iterrows():
  if i in remaining:gain.append({'source_record_id':i,'census_year':int(x.census_year),'population':x.population,'projected_root':rt})
pd.DataFrame(gain,columns=['source_record_id','census_year','population','projected_root']).to_csv(Z/'projected_incremental_native_finite_UID.csv.gz',index=False,compression={'method':'gzip','mtime':0})
receipt={'status':'bounded positive packet; requires root exact-edge rejection compositor and independent review before integration','baseline':'actual68','cohort_UIDs':58,'dispositions':DD.disposition.value_counts().to_dict(),'ordinary_edges':len(edges),'point_uses':len(points),'identity_rejections':1,'point_rejections':1,'group_holds':holds,'projected_finite_increment_by_year':{str(y):{'UIDs':len([x for x in gain if x['census_year']==y]),'population':sum(x['population'] for x in gain if x['census_year']==y)} for y in [2002,2010,2021]},'source_values_changed':False,'new_Duchi_2021_only_observed_population':926,'new_Duchi_old_year_counts':'UNKNOWN; entity formation2013, never assign historical old village counts','projection_not_State_replay':True,'input_pins':{str(f):{'sha256':sha(f),'bytes':f.stat().st_size} for f in [A/'applied_state_observations.parquet',A/'applied_component_snapshot.csv.gz',A/'applied_point_snapshot.parquet',A/'applied_remaining_primary.csv.gz',rawpath,baseline]}}
(Z/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False)[:2200])
