import pandas as pd
import pytest
from research_rebuild.mass_linkage.coverage import measure, identity_sets

def inputs():
    s=pd.DataFrame({'source_record_id':['a','b','c','other'],'census_year':[2002,2010,2021,2021],
        'population':[100,95,110,None], 'latitude':[None,None,60,None], 'longitude':[None,None,40,None],
        'population_scope':['settlement']*4,'population_value_quality':['direct','confidentiality_perturbed_within_ten','direct',None]})
    l=pd.DataFrame({'source_record_id':['a','b'],'any_legacy_point_available':[True,True]})
    e=pd.DataFrame({'from_source_record_id':['a','b'],'to_source_record_id':['b','c']})
    points=pd.DataFrame({'target_source_record_id':['c'],'latitude':[60],'longitude':[40]})
    return s,l,e,points,{2002:101,2010:100,2021:120}

def test_inventory_is_not_admission_and_control_gap_is_retained():
    r=measure(*inputs());y={x['year']:x for x in r['census_metrics']}
    assert y[2002]['axes']['coordinate_availability_by_exact_source_route']['known_population']==100
    assert y[2002]['axes']['coordinate_admitted']['known_population']==0
    assert y[2010]['selected_known_population_gap_to_control']==5
    assert y[2010]['population_quality_categories'][0]['source_quality']=='confidentiality_perturbed_within_ten'
    assert y[2021]['unknown_population_rows']==1
    assert y[2021]['axes']['coordinate_admitted']['official_control_population_fraction']==110/120
    assert r['identity_graph']['full_census_components']==1
    assert y[2021]['population_boundary_comparability']['status']=='not_measured'

def test_same_year_component_collision_fails():
    s,l,e,p,c=inputs();e.loc[len(e)]=['a','other']
    with pytest.raises(ValueError,match='one census year'):identity_sets(s,e)

def test_aggregate_point_and_unvalidated_extra_year_fail():
    s,l,e,p,c=inputs();s.loc[2,'population_scope']='federal_city_region'
    with pytest.raises(ValueError,match='aggregate'):measure(s,l,e,p,c)
    s.loc[2,'population_scope']='settlement';s.loc[2,'census_year']=2022
    with pytest.raises(ValueError,match='annual'):measure(s,l,e,p,c)


def test_legacy_place_pointer_only_increases_candidate_inventory():
    s,l,e,p,c=inputs();s['settlement_id']=['X','Y','Z','X'];l['settlement_id']=['X','Y']
    r=measure(s,l,e,p,c);y=r['census_metrics'][2]
    assert y['axes']['coordinate_inventory_including_unaccepted_legacy_place_pointers']['rows']==2
    assert y['axes']['coordinate_admitted']['rows']==1
