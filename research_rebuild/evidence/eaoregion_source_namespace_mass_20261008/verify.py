"""Independent State API replay plus exact source/header and accepted rival checks."""
import json
import sys
from pathlib import Path
import pandas as pd
import xlrd
import build

OUT=Path(__file__).resolve().parent
def main():
    receipt=json.loads((OUT/'application_receipt.json').read_text())
    assert build.sha(OUT/'build.py')==receipt['code_sha256']
    for p,h in receipt['input_pins'].items():assert build.sha(Path(p))==h,p
    for p,h in receipt['output_pins'].items():assert build.sha(OUT/p)==h,p
    s=build.load(49)
    fifty=build.E/'native2010_remaining_county_rule_mass_20261008'
    s.add_deltas([fifty/'accepted_identity_edge_delta.csv.gz'],[fifty/'accepted_point_use_delta.csv.gz'])
    assert build.finite(s)==receipt['before_finite_all3_all_points']
    assert s.metrics()==receipt['before']
    correction=pd.read_csv(OUT/'source_namespace_interpretation_delta.csv',keep_default_na=False)
    assert len(correction)==98 and correction.source_record_id.is_unique
    cols=['source_record_id','population','population_value_quality','settlement_name','settlement_type','source_file','source_path','source_sha256','source_locator']
    protected=s.obs[cols].copy()
    oldpoints={sid:dict(row) for sid,row in s.point_rows.items()}
    s.obs['region_norm_original_import']=s.obs.region_norm
    s.by_id['region_norm_original_import']=s.by_id.region_norm
    for row in correction.itertuples():
        assert s.by_id.loc[row.source_record_id,'region_norm']==row.region_norm_original_import
        s.obs.loc[s.obs.source_record_id.eq(row.source_record_id),'region_norm']=row.effective_region_norm
        s.by_id.loc[row.source_record_id,'region_norm']=row.effective_region_norm
    assert build.finite(s)==receipt['before_finite_all3_all_points']
    assert s.obs.set_index('source_record_id').region_norm.equals(s.by_id.region_norm)
    book=xlrd.open_workbook(correction.iloc[0].source_namespace_witness_file,on_demand=True)
    sheet=book.sheet_by_name('Sheet1');assert sheet.cell_value(0,0)=='Еврейская АО'
    raw=pd.read_csv(OUT/'actual98_native_raw_source_checks.csv',keep_default_na=False)
    for row in raw.itertuples():
        rn=int(float(row.raw_locator.rsplit('=',1)[1]))-1;actual=sheet.row_values(rn)
        assert json.loads(row.raw_row_json)==actual
        assert float(actual[1])==s.by_id.loc[row.source_record_id,'population']
    assert raw.native_population.sum()==62556
    positives=pd.read_csv(OUT/'accepted_native_binding_witnesses.csv',keep_default_na=False)
    rivals=pd.read_csv(OUT/'all_name_type_county_competitors.csv',keep_default_na=False)
    books={};checks=[]
    for row in positives.itertuples():
        ids=[row.native2002_source_record_id,row.native2010_source_record_id,row.native2021_source_record_id]
        a,b,c=[s.by_id.loc[i] for i in ids]
        assert all(r.region_norm=='еврейская' for r in [a,b,c])
        assert build.nm(a.settlement_name)==build.nm(b.settlement_name)==build.nm(c.settlement_name)
        assert build.ty(a.settlement_type)==build.ty(c.settlement_type)
        assert build.county_key(a.district_raw)==build.county_key(c.district_raw)
        relevant=rivals[rivals.target2002_source_record_id.eq(ids[0])]
        expected=set(s.obs[s.obs.region_norm.eq('еврейская')&s.obs.settlement_name.map(build.nm).eq(build.nm(a.settlement_name))].source_record_id)
        assert set(relevant.rival_source_record_id)==expected
        native_path=Path('/workspace/settlements-raw')/b.source_file
        if str(native_path) not in books:books[str(native_path)]=xlrd.open_workbook(str(native_path),on_demand=True)
        _,_,sn,rn=ids[1].split(':');native_sheet=books[str(native_path)].sheet_by_name(sn)
        vals=native_sheet.row_values(int(rn)-1)
        assert str(int(b.population)) in [str(v).strip().removesuffix('.0') for v in vals]
        checks.append(dict(source_record_id=ids[1],source_file=str(native_path),source_sha256=build.sha(native_path),source_locator=f'{sn}!row_1based={rn}',raw_row_json=json.dumps(vals,ensure_ascii=False),native_population=b.population,native_population_quality=b.population_value_quality))
    pd.DataFrame(checks).to_csv(OUT/'accepted_native2010_raw_source_checks.csv',index=False)
    s.add_deltas([OUT/'accepted_identity_edge_delta.csv'],[OUT/'accepted_point_use_delta.csv'])
    assert build.finite(s)==receipt['after_finite_all3_all_points'] and s.metrics()==receipt['after']
    assert protected.equals(s.obs[cols])
    for sid,point in oldpoints.items():assert s.point_rows[sid]==point,sid
    verification=dict(status='passed_independent_actual50_to_effective51_State_API_replay',
        application_receipt_sha256=build.sha(OUT/'application_receipt.json'),source_header_and98_literal_native_rows_verified=True,
        existing_admitted_point_uses_all_preserved=True,populations_types_names_quality_raw_metadata_preserved=True,
        candidate_all_class_county_rival_completeness_verified=True,source_namespace_interpretation_only=True,
        accepted_native2010_literal_row_checks=len(checks),accepted_native2010_raw_checks_sha256=build.sha(OUT/'accepted_native2010_raw_source_checks.csv'),
        accepted_native2010_source_pins={str(p):build.sha(Path(p)) for p in books},
        after_finite_all3_all_points=build.finite(s),code_sha256=build.sha(Path(__file__)))
    (OUT/'verification_receipt.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(verification,ensure_ascii=False))

if __name__=='__main__':main()
