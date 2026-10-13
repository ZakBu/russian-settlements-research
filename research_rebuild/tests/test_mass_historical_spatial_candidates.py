import geopandas as gpd
import pandas as pd
from shapely.geometry import box
from research_rebuild.mass_linkage.historical_spatial_candidates import historical_objects,historic_region_context


def test_historical_competitor_absent_from_modern_layer_is_still_counted():
    history=pd.DataFrame([
        {'historical_okato':'01201802001','longitude_from_long':82.7,'latitude_from_lat':52.4,'name_key':'алейский','type_key_2009':'поселок'},
        {'historical_okato':'01201802002','longitude_from_long':82.8,'latitude_from_lat':52.5,'name_key':'алейский','type_key_2009':'поселок'},
    ])
    shapes=gpd.GeoDataFrame({'shapeISO':['RU-ALT']},geometry=[box(80,50,85,55)],crs='EPSG:4326')
    result=historic_region_context(history,shapes)
    assert result.historical_key_region_name_type_count.tolist()==[2,2]
    assert result.historical_point_modern_region.tolist()==['алтайский','алтайский']


def test_exact_code_does_not_override_historical_name_or_type_conflict():
    classifier=pd.DataFrame([{'historical_okato':'01201802001','is_settlement_raw':'t','name':'Алейский','name_raw':'п Алейский','status':'поселок сельского типа'}])
    geo=pd.DataFrame([{'historical_okato':'01201802001','name_raw':'с Другой','settlement_type_raw':'с'}])
    result=historical_objects(classifier,geo)
    assert not result.iloc[0].historical_name_exact
    assert not result.iloc[0].historical_type_exact
