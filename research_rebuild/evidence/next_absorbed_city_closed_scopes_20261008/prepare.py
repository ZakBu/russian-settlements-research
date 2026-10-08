from pathlib import Path
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence');O=Path(__file__).parent;s=(E/'city_territory_mass_followup_20261008/build.py').read_text()
s=s.replace("O=E/'city_territory_mass_followup_20261008'","O=E/'next_absorbed_city_closed_scopes_20261008'");s=s.replace("s=load();print('loaded');","s=load(stage=34);print('loaded34');")
# First-line prefix imports and loads old scan preamble; freeze the stage explicitly.
s=s.replace("exec(open('/workspace/settlements-work/large_absorbed_city_closed_scope_mass_20261008/scan.py').read().split('configs=')[0])","exec(open('/workspace/settlements-work/large_absorbed_city_closed_scope_mass_20261008/scan.py').read().split('configs=')[0].replace('s=load();', 's=load(stage=34);'))")
a=s.index('cfg=');b=s.index('\nprior=',a)
s=s[:a]+'''cfg=[('Тюмень','тюменская',7716,7730,'058_a73d73c7dd_02c-Tyumen_obl_new.xls',3,38,'003_eb441570b1_11._20Урал_ФО_2010.xls','Урал',2493,2512,604816,22909),('Волжский','волгоградская',4793,4795,None,0,0,'004_486e984bdc_12._20Астр_Волгог_Ростов.xls','Южный',1945,1946,327089,0),('Новоалтайск','алтайский',8446,8451,'066_76aa869929_Altai_krai1.xls',44,45,'008_342f3c208b_16._20Сиб_ФО_2010.xls','Sib',1619,1619,70437,0),('Самара','самарская',6868,6883,'053_f7f2b62d26_Samarskaja_new.xls',3,8,'016_802d308e41_8._20Or_Penz_Perm_Samar_Saratov_Uly_2010.xls','!!!',1318,1320,1164814,129)]''' +s[b:]
s=s.replace("'nakhoda_complete_published_scope_aux5_application_20261008']","'nakhoda_complete_published_scope_aux5_application_20261008','city_territory_mass_followup_application_20261008','city_territory_mass_final_two_application_20261008']")
s=s.replace("text=Path(","for folder in ['complete_transferred_municipal_scope_application_20261008','moscow_complete_scope_mass_application_20261008']:\n prior.update(pd.read_csv(E/folder/'accepted_native_scope_constituents.csv').source_record_id)\ntext=Path(",1)
a=s.index(' if len(regional2010)!=cend-cstart:');b=s.index('primary2010=cityrows',a)
s=s[:a]+''' if city=='Волжский':
  extra=o[o.census_year.eq(2010)&o.region_norm.eq(region)&o.name_norm.eq('краснооктябрьский')&o.type_norm.eq('пгт')];assert len(extra)==1 and int(extra.iloc[0].population)==12834;assert len(regional2010)==0
 else:
  extra=o.iloc[:0]
  if len(regional2010)!=cend-cstart:
   missing=set(range(cstart+1,cend+1))-set(regional2010.source_row.astype(int));holds.append({'city':city,'reason':'original2010roster contains selectednative omissions requiring actualaux or primaryoverrides','missing_raw_rows_json':json.dumps([{'row':n,'original_row':raw2010sheet.row_values(n-1)[:11]} for n in sorted(missing)],ensure_ascii=False)});print('HOLD2010',city,sorted(missing),flush=True);continue
 ownmembers[2010]=pd.concat([cityrows[cityrows.census_year.eq(2010)],extra,regional2010]);''' +s[b:]
s=s.replace("hits=[(n,l) for n,l in enumerate(lines) if re.match(r'^\\s*г\\.\\s+'+re.escape(city)+r'\\s+с подчиненными',l)];assert hits","hits=[(n,l) for n,l in enumerate(lines) if re.match(r'^\\s*г\\.\\s+'+re.escape(city)+r'\\s+с подчиненными',l)] if city!='Новоалтайск' else [(n,l) for n,l in enumerate(lines) if re.match(r'^\\s*г\\.\\s+Новоалтайск\\s+70437',l)];assert hits")
s=s.replace("assert str(parent2010) in below and str(ruralcontrol2010) in below","assert str(parent2010) in (line+'\\n'+below) and (str(ruralcontrol2010) in below if ruralcontrol2010 else True)")
s=s.replace("'existing_scope_exclusions':'finite ordinary+parts12+qualified1919+named10+all26 territorialselected-IDcredit+approved Nakhoda14native union'","'existing_scope_exclusions':'actual loader34 finite ordinary all3-ownpoint source-IDunion plus existing complete partitions,qualifiedphysical,named10,all14 cityscopes,Ryazan,Moscow5; no county representative points credited'")
(O/'build.py').write_text(s)
s=(E/'city_territory_mass_followup_20261008/verify.py').read_text();s=s.replace("else:ix=4;value=int(rr[5])","elif sn=='Южный':ix=6;value=int(rr[7])\n  elif sn=='!!!':ix=5;value=int(rr[6])\n  else:ix=4;value=int(rr[5])");(O/'verify.py').write_text(s)
