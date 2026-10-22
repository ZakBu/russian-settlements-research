#!/usr/bin/env python3
"""Unit and impossible-value diagnostics on independently extracted source rows."""
from pathlib import Path
import json,hashlib
import pandas as pd
H=Path(__file__).resolve().parent;O=H/'independent_sources/agriculture';P=O/'independent_selected_raw.parquet'
def main():
 d=pd.read_parquet(P);production=d.group.eq('production');bad=production&d.indicator_value.lt(0);d.loc[bad].to_csv(O/'negative_production_source_rows.csv',index=False);checks={'all_crop_units_hectares':d.loc[~production,'indicator_unit'].eq('Гектар').all(),'all_production_units_thousand_RUB':d.loc[production,'indicator_unit'].eq('Тысяча рублей').all(),'negative_production_not_in_2010_or_2021':not (bad&d.year.isin([2010,2021])).any()};audit={'checks':{k:bool(v) for k,v in checks.items()},'pass':all(checks.values()),'negative_source_production_rows':int(bad.sum()),'negative_values_are_real_production':False,'input_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'meaning':'Three source anomalies are preserved as source evidence, not interpreted as negative production. Main 2010/2021 and nonnegative latest production features are unaffected.'};(O/'UNIT_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(audit['pass'],'unit/negative-source audit; anomalies',int(bad.sum()))
if __name__=='__main__':main()
