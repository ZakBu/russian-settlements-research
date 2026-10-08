import hashlib,json
from pathlib import Path
import pandas as pd
Z=Path(__file__).resolve().parent;S=Z.parent/'native_singleton_rural_mass_20261008';rule=json.loads((Z/'sampling_rule.json').read_text());f=pd.read_csv(S/'accepted_native_source_binding_witnesses.csv.gz',keep_default_na=False)
assert len(f)==2326 and not f.native2010_source_record_id.duplicated().any()
pop=f.protected2010_population.astype(float);f['stratum']=pop.map(lambda v:'>=1000' if v>=1000 else '100..999' if v>=100 else '1..99' if v>=1 else '0');f['frozen_rank']=f.native2010_source_record_id.map(lambda sid:hashlib.sha256(f"20261008|{sid}".encode()).hexdigest());groups={band:f[f.stratum.eq(band)].sort_values('frozen_rank') for band in rule['bands']};selected=[];used=set()
for band in rule['bands']:
 for _,r in groups[band].head(10).iterrows():selected.append(r.to_dict());used.add(r.native2010_source_record_id)
while len(selected)<40:
 progress=False
 for band in rule['bands']:
  remaining=groups[band][~groups[band].native2010_source_record_id.isin(used)]
  if len(remaining) and len(selected)<40:
   r=remaining.iloc[0];selected.append(r.to_dict());used.add(r.native2010_source_record_id);progress=True
 if not progress:break
assert len(selected)==40
pd.DataFrame(selected).to_csv(Z/'fixed_sample40.csv',index=False)
sha=lambda p:hashlib.file_digest(p.open('rb'),'sha256').hexdigest();pins={str(p):sha(p) for p in S.iterdir() if p.is_file() and p.suffix in {'.gz','.json','.py'}};pins[str(Z/'sampling_rule.json')]=sha(Z/'sampling_rule.json');(Z/'selection_receipt.json').write_text(json.dumps(dict(status='fixedstratifiedsample_selected_before_inspection',rule=rule,available_by_band={b:len(g) for b,g in groups.items()},selected_by_band=pd.DataFrame(selected).stratum.value_counts().to_dict(),input_pins=pins,selected40_sha256=sha(Z/'fixed_sample40.csv')),indent=2)+'\n');print(pd.DataFrame(selected)[['name','region','type','county_key','protected2010_population','stratum']].to_string(index=False))
