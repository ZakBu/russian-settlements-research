"""Preserve the nonterminal legacy event in a separately reviewed village path."""
import json
from pathlib import Path
import duckdb
import openpyxl
import xlrd
from research_rebuild.mass_linkage.apply_reviewed_large_inclusion_scope_20261004 import sha
from research_rebuild.mass_linkage.build_long_table import ACCEPTED_COORDINATE_STATUSES


def run(folder, output, points):
    folder, output, points = map(Path, (folder, output, points))
    assert not output.exists()
    proposal = folder/'proposal.json'; review = folder/'receipt.json'
    j = json.loads(proposal.read_text())
    reviewed = json.loads(review.read_text())
    assert sha(proposal) == reviewed['outputs']['proposal.json']['sha256']
    assert j['status'] == 'separate_event_aware_physical_trajectory_candidate_pending_parent_review'
    for pin in j['source_pins'].values():
        assert sha(pin['path']) == pin['sha256']
    obs = j['observations']; assert len(obs) == 3
    expected = {2002:('2002:031_70abec85e7_02c_KBR.xls:Sheet1:37',20355),2010:('2010:002_027be52979_10._20СевКаз_ФО_20(без_20Даг)_202010.xls:СК:1072',20228),2021:('2021:data_allsettlements_anon_156_v20251217.parquet:parquet:32133',20852)}
    ids = [r['source_record_id'] for r in obs]
    db = duckdb.connect(config={'threads':1,'memory_limit':'256MB'})
    selected = j['source_pins']['selected_observations']['path']
    rows = {r['source_record_id']: r for r in db.execute('select source_record_id,census_year,settlement_type,population,population_scope,is_additive_settlement_record,population_value_quality from read_parquet(?) where source_record_id in(select unnest(?))',[selected,ids]).fetch_arrow_table().to_pylist()}
    for r in obs:
        sid = r['source_record_id'];year = int(r['year']); raw = rows[sid]
        assert (sid,int(r['population'])) == expected[year]
        assert raw['census_year'] == year and raw['settlement_type'] == 'село' and raw['is_additive_settlement_record']
        assert int(raw['population']) == r['population']
        assert r['frozen_legacy_verified_successor_settlement_id'] == 'RU-OKTMO-83703000001'
        r['population_value_quality'] = raw['population_value_quality']
        r['decision_status'] = 'accepted_event_aware_physical_village_trajectory'
        r['ordinary_NP3'] = False
        r['national_new_population_row'] = False
        r['boundary_comparability_asserted'] = False
    # Replay the essential primary hierarchy rather than trusting row labels.
    wb = xlrd.open_workbook(j['source_pins']['raw_2002_publisher']['path']);s = wb.sheet_by_name('Sheet1')
    assert 'Дугулубгей' in ' '.join(map(str,s.row_values(36)))
    # This publisher stores population as decimal strings, unlike the 2010 XLS.
    # Read the documented population column, not any matching value on the row.
    assert s.cell_value(36, 1) == '20355' and s.cell_value(35, 1) == '20355'
    wb = xlrd.open_workbook(j['source_pins']['raw_2010_publisher']['path']);s=wb.sheet_by_name('СК')
    assert 'Баксан' in ' '.join(map(str,s.row_values(1070))) and 'Дыгулыбгей' in ' '.join(map(str,s.row_values(1071)))
    assert s.cell_value(1070, 6) == 36859 and s.cell_value(1071, 6) == 20228
    wb=openpyxl.load_workbook(j['source_pins']['official_2021_table5']['path'],read_only=True,data_only=True)
    rr=list(wb['таб. 5'].iter_rows(min_row=11617,max_row=11619,values_only=True));wb.close()
    assert [int(r[1]) for r in rr] == [60445,39593,20852]
    assert rr[0][1] == rr[1][1]+rr[2][1] and 'Дыгулыбгей' in str(rr[2][0])
    excerpt=Path(j['source_pins']['archived_official_baksan_charter_excerpt']['path']).read_text()
    assert 'Баксан' in excerpt and 'Дыгулыбгей' in excerpt
    carrier=expected[2021][0]
    use=db.execute('select latitude,longitude,coordinate_admission_status from read_parquet(?) where target_source_record_id=?',[str(points),carrier]).fetchall()
    assert len(use)==1 and use[0][2] in ACCEPTED_COORDINATE_STATUSES
    for point in j['points']:
        assert (point['latitude'],point['longitude']) == use[0][:2]
        point['status']='accepted_scoped_representative_point_use'
        point['historical_coordinate_measurement_asserted']=False
        point['ordinary_coordinate_ledger_admission']=False
        point['inference_from_accepted_current_source_record_id']=carrier
    for link in j['links']:
        assert not link['population_comparability_asserted'] and not link['city_or_urban_group_population_included']
        link['status']='accepted_separate_event_aware_physical_place_relation'
    j['status']='applied_separate_event_aware_existing_selected_village_trajectory'
    j['legal_event_dates_independently_verified']=False
    j['source_evidence_flags_modified']=False
    j['national_credit_basis']='union only the three existing selected source IDs once; no Baksan city or urban aggregate'
    output.mkdir(parents=True);path=output/'accepted_scoped_trajectory.json';path.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n')
    receipt={'status':j['status'],'observations':3,'input_pins':{str(proposal):sha(proposal),str(review):sha(review),str(points):sha(points)},'outputs':{path.name:sha(path)},'ordinary_NP_graph_modified':False,'source_population_values_modified':False,'legacy_flags_modified':False,'population_boundary_comparability':'unknown','script_sha256':sha(__file__)}
    (output/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt
