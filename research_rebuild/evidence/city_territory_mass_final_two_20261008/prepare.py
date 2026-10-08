from pathlib import Path
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence');O=E/'city_territory_mass_final_two_20261008';s=(E/'city_territory_mass_followup_20261008/build.py').read_text()
s=s.replace("O=E/'city_territory_mass_followup_20261008'","O=E/'city_territory_mass_final_two_20261008'")
a=s.index("('Екатеринбург','свердловская'");b=s.index('\nprior=',a);s=s[:a-1]+']'+s[b:]
s=s.replace("'nakhoda_complete_published_scope_aux5_application_20261008']","'nakhoda_complete_published_scope_aux5_application_20261008','city_territory_mass_followup_application_20261008']")
s=s.replace('controls=[];members=[];groups=[];points=[];proof=[];net=[];holds=[];hashcache={}','controls=[];members=[];groups=[];points=[];proof=[];net=[];holds=[];auxiliary=[];hashcache={}')
a=s.index(' if len(regional2010)!=cend-cstart:');b=s.index('\n # ',a) if '\n # ' in s[a:] else -1
# Replace complete narrow selected-roster validation and original extra assignment up to primary2010.
b=s.index('primary2010=cityrows',a)
s=s[:a]+''' missing=set(range(cstart+1,cend+1))-set(regional2010.source_row.astype(int));expected={1584} if city=='Барнаул' else {6799};assert missing==expected,(city,missing)
 auxpop=0;auxproof={};extra=o.iloc[:0]
 if city=='Барнаул':
  extra=o[o.census_year.eq(2010)&o.region_norm.eq(region)&o.name_norm.eq('южный')&o.type_norm.eq('пгт')];assert len(extra)==1
  assert '19233' in text and int(extra.iloc[0].population)==19233
 else:
  rr=raw2010sheet.row_values(6798);assert rr[3]=='турбаза "Ладога"' and int(rr[4])==201;auxpop=201
  auxproof={'group':group,'census_year':2010,'raw_file':'/workspace/settlements-raw/data/raw/2010/'+file2010,'raw_sha256':h(Path('/workspace/settlements-raw/data/raw/2010/'+file2010)),'raw_sheet':sheet2010,'raw_row_1based':6799,'raw_label':rr[3],'raw_type':'турбаза','population':201,'selected_source_record_id':'','population_quality':'actual_published_secondary_confidentiality_protected_named_atomic_leaf_absent_selectedNP_layer','national_additive_credit':False,'geometry_scope':'current owncity representative_scope only; no individual historical NP coordinate assertion','raw_original_row_json':json.dumps(rr[:11],ensure_ascii=False)};auxiliary.append(auxproof)
 ownmembers[2010]=pd.concat([cityrows[cityrows.census_year.eq(2010)],extra,regional2010]);''' +s[b:]
s=s.replace("total=int(g.population.sum());ids=list(g.source_record_id)","native_total=int(g.population.sum());actual_aux=auxpop if year==2010 else 0;total=native_total+actual_aux;ids=list(g.source_record_id)")
s=s.replace("'complete_selected_atomic_sum':total,","'complete_selected_atomic_sum':native_total,'actual_published_auxiliary_population_sum':actual_aux,'complete_published_atomic_sum':total,")
s=s.replace("'constituent_count':len(g),","'constituent_count':len(g),'native_selected_population_sum':native_total,'actual_published_auxiliary_population_sum':actual_aux,'actual_published_auxiliary_member_count':int(actual_aux>0),'actual_published_atomic_constituent_count':len(g)+int(actual_aux>0),'auxiliary_published_provenance_json':json.dumps(auxproof,ensure_ascii=False) if actual_aux else '{}',")
s=s.replace("('held_group_scope',holds)","('held_group_scope',holds),('actual_published_auxiliary_atom',auxiliary)")
s=s.replace("'atomic_members':len(members)","'atomic_members':len(members),'actual_published_auxiliary_atoms':len(auxiliary),'actual_published_atomic_members':len(members)+len(auxiliary),'unselected_auxiliary_national_credit':0")
s=s.replace('all26 territorialselected-IDcredit+approved Nakhoda14native union','all26 territorialselected-IDcredit+approved Nakhoda14native+approved followup527native union')
(O/'build.py').write_text(s)
s=(E/'city_territory_mass_followup_20261008/verify.py').read_text();(O/'verify.py').write_text(s)
