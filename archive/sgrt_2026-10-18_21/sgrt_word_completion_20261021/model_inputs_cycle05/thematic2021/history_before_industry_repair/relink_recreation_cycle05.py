"""Relink frozen historical assertions to the extended, additive 2021 NP frame.

Keep the accepted physical-site partition fixed. A canonical site is represented
by its source-ID representative, so it cannot supply positive evidence to two NP.
Current resort designations are retained only as explicitly dated context fields.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / 'model_inputs_cycle05' / 'thematic2021'

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(2**20), b''):
            h.update(b)
    return h.hexdigest()

def xyz(lat, lon):
    a, b = np.radians(lat), np.radians(lon)
    return np.column_stack([np.cos(a)*np.cos(b), np.cos(a)*np.sin(b), np.sin(a)])

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ap = ROOT/'data/source_controls_cycle05/full_settlement_axis_cycle05_federal_children.parquet'
    op = HERE/'recreation_objects_2021.parquet'
    tp = ROOT/'typology/settlement_features.parquet'
    axis, objects, old = pd.read_parquet(ap), pd.read_parquet(op), pd.read_parquet(tp)
    frame = axis.loc[axis.population_2021.notna() & axis.is_additive_source_unit.fillna(False)
                     & ~axis.axis_kind.fillna('').str.contains('territory', case=False)
                     & np.isfinite(axis[['lat','lon']].to_numpy(float)).all(axis=1)].copy()
    tree = cKDTree(xyz(frame.lat.to_numpy(), frame.lon.to_numpy()))
    sites = objects.loc[objects.site_id.eq(objects.canonical_site_id)].copy()
    assert sites.canonical_site_id.is_unique
    assert set(sites.canonical_site_id) == set(objects.canonical_site_id)
    good = np.isfinite(sites[['lat','lon']].to_numpy(float)).all(axis=1)
    sites['old_nearest_axis_id'] = sites.nearest_axis_id
    sites['nearest_axis_id'] = None
    sites['nearest_distance_km'] = np.nan
    chord, index = tree.query(xyz(sites.loc[good,'lat'].to_numpy(), sites.loc[good,'lon'].to_numpy()))
    sites.loc[good,'nearest_axis_id'] = frame.id.to_numpy()[index]
    sites.loc[good,'nearest_distance_km'] = 12742.0176*np.arcsin(np.clip(chord/2,0,1))
    sites['count_eligible'] = sites.nearest_distance_km.le(3) & ~sites.inactive_source_asserted
    sites.to_parquet(OUT/'recreation_canonical_site_links.parquet', index=False)
    features = axis[['id']].copy()
    for group, column in [('accommodation','osm_accommodation_points_within3km'),
                           ('allotments','osm_allotment_geometries_within3km')]:
        count = sites.loc[sites.count_eligible & sites.source_group.eq(group)].groupby('nearest_axis_id').size()
        features[column] = features.id.map(count).fillna(0).astype('int32')
    for flag, col in [('recreation_facility_evidence','osm_accommodation_points_within3km'),
                       ('dacha_landuse_evidence','osm_allotment_geometries_within3km')]:
        features[flag] = pd.array(np.where(features[col].gt(0),True,None),dtype='boolean')
    features['recreation_dacha_evidence'] = pd.array(np.where(features.iloc[:,1:3].sum(axis=1).gt(0),True,None),dtype='boolean')
    features['recreation_source_snapshot'] = '2021-01-01'
    features['recreation_absent_record_is_unknown'] = True
    # Current-only positive witnesses cannot define a retrospective 2021 type.
    replaced = set(features)-{'id'}
    current = [c for c in old if c.startswith(('sanatorium_','designated_resort_','official_resort_'))]
    old = old.rename(columns={c:'context2026_'+c for c in current})
    merged = axis[['id']].merge(old.drop(columns=list(replaced & set(old))),on='id',how='left',validate='one_to_one')
    merged = merged.merge(features,on='id',how='left',validate='one_to_one')
    # Missing contemporary resort observations remain unknown in the main family.
    for c in current:
        merged[c] = pd.array([pd.NA]*len(merged), dtype='boolean' if c.endswith('_evidence') else 'Float64')
    merged.to_parquet(OUT/'settlement_thematic_features_2021.parquet',index=False)
    features.to_parquet(OUT/'settlement_recreation_features_full_axis.parquet',index=False)
    receipt = {'status':'COMPUTED_PENDING_INDEPENDENT_REVIEW','source_snapshot':'2021-01-01',
        'inputs':{str(p.relative_to(ROOT)):sha(p) for p in [ap,op,tp]},'code_sha256':sha(Path(__file__)),
        'axis_rows':len(axis),'dated_additive_reference_rows':len(frame),'raw_assertions':len(objects),
        'canonical_sites':len(sites),'sites_reassigned':int(sites.old_nearest_axis_id.ne(sites.nearest_axis_id).sum()),
        'eligible_sites':int(sites.count_eligible.sum()),'positive_recreation_np':int(features.recreation_facility_evidence.fillna(False).sum()),
        'positive_dacha_np':int(features.dacha_landuse_evidence.fillna(False).sum()),
        'canonical_partition_fixed_before_model':True,'no_current_resort_witness_in_primary':True,
        'unknown_not_absence':True,'other_industrial_current_context_not_repaired_in_this_step':True,
        'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.glob('*.parquet')}}
    (OUT/'relink_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__ == '__main__':
    main()
