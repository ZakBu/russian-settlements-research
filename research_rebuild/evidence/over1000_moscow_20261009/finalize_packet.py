import pandas as pd,json,hashlib,pathlib
O=pathlib.Path(__file__).resolve().parent
p=pd.read_csv(O/'per_record_working_dispositions.csv')
e=pd.read_csv(O/'accepted_direct_event_native_credit_union.csv');b=pd.read_csv(O/'accepted_newly_formed_native_credit_union.csv')
holds={
'1568':'Dated 2004 inclusion into Shemetovo cached; former Central Estate own point missing. Receiver point cannot represent former NP.',
'413':'Voskresensk printed county identifies former NP; live Krasny Kholm article is Klin homonym. Proper own point and dated lifecycle not established.',
'1040':'Own Lugovaya article gives 1976 inclusion into Lobnya, conflicting with native2002 separate PGT grain. Own point alone does not resolve temporal path.',
'4618':'Literal Lagovsky source context and 2009 own code available; former Podolsky estate point and dated lifecycle unproven.',
'3866':'Explicit 24 March 2004 inclusion into Kudinovo; former estate own point missing.',
'4801':'Old selo distinct from receiving Pushkino city; independent former selo own point and exact lifecycle not established.',
'5449':'Explicit 2003 merger formation of Uspensky; predecessor Sovkhoz own point missing. New successor receives no invented2002 row.',
'1300':'Explicit 14 September 2004 former poselok inclusion into Buzhaninovo selo; merged selo/station point cannot substitute former poselok point.',
'3811':'Explicit 9 August 2004 inclusion into Vishnyakovskie Dachi; separate former Svetly own point missing.',
'81':'Explicit 16 July 2003 inclusion into Volokolamsk; former Volokolamets own point missing.',
'1205':'Own historical point exists; 2004 county-centre transfer is not settlement absorption. Actual rename/inclusion/native successor remains unproven.',
'3920':'Explicit 2004 inclusion into Yamkino; former Chapaev estate own point missing.',
'69722':'Two Popovka own historical homonyms disambiguated; current raw duplicate provider code/coordinate conflicts. Current own OKTMO590 versus587 independent crosswalk unproven.',
'11':'Dated 2003 inclusion into Zvenigorod documented; separate former Porechye subsidiary estate own point missing.',
'65263':'Own current Petrovskoye point exists and military predecessor since1953 documented; formal available-year creation/source2002/2010 scope unresolved.',
'272':'Explicit 5 May 2004 Volokolamsk inclusion; retained raw geo point is Klin homonym. Former Volokolamsk Shchekino point missing.',
'2538':'Explicit 19 October 2004 inclusion into Opalikha; former weaving-factory NP own point missing.'}
for i,r in p.iterrows():
 sid=r.source_record_id;k=sid.split(':')[-1]
 status='hold';reason=holds.get(k,'')
 if r.ordinary_proposed_resolved_full3: status='ready_ordinary_native_three_year';reason='Bounded actual68 UF replay: native identity edges have disjoint year sets and independent own NP point; populations unchanged.'
 elif sid in set(e.source_record_id): status='ready_dated_included_in_native_path';reason='Former NP independent own point plus pinned dated included_in source and receiving NP accepted three-native-year context; separate event axis only.'
 elif sid in set(b.source_record_id):status='ready_dated_new_formal_NP_available_year_path';reason='Pinned dated merger/formal named NP creation with actual2010/2021 own native observations and own points; predecessor unknown retained, no2002 successor count.'
 elif k in ['1324','1391']:status='already_ready_prior69_event_packet';reason='Semkhoz/Kerva source IDs already frozen in next69_event_mass_20261009; excluded from this packet credit.'
 elif k=='67653':status='conditional_ready_after_explicit_false_edge_rejection';reason='Remove source2010 10365 to Dmitrov65842 false homonym pair from earlier stage63 ledger before correct Krasnogorsk67653 union. Net gain accounts lost false Dmitrov2002/2021 credit.'
 assert reason,(sid,status)
 p.loc[i,'final_disposition']=status;p.loc[i,'final_reason']=reason
p.to_csv(O/'all79_final_record_dispositions.csv',index=False)
r=json.loads((O/'ordinary_replay_receipt.json').read_text())
r.update({'status':'FINAL_FROZEN_READY_PACKET_WITH_EXPLICIT_HOLDS','baseline':68,'assigned_records':79,'assigned_sourceyear_population':float(p.population.sum()),'assigned_disposition_counts':p.final_disposition.value_counts().to_dict(),'assigned_hold_population':float(p[p.final_disposition=='hold'].population.sum()),'separate_inclusion_native_UIDs':len(e),'separate_inclusion_population_by_year':e.groupby('year').source_population.sum().to_dict(),'new_formal_NP_available_year_UIDs':len(b),'new_formal_NP_population_by_year':b.groupby('year').source_population.sum().to_dict(),'conditional_Gavrilkovo_net_primary_gain_by_year':{'2002':74,'2010':0,'2021':1086},'conditional_Gavrilkovo_former_false_primary_credit_removed':{'2002':2,'2021':1},'point_claim_rejections':len(pd.read_csv(O/'accepted_point_rejection_delta.csv')),'source_comparability':'UNKNOWN','missing_year_population_imputation':False,'former_child_future_population_imputation':False,'current_boundary_reconstruction_claim':False,'ready_assigned_records_including_prior69_and_conditional':int((p.final_disposition!='hold').sum())})
(O/'FINAL_packet_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
(O/'network_search_throttle_note.json').write_text(json.dumps({'status':'discovery_search_batch_received_HTTP429_and_stopped','exact_batch_API_subsequently_succeeded_after_backoff':True,'bypass_attempted':False,'retry_after_value_not_captured':True},indent=2)+'\n')
manifest={'baseline':68,'packet_directory':str(O),'status':'FINAL_FROZEN','files':[],'replay_receipt':'FINAL_packet_receipt.json','all79_dispositions':'all79_final_record_dispositions.csv','conditional_repair_required':True}
for f in sorted(O.iterdir()):
 if f.is_file() and f.name not in ['FINAL_manifest.json','FINAL_manifest.sha256']:
  manifest['files'].append({'path':f.name,'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
(O/'FINAL_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
h=hashlib.sha256((O/'FINAL_manifest.json').read_bytes()).hexdigest();(O/'FINAL_manifest.sha256').write_text(h+'  FINAL_manifest.json\n')
print(json.dumps(r,ensure_ascii=False,indent=2));print('MANIFEST_SHA256',h);print('BYTES',sum(f.stat().st_size for f in O.iterdir() if f.is_file()))
