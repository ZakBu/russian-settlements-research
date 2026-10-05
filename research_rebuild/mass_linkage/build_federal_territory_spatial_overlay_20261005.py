#!/usr/bin/env python3
"""Build a separate spatial overlay for published federal-city territory totals.

Does not mutate the physical-settlement graph or the accepted point ledger. It
replaces each selected federal-city region's component settlement rows with one
territorial observation, so coverage calculations do not double count children.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import duckdb, pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research_rebuild/evidence/federal_territory_spatial_overlay_20261005'
SELECTED=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
POINTS=Path('/tmp/graph29_ozherele_points_20261005/accepted_point_uses.parquet')
EDGES=Path('/tmp/graph28_three_code_bridge_20261005/accepted_identity_edges.parquet')
RAW2021=Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet')
RAW2002=Path('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls')
CONTROLS={2002:145166731,2010:142856536,2021:147182123}
STATUS=['reviewed_rule_accepted','frozen_r5b_reviewed_baseline_preserved','reviewed_extension_rule_accepted','reviewed_case_accepted']

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    c=duckdb.connect(config={'threads':2,'memory_limit':'2GB'})
    s=c.execute('select * from read_parquet(?)',[str(SELECTED)]).fetchdf()
    # The only missing published 2002 Moscow territorial total is an explicit
    # parent row in Table 4; verify its value directly and against selected child rows.
    raw=pd.read_excel(RAW2002,sheet_name=0,header=None)
    raw_moscow=int(raw.iloc[2153,1])
    if raw_moscow!=10382754:raise RuntimeError(f'2002 Moscow parent changed: {raw_moscow}')
    selected_moscow=int(s[(s.census_year==2002)&(s.region_norm=='москва')].population.sum())
    if selected_moscow!=raw_moscow:raise RuntimeError('2002 selected Moscow components do not close to published parent')
    # Take 2021 source-row coordinates as the spatial anchor for each territory.
    roots=s[(s.census_year==2021)&s.region_norm.isin(['москва','санкт петербург','севастополь'])].copy()
    if len(roots)!=3 or roots.region_norm.duplicated().any():raise RuntimeError('2021 federal-city roots not unique')
    if roots[['latitude','longitude']].isna().any().any():raise RuntimeError('2021 territorial anchor coordinate missing')
    byregion=roots.set_index('region_norm')
    territory=[]
    def add(region,year,pop,source_id,name,quality,sourcefile,locator,source_sha,scope_note):
        anchor=byregion.loc[region]
        territory.append({'territory_key':{'москва':'RU-FED-MOW','санкт петербург':'RU-FED-SPB','севастополь':'RU-FED-SEV'}[region],
          'census_year':year,'territory_name':{'москва':'Москва','санкт петербург':'Санкт-Петербург','севастополь':'Севастополь'}[region],
          'region_norm':region,'territory_population':int(pop),'population_source_record_id':source_id,
          'population_value_quality':quality,'population_source_file':sourcefile,'population_source_locator':locator,
          'population_source_sha256':source_sha,'published_scope_note':scope_note,
          'latitude':float(anchor.latitude),'longitude':float(anchor.longitude),
          'coordinate_source_record_id':str(anchor.source_record_id),'coordinate_source_file':str(anchor.source_file),
          'coordinate_source_sha256':str(anchor.source_sha256),'coordinate_source_locator':f"{anchor.source_file}#:row_1based={int(anchor.source_row)}",
          'coordinate_source_quality':'territorial representative anchor from 2021 source row; not a territory centroid or census-date measurement',
          'coordinate_measurement_date_unknown':True,'territorial_identity_chain_status':'linked territory continuity; boundary/population comparability not asserted',
          'children_replaced_in_territory_coverage':True,'settlement_identity_asserted':False})
    # Moscow 2002 uses the explicit parent aggregate; it replaces all five selected
    # city/subordinate rows for this alternative territory-level spatial measure.
    add('москва',2002,raw_moscow,'aggregate:2002:Moscow_and_administratively_subordinate_settlements',
        'Москва','direct_published_parent_total','data/raw/2002_official_tom1/1_TOM_01_04.xls','Sheet 01-04; Excel row 2154; column 1',sha(RAW2002),'Urban total for Moscow and settlements subordinate to its administration; component rows sum exactly to this parent.')
    for region,year in [('санкт петербург',2002),('москва',2010),('санкт петербург',2010)]:
        row=s[(s.census_year==year)&(s.region_norm==region)]
        if len(row)!=1:raise RuntimeError(f'expected one selected city row: {region}/{year}, got {len(row)}')
        r=row.iloc[0]
        add(region,year,int(r.population),str(r.source_record_id),str(r.settlement_name),str(r.population_value_quality),str(r.source_file),f"{r.source_sheet}:source_row={int(r.source_row)}",str(r.source_sha256),
            'Official city-labelled census count; represented in separate territory layer under user instruction. Original source-scope ambiguity remains recorded; no boundary comparability asserted.')
    for region in ['москва','санкт петербург','севастополь']:
        r=byregion.loc[region]
        add(region,2021,int(r.population),str(r.source_record_id),str(r.settlement_name),str(r.population_value_quality),str(r.source_file),f"{r.source_sheet}:source_row={int(r.source_row)}",str(r.source_sha256),
            'Published federal-city territory total; city-subject aggregate, not an individual settlement observation.')
    t=pd.DataFrame(territory).sort_values(['territory_key','census_year'])
    if t.duplicated(['territory_key','census_year']).any():raise RuntimeError('duplicate territory/year')
    # Check population totals equal the selected layer in all ordinary years; 2002
    # Moscow's selected rows are replaced by the published parent, not added to it.
    rows=[]
    for y in (2002,2010,2021):
        d=s[(s.census_year==y)&s.is_additive_settlement_record.fillna(False)]
        roots_y=t[t.census_year==y]
        root_sum=int(roots_y.territory_population.sum())
        federal_selected=int(d[d.region_norm.isin(roots_y.region_norm)].population.sum())
        if root_sum!=federal_selected:raise RuntimeError(f'{y} territory roots do not conserve selected federal-region population: {root_sum} vs {federal_selected}')
        rows.append({'year':y,'selected_additive_population_federal_regions':federal_selected,'territory_layer_population':root_sum,'difference':root_sum-federal_selected,'official_control':CONTROLS[y]})
    OUT.mkdir(exist_ok=True)
    t.to_csv(OUT/'federal_territory_observations.csv',index=False)
    pd.DataFrame(rows).to_csv(OUT/'territory_population_conservation.csv',index=False)
    receipt={'status':'separate_user_authorized_spatial_territory_overlay_no_physical_NP_or_core_graph_mutation',
      'user_instruction':'Count federal territories in the spatial indicator; count individual settlements separately.',
      'inputs':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in [SELECTED,POINTS,EDGES,RAW2021,RAW2002]},
      'territory_observations':len(t),'territory_keys':t.territory_key.nunique(),'territory_rows_by_year':{str(y):int((t.census_year==y).sum()) for y in (2002,2010,2021)},
      'population_conservation_checks':rows,'double_counting':'territorial coverage replaces all additive selected rows within each corresponding federal city region; it does not add federal totals on top of constituent settlement rows.',
      'known_scope_events':{'Moscow':'2002 parent urban total includes subordinate settlements; later values are city/federal territory counts; 2012 boundary expansion prevents population comparability.','Saint Petersburg':'city/federal-territory continuity; source-specific administrative scope retained; population comparability not asserted.','Sevastopol':'outside Russian census scope in 2002/2010; represented only in 2021, not treated as zero or failed match.'},
      'coordinate_semantics':'2021 source-row location is reused as a spatial anchor for territory observations. It is not a polygon centroid, historical survey point, or settlement-level coordinate.',
      'outputs':{}}
    receipt['outputs']={f.name:sha(f) for f in OUT.iterdir() if f.is_file()}
    (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    (OUT/'README.md').write_text('''# Пространственный слой федеральных территорий\n\nСлой отвечает на отдельное решение пользователя: представлять опубликованные итоги Москвы, Санкт-Петербурга и Севастополя как федеральные территории в пространственном показателе; населённые пункты при этом остаются отдельными записями. В показателе территории заменяют записи дочернего состава соответствующего субъекта, поэтому федеральный итог не суммируется поверх населённых пунктов.\n\nКоордината берётся из строки территории 2021 года и ретроспективно используется как точка пространственного представления; это не точная дата измерения и не центроид территории. Связь по годам относится к территории субъекта, не доказывает сопоставимость населения или границ. Москва 2012 года и изменение охвата 2002/2010/2021 сохранены как ограничение. Севастополь имеет наблюдение только в 2021 году, поскольку российские переписи 2002 и 2010 годов его не охватывали.\n\nСлой аддитивен только к отдельному территориальному показателю. Основной граф физических НП и его coordinate ledger не изменяются. SHA источников, conservation checks и статусы содержатся в `receipt.json` и CSV.\n''',encoding='utf-8')
    print(json.dumps({'territory_observations':len(t),'conservation':rows,'output':str(OUT)},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
