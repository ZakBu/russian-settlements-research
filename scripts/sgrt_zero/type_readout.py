#!/usr/bin/env python3
"""Correct descriptive metadata on frozen partitions; never reroute or regroup."""
import argparse
import json
from pathlib import Path
import pandas as pd
try:
    from .hierarchy import demographic_summaries,inherit_provider_metadata,file_sha256
except ImportError:
    from hierarchy import demographic_summaries,inherit_provider_metadata,file_sha256


def centre_periphery(units,members,reference,reference_records=None):
    """Separate an unambiguous NP centre from ordinary demand members.

    External centres are context, never added to member population. Unknown
    sites block a unique centre; towns in the surrounding group stay explicit.
    """
    if reference_records is None:reference_records=reference_dict(reference)
    grouped=members.groupby('unit_id',sort=False).origin_id.agg(list).to_dict()
    keys_column='cumulative_provider_keys_json' if 'cumulative_provider_keys_json' in units else 'provider_keys_json'
    records=[]
    for row in units.itertuples():
        keys=json.loads(getattr(row,keys_column));known=len(keys)==1 and keys[0].startswith('np:')
        result={'unit_id':row.unit_id,'unique_np_centre_established':known,
          'centre_is_descriptive_context':True,'centre_population_added_to_member_budget':False,
          'centre_reference_population_role':None,'centre_is_nonadditive_city_aggregate':None,
          'surrounding_scope':'ordinary_demand_members_except_centre_not_necessarily_all_rural',
          'historical_boundary_equivalence_established':False,'word_causal_type_established':False}
        cid=keys[0][3:] if known else None;result['centre_source_record_id']=cid
        if not known:
            result['centre_identity_status']='no_offer' if not keys else 'multiple_or_unidentified_supplier_anchors'
            for a in [2002,2010]:
                for field in ['centre_direction','surrounding_direction','rural_surrounding_direction','joint_centre_surrounding_direction']:result[f'{field}_{a}_2021']='unknown'
            records.append(result);continue
        if cid not in reference_records:raise ValueError('Centre missing from accepted reference')
        centre=reference_records[cid];ids=grouped[row.unit_id]
        result['centre_reference_population_role']=centre['population_role']
        result['centre_is_nonadditive_city_aggregate']=centre['population_role']=='external_context_nonadditive'
        surrounding=[reference_records[x] for x in ids if x!=cid]
        ordinary=[x for x in surrounding if x['population_role']=='ordinary_settlement_record']
        urban=[x for x in ordinary if x.get('settlement_type_2021') in ['город','пгт']]
        unknown_type=[x for x in ordinary if pd.isna(x.get('settlement_type_2021'))]
        rural=[x for x in ordinary if not pd.isna(x.get('settlement_type_2021')) and x.get('settlement_type_2021') not in ['город','пгт']]
        result.update(centre_identity_status='one_accepted_np_anchor',centre_name=centre['name'],centre_inside_demand_group=cid in ids,
          surrounding_nonordinary_records_excluded=len(surrounding)-len(ordinary),surrounding_urban_records=len(urban),surrounding_settlement_type_unknown_records=len(unknown_type))
        for label,part in [('surrounding',ordinary),('rural_surrounding',rural)]:
            result[label+'_records']=len(part)
            for y in [2002,2010,2021]:
                values=[x[f'population_{y}'] for x in part if observed(x,y)]
                result[f'{label}_population_{y}_known_sum']=sum(values) if values else None
                result[f'{label}_population_{y}_known_records']=len(values)
            for a in [2002,2010]:
                cohort=[x for x in part if observed(x,a) and observed(x,2021)]
                complete=bool(part) and len(cohort)==len(part) and not (label=='rural_surrounding' and unknown_type)
                start=sum(x[f'population_{a}'] for x in cohort) if cohort else None
                end=sum(x['population_2021'] for x in cohort) if cohort else None
                result[f'{label}_comparable_records_{a}_2021']=len(cohort)
                result[f'{label}_complete_{a}_2021']=complete
                result[f'{label}_cohort_start_{a}_2021']=start;result[f'{label}_cohort_end_{a}_2021']=end
                result[f'{label}_direction_{a}_2021']=direction(start,end) if complete else 'unknown'
        for y in [2002,2010,2021]:
            result[f'centre_population_{y}']=float(centre[f'population_{y}']) if centre['population_role']=='ordinary_settlement_record' and observed(centre,y) else None
            result[f'centre_population_value_quality_{y}']=centre.get(f'population_value_quality_{y}')
        for a in [2002,2010]:
            cd=direction(result[f'centre_population_{a}'],result['centre_population_2021']);sd=result[f'surrounding_direction_{a}_2021']
            result[f'centre_direction_{a}_2021']=cd
            result[f'joint_centre_surrounding_direction_{a}_2021']=cd+'__'+sd if cd!='unknown' and sd!='unknown' else 'unknown'
        records.append(result)
    return pd.DataFrame(records)


def observed(record,year):
    credit=record[f'credit_{year}']
    return pd.notna(credit) and bool(credit) and pd.notna(record[f'population_{year}'])


def reference_dict(reference):
    columns=['source_record_id','name','population_role','settlement_type_2021']+[f'{field}_{y}' for y in [2002,2010,2021] for field in ['population','credit','population_value_quality']]
    ref=reference[reference.source_record_id.notna()][[x for x in columns if x in reference]].set_index('source_record_id')
    if not ref.index.is_unique:raise ValueError('Repeated census identity')
    return ref.to_dict('index')


def direction(start,end):
    if pd.isna(start) or pd.isna(end):return 'unknown'
    return 'growth' if end>start else 'decline' if end<start else 'unchanged'


def run(root,output):
    if output.resolve()==root.resolve() or root.resolve() in output.resolve().parents:
        raise ValueError('Use a separate audit directory outside the frozen public source')
    reference_path=root/'context/analysis_reference.parquet';reference=pd.read_parquet(reference_path);reference_records=reference_dict(reference)
    paths=sorted(root.glob('hierarchy/*/level0_units.parquet'))+sorted(root.glob('upward/*/*/units.parquet'))+sorted(root.glob('upward_extended/*/*/*/units.parquet'))
    if len(paths)!=15:raise ValueError('Expected all fifteen frozen partitions')
    code_paths=[Path(__file__),Path(__file__).with_name('hierarchy.py')]
    results={};corrected={};fingerprints={p:file_sha256(p) for p in [reference_path,*code_paths]}
    for path in paths:
        relative=path.parent.relative_to(root);zero=path.name.startswith('level0_')
        mp=path.parent/('level0_memberships.parquet' if zero else 'memberships.parquet')
        fingerprints[path]=file_sha256(path);fingerprints[mp]=file_sha256(mp)
        units=pd.read_parquet(path);members=pd.read_parquet(mp)
        if members.origin_id.duplicated().any():raise ValueError('Repeated demand point')
        dem=demographic_summaries(members,reference,compute_geometry=False)
        units=units.drop(columns=[c for c in dem if c!='unit_id' and c in units]).merge(dem,on='unit_id',validate='one_to_one')
        units['demographic_type']=units.member_direction_2002_2021
        if zero:
            units['functional_type_code']=units.type_code;units['operation_code']='initial_daily_profile_partition'
            units['cumulative_provider_keys_json']=units.provider_keys_json
        else:
            cp=path.parent/'subsystem_crosswalk.parquet';fingerprints[cp]=file_sha256(cp);cross=pd.read_parquet(cp)
            if relative.parts[0]=='upward':
                index=int(relative.name[:2]);previous='hierarchy/daily_20_school30_wb' if index==1 else next(k for k in corrected if k.startswith('upward/') and Path(k).name.startswith(f'{index-1:02d}_'))
            else:
                index=int(relative.name[:2]);previous=next(k for k in corrected if k.startswith('upward/') and Path(k).name.startswith('01_')) if index==2 else next(k for k in corrected if k.startswith('/'.join(relative.parts[:3])+'/') and Path(k).name.startswith(f'{index-1:02d}_'))
            # Frozen v1 real_provider_keys contain CURRENT-layer offers only.
            current={row.unit_id:json.loads(row.real_provider_keys_json) for row in units.itertuples()}
            units=inherit_provider_metadata(units,corrected[previous],cross,current)
            if 'all_provider_keys_json' in units:
                same=[set(json.loads(a))==set(json.loads(b)) for a,b in zip(units.all_provider_keys_json,units.cumulative_provider_keys_json)]
                if not all(same):raise ValueError('Cumulative supplier identities differ from frozen inherited offer metadata')
        target=output/relative;target.mkdir(parents=True,exist_ok=True)
        units.to_parquet(target/path.name,index=False,compression='zstd')
        centre=centre_periphery(units,members,reference,reference_records);centre.to_parquet(target/'centre_periphery.parquet',index=False,compression='zstd')
        corrected[str(relative)]=units
        results[str(relative)]={'units':len(units),'member_input_sha256':fingerprints[mp],
          'unit_output_sha256':file_sha256(target/path.name),'membership_changed':False,
          'legacy_inherited_provider_sets_preserved':True,
          'functional_type_counts':units.functional_type_code.value_counts().to_dict(),
          'operation_counts':units.operation_code.value_counts().to_dict(),
          'member_direction_2002_2021':units.member_direction_2002_2021.value_counts().to_dict(),
          'unique_np_centres':int(centre.unique_np_centre_established.sum()),
          'joint_centre_surrounding_2002_2021':centre.joint_centre_surrounding_direction_2002_2021.value_counts().to_dict()}
        print(json.dumps({'partition':str(relative),'units':len(units)},ensure_ascii=False),flush=True)
    if any(file_sha256(p)!=sha for p,sha in fingerprints.items()):raise RuntimeError('Frozen input changed during metadata readout')
    summary={'partitions':results,'source_root':str(root),'input_sha256':{str(k):v for k,v in fingerprints.items()},
       'source_code_sha256':{str(p):file_sha256(p) for p in [Path(__file__),Path(__file__).with_name('hierarchy.py')]},
       'only_metadata_recalculated':True,'no_membership_candidate_or_travel_time_changed':True,
       'centre_population_never_added_to_demand_population':True,'word_causal_types_established':False}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.root,a.output)
