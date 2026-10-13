from pathlib import Path
import sys,json,hashlib
R=Path('/workspace/russian-settlements-research');D=Path(__file__).parent;sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
s=load(44)
ids=['2002:1_TOM_01_04.xls:0:1208','2002:1_TOM_01_04.xls:0:1209','2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:11246','2010:010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls:Data Sheet:11251']
rows=[]
for sid in ids:
 r=s.by_id.loc[sid];point=s.point_rows.get(sid);rows.append(dict(source_record_id=sid,census_year=int(r.census_year),settlement_name=r.settlement_name,settlement_type=r.settlement_type,population=float(r.population),population_quality=r.population_value_quality,existing_admitted_point=point or None))
pins={str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in s.inputs};(D/'state44_actual_native_point_rows.json').write_text(json.dumps(dict(label='explicit_State44_admittedpoint_readback_only_notfuture45populationcredit_witness',rows=rows,input_hashes_at_readback=pins),ensure_ascii=False,indent=2,default=str)+'\n');print(json.dumps(rows,ensure_ascii=False,default=str))
