"""Actual dated observations retained for display, with no census-union credit."""
from pathlib import Path
import math
import pandas as pd


def load(folder,state,pin,series):
    if not (folder/'application_receipt.json').exists(): return {'status':'not_loaded_without_root_application_receipt'}
    frame=pd.read_csv(folder/'accepted_working_temporal_year_observations.csv',keep_default_na=False)
    assert len(frame)==3*series and frame.trajectory_id.nunique()==series
    assert frame.accepted_working_temporal_year_observation_for_display.all()
    assert not frame.national_mixed_census_source_ID_credit_asserted.any()
    assert not frame.strict_census_three_year_path_asserted.any()
    assert not frame.accepted_physical_three_observed_census_year_path.any()
    assert not frame.ordinary_NP3_asserted.any() and not frame.boundary_comparability_asserted.any()
    assert not frame.loc[frame.year.eq(2002),'source_population_is_census_known'].any()
    for _,group in frame.groupby('trajectory_id'): assert len(group)==3 and set(group.year)=={2002,2010,2021}
    for row in frame.to_dict('records'):
        assert math.isfinite(float(row['population_source_value']))
        assert -90<=float(row['latitude'])<=90 and -180<=float(row['longitude'])<=180
        assert pin(Path(row['point_origin_file']))==row['point_origin_sha256']
        if int(row['year'])==2002:
            assert row['nonadditive_observation'] and row['source_record_id']==''
            assert row['declared_date'].startswith('+2002-') and int(row['date_precision'])>=9
            assert pin(Path(row['source_path']))==row['source_sha256']
        else:
            native=state.by_id.loc[row['source_record_id']]
            assert int(native.census_year)==int(row['year']) and float(native.population)==float(row['population_source_value'])
            assert native.population_value_quality==row['population_quality']
    return frame


def build(E,state,pin,out=None):
    frames=[]
    for dirname,series in [('own_dated2002_secondary_scope_20261008',33),('own_uncached2002_secondary_scope_20261008',5)]:
        folder=E/dirname
        if (folder/'application_receipt.json').exists(): frames.append(load(folder,state,pin,series))
    if not frames: return {'status':'not_loaded_without_root_application_receipt'}
    frame=pd.concat(frames,ignore_index=True)
    assert not frame[['trajectory_id','year']].duplicated().any()
    if out is not None: frame.to_csv(out/'actual_dated2002_temporal_display_observations.csv',index=False)
    return {'status':'retained_actual_dated_year_observations_for_display_only','trajectories':frame.trajectory_id.nunique(),'observations':len(frame),'census2002_identity_known':False,'native_population_credit_to_census_union':0,'ordinary_NP3_asserted':False,'unknown_population_imputed':False,'source_population_sum_interpretation':'Actual dated source observations; no three-census comparability or census coverage claim.'}
