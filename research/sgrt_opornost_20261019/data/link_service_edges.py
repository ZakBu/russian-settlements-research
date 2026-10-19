"""Exact contextual links only; preserve ambiguous and absent source names."""
from pathlib import Path
import argparse, hashlib, json, re
import pandas as pd


def norm(x):
    return re.sub(r'\s+', ' ', str(x).lower().replace('ё','е').replace('–','-').replace('—','-').strip())


def region_key(x):
    return norm(x).replace('республика ', '').replace(' область','').replace(' край','')


def municipality_key(x):
    x = norm(x).replace('"','').replace('«','').replace('»','')
    for w in ['муниципальное образование', 'муниципальный', 'городской', 'округ', 'район']:
        x = re.sub(r'\b'+w+r'\b',' ',x)
    return norm(x)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--axis',type=Path,required=True)
    ap.add_argument('--services',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    p=pd.read_parquet(a.axis)
    p['rk']=p.region.map(region_key);p['mk']=p.municipality_upper_2021.map(municipality_key);p['nk']=p.name.map(norm)
    # Search dictionary makes every source resolution independently reproducible.
    lookup={k:g for k,g in p.groupby(['rk','mk','nk'],dropna=False)}
    ledger=[]
    def resolve(row,name,role,kind=None):
        key=(region_key(row['region']), municipality_key(row['municipality']), norm(name))
        found=lookup.get(key,p.iloc[:0])
        if kind and not pd.isna(kind):
            found=found[found.type.map(norm).eq(norm(kind))]
        status='exact_name_region_municipal_label_unique' if len(found)==1 else ('ambiguous_exact_context_name' if len(found)>1 else 'not_in_three_census_cohort_exact_context')
        result=dict(uid=found.iloc[0].id if len(found)==1 else None,match_status=status)
        for r in found.itertuples():
            ledger.append(dict(source_record=row.get('edge_id',row.get('inventory_id',name)),role=role,source_name=name,
                candidate_uid=r.id,candidate_name=r.name,candidate_type=r.type,
                source_region=row['region'],source_municipality=row['municipality'],panel_municipality=r.municipality_upper_2021,
                accepted=len(found)==1,status=status,
                identity_basis='exact_normalized_name_region_municipal_label; municipal_legal_type_removed; historical_boundary_not_asserted'))
        if not len(found):
            ledger.append(dict(source_record=row.get('edge_id',row.get('inventory_id',name)),role=role,source_name=name,
                candidate_uid=None,candidate_name=None,candidate_type=None,source_region=row['region'],source_municipality=row['municipality'],
                panel_municipality=None,accepted=False,status=status,identity_basis='no_fuzzy_or_nearest_resolution'))
        return result
    edges=pd.read_csv(a.services/'service_edges.csv')
    records=[]
    for row in edges.to_dict('records'):
        o=resolve(row,row['origin_name'],'origin',row.get('origin_type'))
        d=resolve(row,row['provider_settlement'],'destination',row.get('provider_type'))
        row.update(origin_uid=o['uid'],destination_uid=d['uid'],origin_match_status=o['match_status'],destination_match_status=d['match_status'])
        row['both_endpoints_linked']=bool(o['uid'] and d['uid'])
        row['endpoint_same_place']=bool(row['both_endpoints_linked'] and o['uid']==d['uid'])
        records.append(row)
    e=pd.DataFrame(records);e.to_csv(a.out/'service_edges_linked.csv',index=False)
    n=pd.read_csv(a.services/'school_feature_nodes.csv');nr=[]
    for row in n.to_dict('records'):
        z=resolve(row,row['name'],'school_inventory_node',row.get('settlement_type'))
        row.update(id=z['uid'],match_status=z['match_status']);nr.append(row)
    linked=pd.DataFrame(nr);linked.to_csv(a.out/'school_feature_nodes_linked.csv',index=False)
    inventory=pd.read_csv(a.services/'school_inventory.csv');ir=[]
    for row in inventory.to_dict('records'):
        z=resolve(row,row['provider_settlement'],'school_inventory_record',row.get('provider_type'))
        row.update(id=z['uid'],match_status=z['match_status']);ir.append(row)
    pd.DataFrame(ir).to_csv(a.out/'school_inventory_linked.csv',index=False)
    pd.DataFrame(ledger).to_csv(a.out/'service_identity_candidate_ledger.csv',index=False)
    checks=[dict(test='every_source_edge_retained',passed=len(e)==len(edges)),
        dict(test='no_duplicate_edge_ids',passed=e.edge_id.is_unique),
        dict(test='no_ambiguous_origin_accepted',passed=e.loc[e.origin_match_status.str.startswith('ambiguous'),'origin_uid'].isna().all()),
        dict(test='no_ambiguous_destination_accepted',passed=e.loc[e.destination_match_status.str.startswith('ambiguous'),'destination_uid'].isna().all()),
        dict(test='all_inventory_nodes_retained',passed=len(linked)==len(n)),
        dict(test='only_existing_UIDs',passed=set(e.origin_uid.dropna())|set(e.destination_uid.dropna()) <= set(p.id))]
    assert all(x['passed'] for x in checks)
    result=dict(status='PASS',author='anchor_data; demographic axis author',
        edges=len(e),both_linked=int(e.both_endpoints_linked.sum()),distinct_linked_origins=int(e.origin_uid.nunique()),
        linked_provider_nodes=int(e.destination_uid.nunique()),
        origin_status=e.origin_match_status.value_counts().to_dict(),destination_status=e.destination_match_status.value_counts().to_dict(),
        inventory_nodes=len(n),linked_inventory_nodes=int(linked.id.notna().sum()),
        identity_normalization='case/whitespace/ё-to-е/dash; region administrative suffix and municipal legal-type words removed; no adjectival stemming, no fuzzy match, no distance',
        municipal_territory_continuity='not independently established between source dates and 2021; exact named-context used only for identity disambiguation',
        model_feature_inventory_separate_from_holdout_edges=True,
        input_sha256={str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in [a.axis,a.services/'service_edges.csv',a.services/'school_feature_nodes.csv',a.services/'school_inventory.csv']},
        checks=checks)
    (a.out/'service_linkage_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
