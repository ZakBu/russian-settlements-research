import pandas as pd
from shapely.geometry import Polygon,MultiPolygon
from research_rebuild.mass_linkage.region_point_screen import screen

def test_dateline_and_crimea_are_physical_not_country_vetoes():
    d=pd.DataFrame({'source_record_id':['east','west','crimea','bad'],'region_norm':['чукотский','чукотский','крым','чукотский'],'population':[1,2,3,4],'latitude':[66,66,45,95],'longitude':[179.5,-179.5,34,179.5]})
    chuk=MultiPolygon([Polygon([(179,65),(180,65),(180,67),(179,67)]),Polygon([(-180,65),(-179,65),(-179,67),(-180,67)])])
    cr=Polygon([(33,44),(35,44),(35,46),(33,46)])
    r=screen(d,{'RU-CHU':chuk,'UA-43':cr})
    assert r.region_screen_status.tolist()==['inside_expected_modern_region']*3+['point_missing_or_invalid']
    assert r.admission_status.eq('diagnostic_only_no_admission').all()

def test_polygon_edge_and_near_border_are_not_gross_conflicts():
    d=pd.DataFrame({'source_record_id':['edge','near','far'],'region_norm':['москва']*3,'population':[1]*3,'latitude':[55.5,55.5,55.5],'longitude':[37,36.99,30]})
    r=screen(d,{'RU-MOW':Polygon([(37,55),(38,55),(38,56),(37,56)])})
    assert r.region_screen_status.tolist()==['inside_expected_modern_region','border_near_or_simplification_uncertain','outside_expected_region_requires_review']
