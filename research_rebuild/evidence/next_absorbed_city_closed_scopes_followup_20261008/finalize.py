from pathlib import Path
import pandas as pd,json,xlrd,re,hashlib
D=Path(__file__).parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
m=pd.read_csv(D/'candidate_constituent_credit_union.csv',keep_default_na=False)
proof=[]
for city,fn,a,b in [('Тольятти','053_f7f2b62d26_Samarskaja_new.xls',27,29),('Улан-Удэ','063_3ec7f8316e_buriatia1.xls',4,18),('Пермь','051_46e3ecb0a0_02c_Permskaja_obl.xls',3,5)]:
 p=Path('/workspace/settlements-raw/data/raw/2002')/fn;s=xlrd.open_workbook(str(p)).sheet_by_index(0)
 g=m[m.group.eq('published_closed_city_scope_'+city.replace('-','_'))&m.census_year.eq(2002)&m.source_file.eq(str(p))]
 loc={int(float(z.split('row_1based=')[-1])) for z in g.source_row_locator}
 atoms=set()
 for n in range(a,b+1):
  if any(isinstance(z,str) and re.match(r'^\s*(?:пос[её]лок|деревня|село|станция|насел[её]нный пункт)\s+',z,re.I) for z in s.row_values(n-1)):atoms.add(n)
 assert atoms==loc,(city,atoms,loc)
 proof.append(dict(group='published_closed_city_scope_'+city.replace('-','_'),year=2002,raw_file=str(p),raw_sha256=sha(p),raw_sheet=s.name,raw_start=a,raw_end=b,raw_atomic_count=len(atoms),native_atomic_population=int(g.population.sum()),all_original_named_atomic_rows_equal_selected_native_rows=True,raw_complete_block_and_next_header_json=json.dumps([dict(row_1based=n,row=s.row_values(n-1)) for n in range(a,b+2)],ensure_ascii=False)))
for city,fn,sn,a,b,leafrows in [('Пермь','016_802d308e41_8._20Or_Penz_Perm_Samar_Saratov_Uly_2010.xls','!!!',7781,7789,[7788,7789]),('Улан-Удэ','008_342f3c208b_16._20Сиб_ФО_2010.xls','Sib',11200,11202,[])]:
 p=Path('/workspace/settlements-raw/data/raw/2010')/fn;s=xlrd.open_workbook(str(p)).sheet_by_name(sn)
 g=m[m.group.eq('published_closed_city_scope_'+city.replace('-','_'))&m.census_year.eq(2010)&m.source_file.eq(str(p))]
 loc={int(float(z.split('row_1based=')[-1])) for z in g.source_row_locator}
 assert loc==set(leafrows)-({7788} if city=='Пермь' else set())
 proof.append(dict(group='published_closed_city_scope_'+city.replace('-','_'),year=2010,raw_file=str(p),raw_sha256=sha(p),raw_sheet=sn,raw_start=a,raw_end=b,raw_atomic_count=len(leafrows),native_atomic_population=int(g.population.sum()),auxiliary_blank_ID_rows_json=json.dumps([7788] if city=='Пермь' else []),intracity_wards_nonadditive_to_NP_roster=True,literal_upper_city_context=city,raw_complete_block_and_next_header_json=json.dumps([dict(row_1based=n,row=s.row_values(n-1)) for n in range(a,b+2)],ensure_ascii=False)))
p=Path('/workspace/settlements-raw/data/raw/2010/016_802d308e41_8._20Or_Penz_Perm_Samar_Saratov_Uly_2010.xls');s=xlrd.open_workbook(str(p)).sheet_by_name('!!!');r=s.row_values(7787);assert r[5]=='Казарма 30-й км' and r[6]==6
aux=[dict(group='published_closed_city_scope_Пермь',census_year=2010,raw_file=str(p),raw_sha256=sha(p),raw_sheet='!!!',raw_row_1based=7788,raw_label=r[5],raw_type='not_printed_in_raw_label',population=6,selected_source_record_id='',population_quality='actual_published_secondary_confidentiality_protected_named_atomic_leaf_absent_selectedNP_layer',national_additive_credit=False,geometry_scope='none; no own auxiliary historical point asserted',raw_original_row_json=json.dumps(r,ensure_ascii=False))]
pd.DataFrame(aux).to_csv(D/'actual_published_auxiliary_atom.csv',index=False)
pd.DataFrame(proof).to_csv(D/'original2002_2010_complete_city_rural_block_closures.csv',index=False)
holds=[dict(city='Бор',reason='2002 propercity61525 only; Neklyudovo/B.Pikino belong district; later complete municipality would introduce county children',closed_city_credit_proposed=False),dict(city='Киржач',reason='Красный Октябрь10233 in2002Kirzhach district urban roster, not literalcityparent; current district aggregate excluded',closed_city_credit_proposed=False),dict(city='Новомосковск',reason='2002 receivingcity134081 only; Сокольники separate city under district, not city jurisdiction',closed_city_credit_proposed=False),dict(city='Мурманск',reason='2002 receivingcity336137 only; Росляково outside receivingcity roster',closed_city_credit_proposed=False)]
pd.DataFrame(holds).to_csv(D/'held_group_scope.csv',index=False)
r=json.loads((D/'candidate_receipt.json').read_text());r.update(status='candidate_only_complete_published_city_hierarchy_scopes',frozen_review_packet=True,source_year_territory_changes_explicit_not_modern_boundary_harmonization=True,municipal_county_district_scope_credit_proposed=False,actual_auxiliary_atom_count=1,auxiliary_national_additive_credit=False,protected2010_parent_differences_not_distributed={'Пермь':-3,'Тольятти':0,'Улан-Удэ':0},closure_evidence2010='Tolyatti primary literal city-only table5 control719632; Ulan-Ude original regional complete intracity-only block until next city, proper city only table5 control404426; Perm all literal rural leaves after own intracity wards until nextcity, actual6 auxiliary preserved without invented ID; table5 parent991170/native+aux991173 difference-3 unallocated.')
r['outputs']={p.name:sha(p) for p in D.glob('*.csv')};r['code_sha256']={p.name:sha(p) for p in D.glob('*.py')};(D/'candidate_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
print(r['net_gain_by_year'])
