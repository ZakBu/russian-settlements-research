"""Independent all-row test of adding exactly one mapped school settlement.

This does not import the production field kernel or rebuild routes. It checks
that every field increment is the independently evaluated K(t_i,new_school),
with own supply and unavailable origins treated separately. Other functions
must remain exactly unchanged, including missing-value masks.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd

KHVALYNSK='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:118265'
CANONICAL_CACHE_SHA='e572042d66a56966d746ad9cde60e975d61edf9cf3dd311e5a024ca31808159c'
KEYS=['origin_id','family','evidence_scenario','kernel','half_time_minutes']


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def exact_frames(old,new,scope):
    pd.testing.assert_frame_equal(old.reset_index(drop=True),new.reset_index(drop=True),check_exact=True)
    for column in old:
        if not np.array_equal(old[column].isna(),new[column].isna()):
            raise AssertionError(scope+': missing-value mask changed in '+column)
        if pd.api.types.is_float_dtype(old[column].dtype):
            a=old[column].to_numpy();b=new[column].to_numpy();known=~pd.isna(a)
            if not np.array_equal(a[known].view('uint64'),b[known].view('uint64')):
                raise AssertionError(scope+': floating-point bits changed in '+column)


def check(old_root,new_root,cache_dir,output):
    old_root,new_root,cache_dir=map(Path,(old_root,new_root,cache_dir))
    inputs={}
    for name in ('regional_roster.parquet','halo_roster.parquet','destinations.parquet',
                 'national_reference_with_endpoints.parquet'):
        old_hash=sha(old_root/'fields'/name);new_hash=sha(new_root/'fields'/name)
        if old_hash!=new_hash:raise AssertionError('Frozen field input changed: '+name)
        inputs[name]=old_hash
    full_path=cache_dir/'full_destination_costs.npy';full_hash=sha(full_path)
    if full_hash!=CANONICAL_CACHE_SHA:raise AssertionError('Canonical full road-cost cache changed')
    axis=pd.read_parquet(cache_dir/'origin_axis.parquet')
    dest=pd.read_parquet(old_root/'fields/destinations.parquet')
    found=dest.index[dest.source_record_id.eq(KHVALYNSK)]
    if len(found)!=1:raise AssertionError('Exactly one Khvalynsk destination required')
    col=int(dest.loc[found[0],'destination_index'])
    full=np.load(full_path,mmap_mode='r');row_lookup=dict(zip(axis.source_record_id,axis.full_row_index))
    before_path=old_root/'physical_official/functional_potentials.parquet'
    after_path=new_root/'physical_official/functional_potentials.parquet'
    before=pd.read_parquet(before_path).sort_values(KEYS).reset_index(drop=True)
    after=pd.read_parquet(after_path).sort_values(KEYS).reset_index(drop=True)
    if before.duplicated(KEYS).any() or after.duplicated(KEYS).any():raise AssertionError('Duplicate field primary keys')
    exact_frames(before[KEYS],after[KEYS],'field axes')
    other=before.family.ne('school')
    exact_frames(before.loc[other],after.loc[other],'other fifteen functions')
    a=before.loc[~other].reset_index(drop=True);b=after.loc[~other].reset_index(drop=True)
    if len(a.origin_id.unique())!=1821 or set(a.evidence_scenario)!= {'all_dated_known','nonhistorical_evidence_only'}:
        raise AssertionError('The full pilot and both evidence scenarios are required')
    if len(a)!=1821*8*2:raise AssertionError('Unexpected school field dimensions')
    times=np.array([full[row_lookup[x],col] for x in a.origin_id],dtype=float)
    known=a.origin_route_geometry_known.to_numpy(bool)
    if not np.array_equal(known,b.origin_route_geometry_known):raise AssertionError('Origin route mask changed')
    if np.isnan(times[known]).any() or not np.isnan(times[~known]).all():raise AssertionError('Route cost/availability mismatch')
    half=a.half_time_minutes.to_numpy(float)
    exponent=np.where(a.kernel.eq('exponential'),times/half,(times/half)**2)
    if not a.kernel.isin(['exponential','gaussian']).all():raise AssertionError('Unexpected decay family')
    # Independently use exp/log, rather than production np.exp2.
    weight=np.exp(-math.log(2.)*exponent)
    own=a.origin_id.eq(KHVALYNSK).to_numpy(dtype=float)
    reach=np.isfinite(times).astype(float)
    statistics={}
    def delta(column,expected,valid=None,atol=1e-10):
        x=a[column].to_numpy(dtype=float);y=b[column].to_numpy(dtype=float)
        if not np.array_equal(np.isnan(x),np.isnan(y)):raise AssertionError('Changed NA mask: '+column)
        use=~np.isnan(x) if valid is None else valid
        error=np.abs((y[use]-x[use])-expected[use])
        if not np.allclose(y[use]-x[use],expected[use],atol=atol,rtol=1e-10):
            raise AssertionError('Wrong field increment: '+column+' max error '+str(error.max()))
        statistics[column]={'checked_rows':int(use.sum()),'max_absolute_increment_error':float(error.max(initial=0.))}
    expected_known=np.where(known,weight,np.nan)
    delta('known_np_offer_potential',expected_known)
    delta('known_np_offer_potential_lower',np.where(known,weight,own))
    delta('known_np_offer_potential_upper',np.where(known,weight,1.))
    delta('external_known_np_offer_potential_lower',np.where(known,weight-own,0.))
    delta('external_known_np_offer_potential_upper',np.where(known,weight-own,1.-own))
    delta('own_known_np_function_presence',own,atol=0.)
    delta('known_np_function_offer_count',np.ones(len(a)),atol=0.)
    for column in ('routed_np_offer_count_within_horizon','routed_np_offer_count'):
        delta(column,reach,atol=0.)
    delta('known_np_offers_unreachable_in_road_model',1.-reach,atol=0.)
    changed={'known_np_offer_potential','known_np_offer_potential_lower','known_np_offer_potential_upper',
        'own_known_np_function_presence','external_known_np_offer_potential_lower',
        'external_known_np_offer_potential_upper','known_np_function_offer_count',
        'routed_np_offer_count_within_horizon','routed_np_offer_count',
        'known_np_offers_unreachable_in_road_model','nearest_known_offer_access_score','nearest_known_offer_minutes'}
    exact_frames(a[[c for c in a if c not in changed]],b[[c for c in b if c not in changed]],'unchanged school metadata')
    nearest=b.nearest_known_offer_minutes.to_numpy(float)
    new_exponent=np.where(b.kernel.eq('exponential'),nearest/half,(nearest/half)**2)
    expected_access=np.exp(-math.log(2.)*new_exponent)
    if not np.array_equal(np.isnan(expected_access),b.nearest_known_offer_access_score.isna()):
        raise AssertionError('Nearest-school accessibility mask mismatch')
    if not np.allclose(expected_access,b.nearest_known_offer_access_score,atol=1e-12,rtol=1e-12,equal_nan=True):
        raise AssertionError('Nearest-school accessibility is inconsistent with the new nearest time')
    presence_changes={}
    for scenario in ('all_dated_known','nonhistorical_evidence_only'):
        sets=[]
        for root in (old_root,new_root):
            p=pd.read_parquet(root/'physical_official/np_function_presence_enriched.parquet')
            if scenario=='nonhistorical_evidence_only':p=p[~p.historical_only]
            sets.append(set(zip(p.source_record_id.astype(str),p.family.astype(str))))
        added=sets[1]-sets[0];removed=sets[0]-sets[1]
        if added!={(KHVALYNSK,'school')} or removed:raise AssertionError('Inventory delta is not exactly one school NP')
        presence_changes[scenario]={'added':[[x,y] for x,y in sorted(added)],'removed':[]}
    result={'passed':True,'source_record_id_added':KHVALYNSK,'origins':1821,'school_field_rows':len(a),
        'known_origin_field_rows':int(known.sum()),'unknown_origin_field_rows':int((~known).sum()),
        'own_school_field_rows':int(own.sum()),'other_families':15,'other_function_rows_exactly_unchanged':int(other.sum()),
        'independent_kernel':'exp(-log(2)*t/h) or exp(-log(2)*(t/h)^2)',
        'cache_sha256':full_hash,'before_potentials_sha256':sha(before_path),'after_potentials_sha256':sha(after_path),
        'frozen_field_inputs':inputs,'presence_change_by_evidence':presence_changes,
        'increment_checks':statistics,'other_function_missing_masks_and_known_float_bits_exact':True,
        'transport_or_population_recalculated':False}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(__doc__)
    for name in ('before-root','after-root','cache-dir','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(check(a.before_root,a.after_root,a.cache_dir,a.output),ensure_ascii=False))


if __name__=='__main__':main()
