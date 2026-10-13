"""Generate ordinary 2010 candidates with independently read classifier points.

No candidate is an identity admission. Region/name/type uniqueness alone is
insufficient: these proposals additionally require exact, named 2009/2011
classifier continuity, current exact code/object correspondence and geographic
agreement. The 2011 point is after the census; no exact-date polygon is inferred.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
import geopandas as gpd
from .coordinate_ledger import norm,haversine_array
from .region_point_screen import REGION_ISO


TYPE2009={'деревня':'деревня','село':'село','поселок сельского типа':'поселок',
          'хутор':'хутор','поселок городского типа':'пгт','город':'город',
          'станица':'станица','станция':'станция','разъезд':'разъезд','слобода':'слобода'}
TYPE2011={'д':'деревня','с':'село','п':'поселок','х':'хутор','пгт':'пгт','г':'город',
          'ст-ца':'станица','ст':'станция','рзд':'разъезд','сл':'слобода'}
DEFAULTROOT=Path('/workspace/settlements-work')


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def historical_objects(classifier:pd.DataFrame,geo:pd.DataFrame):
    c=classifier[classifier.is_settlement_raw.eq('t')].copy()
    c['classifier_code_count']=c.groupby('historical_okato').historical_okato.transform('size')
    c=c[c.classifier_code_count.eq(1)].copy()
    g=geo.copy();g['geo_code_count']=g.groupby('historical_okato').historical_okato.transform('size')
    g=g[g.geo_code_count.eq(1)].copy()
    both=c.merge(g,on='historical_okato',suffixes=('_2009','_2011'),validate='one_to_one')
    both['historical_name_exact']=both.name_raw_2009.map(norm).eq(both.name_raw_2011.map(norm))
    both['name_key']=both.name.map(norm)
    both['type_key_2009']=both.status.map(TYPE2009)
    both['type_key_2011']=both.settlement_type_raw.map(TYPE2011)
    both['historical_type_exact']=both.type_key_2009.notna()&both.type_key_2009.eq(both.type_key_2011)
    return both


def historic_region_context(hist:pd.DataFrame,shapes:gpd.GeoDataFrame):
    """Count all historical objects, including those absent from the 2021 layer."""
    geometry=shapes[shapes.shapeISO.isin(set(REGION_ISO.values()))][['shapeISO','geometry']].copy()
    points=gpd.GeoDataFrame(hist[['historical_okato']].copy(),
                          geometry=gpd.points_from_xy(hist.longitude_from_long,hist.latitude_from_lat),crs='EPSG:4326')
    joined=gpd.sjoin(points,geometry.to_crs('EPSG:4326'),how='left',predicate='intersects')
    mapping=joined.groupby('historical_okato').shapeISO.agg(lambda v:sorted(set(v.dropna())))
    reverse={iso:region for region,iso in REGION_ISO.items()}
    result=hist.copy()
    result['historical_point_modern_region']=result.historical_okato.map(mapping).map(lambda x:reverse[x[0]] if isinstance(x,list) and len(x)==1 else None)
    result['historical_key_region_name_type_count']=result.groupby(['historical_point_modern_region','name_key','type_key_2009'],dropna=False).historical_okato.transform('size')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--selected',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); out=args.output
    if out.exists():raise FileExistsError('use a new immutable output')
    paths={
      'selected':args.selected,
      'classifier':DEFAULTROOT/'sources/raw_okato_2009_verification_v1/raw_classifier.parquet',
      'geo':DEFAULTROOT/'sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet',
      'provider':DEFAULTROOT/'coordinates/ledger/coordinate_screen.parquet',
      'region_screen':DEFAULTROOT/'coordinates/region_screen_v1/region_point_screen.parquet',
      'pairs':DEFAULTROOT/'candidates/optimized_run/pair_candidates.csv.gz',
      'russia_geometry':DEFAULTROOT/'sources/region_geometry/RUS_ADM1_simplified.geojson',
      'ukraine_geometry':DEFAULTROOT/'sources/region_geometry/UKR_ADM1.geojson',
    }
    selected=pd.read_parquet(args.selected,columns=['source_record_id','census_year','name_norm','type_norm','region_norm','population','population_value_quality','population_scope','source_file','source_sheet','source_row','is_additive_settlement_record','entity_grain_status','okato'])
    classifier=pd.read_parquet(paths['classifier'])
    hist=historical_objects(classifier,pd.read_parquet(paths['geo']))
    shapes=pd.concat([gpd.read_file(paths[k]) for k in ['russia_geometry','ukraine_geometry']],ignore_index=True)
    hist=historic_region_context(hist,gpd.GeoDataFrame(shapes,geometry='geometry',crs='EPSG:4326'))
    # Objects with no usable spatial region remain possible competitors. Their
    # names are retained as conservative global holds, not silently discarded.
    usable_codes=set(hist.loc[hist.historical_point_modern_region.notna(),'historical_okato'])
    missing=classifier[classifier.is_settlement_raw.eq('t')&~classifier.historical_okato.isin(usable_codes)]
    unresolved_historical_keys=set(zip(missing.name.map(norm),missing.status.map(TYPE2009)))
    provider=pd.read_parquet(paths['provider'],columns=['source_record_id','candidate_family_exact_named_physical_np_fias_point','provider_latitude','provider_longitude','provider_name_exact_selected_name','provider_type_exact_selected_type','raw_okato_dadata'])
    current=selected[selected.census_year.eq(2021)].merge(provider,on='source_record_id',validate='one_to_one')
    current=current.merge(hist,left_on='okato',right_on='historical_okato',how='left',validate='many_to_one')
    current['current_name_exact_historical_name']=current.name_norm.map(norm).eq(current.name_key.fillna(''))
    current['current_type_exact_historical_type']=current.type_norm.eq(current.type_key_2009)
    current['provider_to_historical_point_km']=haversine_array(current.provider_latitude,current.provider_longitude,current.latitude_from_lat,current.longitude_from_long)
    current['historical_point_region_matches_source']=current.region_norm.eq(current.historical_point_modern_region)
    current['unlocated_historical_name_competitor_possible']=[(n,t) in unresolved_historical_keys for n,t in zip(current.name_key,current.type_key_2009)]
    current['historical_spatial_rule_candidate']=current.candidate_family_exact_named_physical_np_fias_point.fillna(False)&current.historical_name_exact.fillna(False)&current.historical_type_exact.fillna(False)&current.current_name_exact_historical_name&current.current_type_exact_historical_type&current.provider_to_historical_point_km.le(1)&current.historical_key_region_name_type_count.eq(1)&current.historical_point_region_matches_source&~current.unlocated_historical_name_competitor_possible&current.is_additive_settlement_record.fillna(False)
    # The independent region screen remains evidence, not a fabricated census polygon.
    region=pd.read_parquet(paths['region_screen'])
    current=current.merge(region.drop(columns=[c for c in region.columns if c in current.columns and c!='source_record_id']),on='source_record_id',validate='one_to_one')
    rows=[]
    for chunk in pd.read_csv(paths['pairs'],chunksize=50000):
        chunk=chunk[chunk.candidate_family.eq('region_name_type')&chunk.candidate_kind.eq('unique_exact_key_pair')&chunk.year_from.eq(2010)&chunk.year_to.eq(2021)]
        rows.append(chunk)
    pairs=pd.concat(rows,ignore_index=True)
    if pairs[['from_source_record_id','to_source_record_id']].duplicated().any():raise ValueError('duplicate source candidate pairs')
    binding_cols=['source_record_id','historical_okato','historical_name_exact','historical_type_exact','current_name_exact_historical_name','current_type_exact_historical_type','historical_spatial_rule_candidate','provider_to_historical_point_km','historical_point_modern_region','historical_key_region_name_type_count','unlocated_historical_name_competitor_possible','source_line_1based','record_number_1based','record_byte_offset_0based','name_raw_2009','name_raw_2011','name','status','settlement_type_raw','latitude_from_lat','longitude_from_long','source_updated_at','source_sha256_2009','source_sha256_2011']
    proposal=pairs.merge(current[binding_cols],left_on='to_source_record_id',right_on='source_record_id',how='left',validate='many_to_one')
    proposal['historical_spatial_rule_candidate']=proposal.historical_spatial_rule_candidate.fillna(False)
    proposal['decision_status']='candidate_requires_independent_review'
    proposal['coordinate_date_interpretation']='2011 source update; adjacent post-census support, not exact 2010 coordinate measurement'
    proposal['historical_code_interpretation']='same exact named classifier object 2009/2011/current provider claim; no legal interval inferred'
    proposal['admission_allowed']=False
    out.mkdir(parents=True)
    current.to_parquet(out/'historical_current_object_screen.parquet',index=False)
    hist.to_parquet(out/'all_historical_object_context.parquet',index=False)
    proposal.to_parquet(out/'identity_candidates.parquet',index=False)
    candidate_ids=set(proposal.loc[proposal.historical_spatial_rule_candidate,'from_source_record_id'])
    g=selected[selected.source_record_id.isin(candidate_ids)]
    receipt={'status':'candidates_only','rule_proposal':'unique_region_name_type_plus_exact_named_historical_code_and_independent_point_agreement',
             'distance_candidate_threshold_km':1,'modern_records_with_named_historical_code_support':int(current.historical_spatial_rule_candidate.sum()),
             'candidate_pairs_2010_2021':int(proposal.historical_spatial_rule_candidate.sum()),
             '2010_candidate_rows':len(g),'2010_candidate_recorded_population':int(g.population.sum()),
             'inputs':{k:{'path':str(v),'sha256':sha(v)} for k,v in paths.items()},
             'outputs':{p.name:sha(p) for p in out.glob('*.parquet')},'builder_sha256':sha(Path(__file__)),
             'limitations':['No identity or coordinate admissions; graph conflicts, source grain, historic events and population comparability require separate review.',
                            'Regional uniqueness is supplemented by a named dated classifier object and spatial agreement; the 1km cutoff is a proposal needing validation.']}
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in {'inputs','outputs','limitations'}},ensure_ascii=False))


if __name__=='__main__':main()
