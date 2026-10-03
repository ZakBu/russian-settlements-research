"""Propose points from exact named, typed historical classifier objects.

This extends the inventory to cities whose raw classifier labels omit the
literal city prefix, and to older census records. No point is admitted here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import numbers
import pandas as pd
import geopandas as gpd
from .historical_spatial_candidates import TYPE2009,TYPE2011,historic_region_context
from .coordinate_ledger import norm,haversine_array


def geo_name(raw,short_type):
    text=norm(raw);prefix=norm(short_type)
    # Anchored literal abbreviation followed by whitespace, never a word-start
    # filter: Городец/Городище/Городовиковск must survive unchanged.
    return re.sub(r'^'+re.escape(prefix)+r'\.?\s+','',text,count=1) if prefix else text


def named_objects(classifier,geo):
    c=classifier[classifier.is_settlement_raw.eq('t')].copy()
    c=c[~c.historical_okato.duplicated(keep=False)]
    g=geo[~geo.historical_okato.duplicated(keep=False)].copy()
    c['historical_okato_2009_raw']=c.historical_okato
    g['historical_okato_2011_raw']=g.historical_okato
    # Geo DBF stores all four code blocks. For a typed urban object, its
    # third object group is literal 000 while the 2009 classifier publishes
    # the eight-digit object code. Retain both raw forms and require name,
    # type and the actual DBF group below. This never repairs native OKTMO.
    urban=c.status.isin(['город','поселок городского типа'])&c.historical_okato.str.len().eq(8)
    c['code_join_basis']=urban.map({True:'typed_urban_8digit_plus_zero_third_geo_group',False:'exact_raw_code'})
    c.loc[urban,'historical_okato']=c.loc[urban,'historical_okato']+'000'
    if c.historical_okato.duplicated().any():
        c=c[~c.historical_okato.duplicated(keep=False)]
    h=c.merge(g,on='historical_okato',suffixes=('_2009','_2011'),validate='one_to_one')
    h['name_key']=h.name.map(norm)
    h['type_key_2009']=h.status.map(TYPE2009)
    h['type_key_2011']=h.settlement_type_raw.map(TYPE2011)
    h['geo_name_key']=[geo_name(n,t) for n,t in zip(h.name_raw_2011,h.settlement_type_raw)]
    h['historical_name_exact']=h.name_key.ne('')&h.name_key.eq(h.geo_name_key)
    h['historical_type_exact']=h.type_key_2009.notna()&h.type_key_2009.eq(h.type_key_2011)
    h['historical_code_structure_compatible']=h.code_join_basis.eq('exact_raw_code')|(h.settlement_type_raw.isin(['г','пгт'])&h.kod3_raw_text.eq('000'))
    h['historical_type_exact'] &= h.historical_code_structure_compatible
    return h


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def numeric_provider_code_equal(raw,canonical):
    """Compare numeric or explicitly serialized .0 provider values only.

    This helper is used solely for the frozen provider OKATO field. Bare
    textual codes, including native census OKTMO, never enter this rule.
    """
    if isinstance(raw,str) and re.fullmatch(r'\d+\.0+',raw):
        raw=int(raw.split('.',1)[0])
    if not isinstance(raw,numbers.Real) or isinstance(raw,bool) or pd.isna(raw):
        return False
    if not isinstance(canonical,str) or not re.fullmatch(r'\d{11}',canonical):
        return False
    return float(raw).is_integer() and abs(float(raw))<2**53 and int(raw)==int(canonical)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--selected',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();root=Path('/workspace/settlements-work')
    if a.output.exists():raise FileExistsError('new immutable output required')
    paths={'classifier':root/'sources/raw_okato_2009_verification_v1/raw_classifier.parquet',
           'geo':root/'sources/geokladr_raw_verification/geokladr_okato_2011_raw_parsed.parquet',
           'selected':a.selected,'provider':root/'coordinates/ledger/coordinate_screen.parquet',
           'russia_geometry':root/'sources/region_geometry/RUS_ADM1_simplified.geojson',
           'ukraine_geometry':root/'sources/region_geometry/UKR_ADM1.geojson'}
    classifier=pd.read_parquet(paths['classifier']);geo=pd.read_parquet(paths['geo'])
    h=named_objects(classifier,geo)
    shapes=gpd.GeoDataFrame(pd.concat([gpd.read_file(paths[k]) for k in ['russia_geometry','ukraine_geometry']],ignore_index=True),geometry='geometry',crs='EPSG:4326')
    h=historic_region_context(h,shapes)
    usable=set(h.loc[h.historical_point_modern_region.notna(),'historical_okato_2009_raw'])
    missing=classifier[classifier.is_settlement_raw.eq('t')&~classifier.historical_okato.isin(usable)]
    unresolved=set(zip(missing.name.map(norm),missing.status.map(TYPE2009)))
    s=pd.read_parquet(a.selected,columns=['source_record_id','census_year','settlement_name','settlement_type','name_norm','type_norm','region_norm','population','population_scope','population_value_quality','okato','oktmo','source_file','source_sheet','source_row','is_additive_settlement_record','entity_grain_status'])
    s['source_region_name_type_count']=s.groupby(['census_year','region_norm','name_norm','type_norm'],dropna=False).source_record_id.transform('size')
    eligible_h=h[h.historical_point_modern_region.notna()&h.historical_key_region_name_type_count.eq(1)].copy()
    eligible_h['possible_unlocated_historical_competitor']=[(n,t) in unresolved for n,t in zip(eligible_h.name_key,eligible_h.type_key_2009)]
    # Preserve every non-unique historical key as a hold instead of choosing
    # the first raw point. Only unique exact regional keys enter this join.
    candidates=s.merge(eligible_h,left_on=['region_norm','name_norm','type_norm'],
                       right_on=['historical_point_modern_region','name_key','type_key_2009'],how='left',validate='many_to_one')
    candidates['historical_named_point_candidate']=candidates.source_region_name_type_count.eq(1)&candidates.historical_name_exact.eq(True)&candidates.historical_type_exact.eq(True)&candidates.possible_unlocated_historical_competitor.eq(False)&candidates.is_additive_settlement_record.eq(True)&~candidates.population_scope.isin(['federal_city_region','municipality','region','territorial_aggregate'])
    # Current-code evidence is supplied independently; a different provider
    # identifier never disappears inside a point-admission metric.
    provider=pd.read_parquet(paths['provider'],columns=['source_record_id','provider_latitude','provider_longitude','provider_fias_level','provider_general_fias_id','provider_general_fias_duplicate_count','provider_coordinate_duplicate_count','raw_okato_dadata','provider_name_exact_selected_name','provider_type_exact_selected_type','source_object_is_naselenniy_punkt','source_is_aggregate_scope'])
    candidates=candidates.merge(provider,on='source_record_id',how='left',validate='one_to_one')
    candidates['modern_provider_to_historical_point_km']=haversine_array(candidates.provider_latitude,candidates.provider_longitude,candidates.latitude_from_lat,candidates.longitude_from_long)
    code=candidates.raw_okato_dadata.astype('string').str.replace(r'\.0+$','',regex=True)
    candidates['modern_provider_code_matches_historical_code']=code.eq(candidates.historical_okato.astype('string')).fillna(False)
    candidates['modern_numeric_provider_code_agrees_historical_code']=[numeric_provider_code_equal(r,c) for r,c in zip(candidates.raw_okato_dadata,candidates.historical_okato)]
    candidates['provider_code_comparison_basis']='numeric or explicit .0 serialized provider OKATO value compared with exact named historical code; raw cell and code widths retained separately, bare native text codes never padded'
    candidate_city=candidates.census_year.eq(2021)&candidates.type_norm.eq('город')&candidates.historical_named_point_candidate&candidates.source_object_is_naselenniy_punkt.eq(True)&candidates.source_is_aggregate_scope.eq(False)&candidates.provider_fias_level.eq('4')&(candidates.modern_provider_code_matches_historical_code|candidates.modern_numeric_provider_code_agrees_historical_code)&candidates.modern_provider_to_historical_point_km.le(5)&candidates.provider_general_fias_duplicate_count.le(1)
    candidates['modern_city_historical_code_point_candidate']=candidate_city
    candidates['decision_status']='candidate_requires_independent_rule_review'
    candidates['point_date_interpretation']='2011 source update, not an exact-date census point'
    candidates['spatial_continuity_admitted']=False
    candidates['population_boundary_comparability_admitted']=False
    a.output.mkdir(parents=True)
    candidates.to_parquet(a.output/'historical_named_point_candidates.parquet',index=False)
    h.to_parquet(a.output/'all_historical_named_objects.parquet',index=False)
    receipt={'status':'candidates_only','builder_sha256':sha(Path(__file__)),
             'inputs':{k:{'path':str(v),'sha256':sha(v)} for k,v in paths.items()},
             'outputs':{f.name:sha(f) for f in a.output.glob('*.parquet')},
             'historical_point_candidates_by_year':[{'year':int(y),'records':int(g.historical_named_point_candidate.sum()),'recorded_population':int(g.loc[g.historical_named_point_candidate,'population'].sum())} for y,g in candidates.groupby('census_year')],
             'current_city_historical_code_point_candidates':int(candidate_city.sum()),'current_city_recorded_population':int(candidates.loc[candidate_city,'population'].sum()),
             'limitations':['No admission; source-grain contradictions, competing identifiers, known relocations/events and source provenance need separate review.',
                            'Historical regional context comes from all historical points in 2017 geometry; it does not establish historical district boundaries.',
                            '5km city-point agreement is a proposed representative-point screen, not a calibrated certainty or a footprint.']}
    (a.output/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ['inputs','outputs','limitations']},ensure_ascii=False))


if __name__=='__main__':main()
