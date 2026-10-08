from pathlib import Path
import pandas as pd,xlrd,json,hashlib,re
E=Path('/workspace/russian-settlements-research/research_rebuild/evidence');O=Path(__file__).parent
m=pd.concat([pd.read_csv(E/'city_territory_mass_followup_application_20261008/accepted_constituent_credit_union.csv'),pd.read_csv(O/'candidate_constituent_credit_union.csv')],ignore_index=True)
cfg=[('Владимир','003_308406b0ed_02c_Vladimirskaja.xls',4,5),('Барнаул','066_76aa869929_Altai_krai1.xls',3,32),('Екатеринбург','057_9b18a354f1_02c_Sverdlovskaja_oblast.xls',3,43),('Киров','047_9960082a3e_02c_Kirovskaja_new.xls',3,151),('Якутск','078_8405ea8fce_Yakutia.xls',3,16)]
proof=[]
for city,file,a,b in cfg:
 p=Path('/workspace/settlements-raw/data/raw/2002')/file;s=xlrd.open_workbook(str(p)).sheet_by_index(0);h=hashlib.sha256(p.read_bytes()).hexdigest();own=m[m.group.eq('published_closed_city_scope_'+city)&m.census_year.eq(2002)&m.source_file.eq(str(p))];native_rows={int(float(z.split('row_1based=')[-1])) for z in own.source_row_locator};atoms=set()
 for n in range(a,b+1):
  rr=s.row_values(n-1);ix=next((i for i,z in enumerate(rr) if isinstance(z,str) and re.match(r'^\s*(?:пос[её]лок|деревня|село|починок|железнодорожная (?:станция|казарма|будка)|станция)\s+',z,re.I)),None)
  if ix is not None:atoms.add(n)
 assert atoms==native_rows,(city,atoms-native_rows,native_rows-atoms)
 proof.append({'group':'published_closed_city_scope_'+city,'year':2002,'raw_file':str(p),'sha256':h,'sheet':s.name,'block_start':a,'block_end':b,'all_original_named_atomic_rows_match_native_selected_rows':True,'raw_atomic_count':len(atoms),'native_population':int(own.population.sum()),'original_zero_population_rows_count':sum(int(float(s.row_values(n-1)[next(i for i,z in enumerate(s.row_values(n-1)) if isinstance(z,str) and re.match(r'^\s*(?:пос[её]лок|деревня|село|починок|железнодорожная (?:станция|казарма|будка)|станция)\s+',z,re.I))+1]))==0 for n in atoms),'block_original_rows_json':json.dumps([{'row_1based':n,'raw_row':s.row_values(n-1)} for n in range(a,b+2)],ensure_ascii=False)})
pd.DataFrame(proof).to_csv(O/'all_five_original2002_full_rural_roster_verification.csv',index=False)
p=O/'candidate_receipt.json';r=json.loads(p.read_text());r['all_original2002_complete_rural_rosters_positive_and_zero_atoms_reopened']=True;r['outputs']['all_five_original2002_full_rural_roster_verification.csv']=hashlib.sha256((O/'all_five_original2002_full_rural_roster_verification.csv').read_bytes()).hexdigest();p.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print('verifiedall5full2002rosters',[(r['group'],r['raw_atomic_count']) for r in proof])
