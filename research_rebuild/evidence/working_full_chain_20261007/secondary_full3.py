"""Load only root-admitted secondary historical physical observation packs."""
from pathlib import Path
import json, math
import pandas as pd

PACKS=[
 ('wikidata_secondary_full3_application_20261007','applied_qualified_secondary_census_referenced_own_physical_series','qualified_accepted_secondary_census_referenced_own_item'),
 ('current_unpointed_own_wiki_mass_application_20261007','applied_current_own_points_and_qualified_secondary_histories','qualified_accepted_secondary_own_census_history'),
 ('existing_event_scope_application_20261007','applied_reviewed_secondary_physical_three_census_scopes',None),
 ('wikidata_secondary_full3_expansion_application_20261007','applied_qualified_secondary_census_referenced_own_physical_series','qualified_accepted_secondary_census_referenced_own_item'),
]

def load(E,state,pin):
    packs=[];cached_hashes={}
    rawroot=Path('/workspace/settlements-raw');r2=Path('/workspace/settlements-work/sources/r2-missing')
    known_r2={'kaliningrad_2010_tom1.xlsx':r2/'kaliningrad_tom1.xlsx','murmansk_population_by_sex_municipalities.doc':r2/'murmansk_population.doc','arkhangelsk_2010_archived_original.html':r2/'arkhangelsk_2010_archived_original.html'}
    def meaningful(value):
        return pd.notna(value) and str(value) not in ['', 'None','nan','NaN']
    def resolve_source(row):
        source_path=row['source_path'];sid=row['source_record_id'];values=[source_path]
        if sid in state.by_id.index:
            selected=state.by_id.loc[sid];values += [selected.source_path,selected.source_file]
        for value in values:
            if not meaningful(value): continue
            path=Path(str(value));candidates=[path] if path.is_absolute() else [rawroot/path,E.parents[1]/path]
            if path.name in known_r2: candidates.append(known_r2[path.name])
            for candidate in candidates:
                if candidate.is_file(): return str(candidate),pin_once(candidate),'exact_cached_source_bytes'
        assert sid in state.by_id.index,('Missing admitted secondary raw-source bytes',source_path)
        return '','','original_native_source_cache_unresolved_imported_provenance_retained'
    def pin_once(path):
        path=Path(path);key=str(path)
        if key not in cached_hashes: cached_hashes[key]=pin(path)
        return cached_hashes[key]
    for dirname,status,decision in PACKS:
        folder=E/dirname;rp=folder/'application_receipt.json'
        if not rp.exists(): continue
        pin(rp);receipt=json.loads(rp.read_text())
        assert status is not None, ('unconfigured root admission status',dirname)
        assert receipt['status']==status,(dirname,receipt['status'])
        name='accepted_qualified_physical_observations.csv'
        outputs=receipt.get('outputs',receipt.get('output_hashes',{}))
        assert pin(folder/name)==outputs[name]
        for filename,h in outputs.items(): assert pin_once(folder/filename)==h
        for filename,h in receipt.get('input_hashes',{}).items(): assert pin_once(Path(filename))==h
        frame=pd.read_csv(folder/name,keep_default_na=False)
        if 'point_provenance.csv' in outputs:
            proof=pd.read_csv(folder/'point_provenance.csv',keep_default_na=False)
            assert not proof.trajectory_id.duplicated().any()
            frame=frame.merge(proof,on='trajectory_id',how='left',validate='many_to_one')
            assert len(frame)==3*len(proof)
        if 'decision_status' not in frame: frame['decision_status']=receipt.get('decision_status',status)
        for canonical,raw in [('source_path','raw_source_file'),('source_sha256','raw_source_sha256'),('source_locator','raw_source_locator')]:
            if canonical not in frame: frame[canonical]=frame[raw]
        assert len(frame) and not frame[['scope','trajectory_id','year']].duplicated().any()
        assert not frame.ordinary_NP3_asserted.any() and not frame.boundary_comparability_asserted.any()
        for field in ['accepted_physical_three_observed_census_year_path','accepted_scoped_representative_point']:
            if field not in frame: frame[field]=True
            assert frame[field].all()
        if decision: assert frame.decision_status.eq(decision).all()
        for _,group in frame.groupby(['scope','trajectory_id']):
            assert len(group)==3 and set(group.year)=={2002,2010,2021}
        actual_sources=[]
        for row in frame.to_dict('records'):
            assert math.isfinite(float(row['population_source_value']))
            assert -90<=float(row['latitude'])<=90 and -180<=float(row['longitude'])<=180
            actual_path,actual_hash,actual_status=resolve_source(row);actual_sources.append((actual_path,actual_hash,actual_status))
            if meaningful(row['source_sha256']) and actual_hash: assert actual_hash==row['source_sha256']
            for path_field,hash_field in [('secondary_source_path','secondary_source_sha256')]:
                if row.get(path_field): assert pin_once(Path(row[path_field]))==row[hash_field]
            assert pin_once(Path(row['point_origin_file']))==row['point_origin_sha256']
            year=int(row['year']);sid=row['source_record_id']
            if row['nonadditive_observation']:
                assert year in [2002,2010] and not sid
            else:
                assert sid in state.by_id.index
                selected=state.by_id.loc[sid]
                assert int(selected.census_year)==year and int(selected.population)==int(row['population_source_value'])
                assert selected.population_value_quality==row['population_quality']
                if dirname=='existing_event_scope_application_20261007':
                    assert state.uf.find(sid)==state.uf.find(row['current_source_record_id'])
            if dirname in ['wikidata_secondary_full3_application_20261007','wikidata_secondary_full3_expansion_application_20261007']:
                assert row['nonadditive_observation']==(year!=2021)
                if dirname=='wikidata_secondary_full3_application_20261007':
                    assert int(row['date_precision'])==9 and row['census_reference_ids']
                elif year in [2002,2010]:
                    assert int(row['date_precision'])==9 and row['census_proof_class'].startswith('explicit_')
                    assert json.loads(row['P248_ids_json']) or json.loads(row['census_reference_titles_json']) or json.loads(row['reference_urls_json'])
        frame[['source_actual_path','source_actual_sha256','source_actual_resolution_status']]=pd.DataFrame(actual_sources,index=frame.index)
        packs.append((dirname,receipt,frame))
    return packs
