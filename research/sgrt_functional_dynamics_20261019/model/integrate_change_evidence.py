#!/usr/bin/env python3
"""Align change evidence types without declaring all changes function transfers."""
from pathlib import Path
import json
import pandas as pd
from build_integrated_graph import resolve,norm

R=Path(__file__).resolve().parent.parent
O=R/'model/results'

def build(out=None):
    global O
    if out is not None:O=Path(out)
    events=[]
    p=pd.read_parquet(R.parent/'anchor_research_20261019/data/point_axis.parquet')
    p['_name']=p.name.map(norm);p['_region']=p.region.map(norm);p['_mun']=p.municipality_upper_2021.map(norm)
    h=pd.read_csv(O/'history_positive_assignment_transitions.csv')
    for i,r in h.iterrows():
        events.append(dict(event_id=f'EDU:{i}',function_group='education',unit_id=r.origin_uid,unit_name=r.origin_name,from_date=f'{r.from_document_year}-school-admission',to_date=f'{r.to_document_year}-school-admission',change_kind='normative_provider_changed' if r.normative_provider_changed else 'same_normative_provider',old_provider=r.old_provider_name,new_provider=r.new_provider_name,measured_quantity='positive_assignment_of_origin',change_value=int(r.normative_provider_changed),documented_provider_change=bool(r.normative_provider_changed),physical_closure_proven=False,actual_flow_transfer_proven=False,evidence_type='paired_statutory_documents',same_place_uid=r.origin_uid))
    med=R/'medical/tariff_snapshots.csv'
    if med.exists():
        m=pd.read_csv(med);key=['organization_code','unit_code']
        a=m[m.snapshot_date.eq('2025-01-01')].set_index(key);b=m[m.snapshot_date.eq('2026-01-01')].set_index(key)
        assert a.index.is_unique and b.index.is_unique
        for i,k in enumerate(sorted(set(a.index)|set(b.index))):
            old=a.loc[k] if k in a.index else None;new=b.loc[k] if k in b.index else None;r=new if new is not None else old
            uid,st=resolve(r.settlement,r.region,r.municipality,p)
            if old is None:kind='newly_listed_tariff_unit_not_proven_opening'
            elif new is None:kind='absent_later_tariff_not_proven_closure'
            elif old.medical_worker_present!=new.medical_worker_present:kind='tariff_staff_presence_flag_changed'
            else:kind='same_tariff_staff_presence_flag'
            delta=float(new.registered_population-old.registered_population) if new is not None and old is not None else None
            events.append(dict(event_id=f'MED:{i}',function_group='health',unit_id=':'.join(map(str,k)),unit_name=r.unit_name,from_date='2025-01-01',to_date='2026-01-01',change_kind=kind,old_provider='',new_provider='',measured_quantity='tariff_registered_population_not_census_or_visits',change_value=delta,documented_provider_change=False,physical_closure_proven=False,actual_flow_transfer_proven=False,evidence_type='paired_tariff_lists',same_place_uid=uid,place_match_status=st,source_url=r.source_url))
    n=pd.read_csv(O/'documented_provider_profiles.csv')
    for i,r in n.iterrows():
        events.append(dict(event_id=f'LEGAL:{i}',function_group='consumer_services_registered_7_groups',unit_id=r.id,unit_name=r['name'],from_date='2016',to_date='2021',change_kind='registered_group_count_changed_or_stable_physical_function_change_unidentified',old_provider='',new_provider='',measured_quantity='RFSD_registered_function_group_count_coded_baseline',change_value=int(r.direct_consumer_function_diversity_2021-r.direct_consumer_function_diversity_2016),documented_provider_change=False,physical_closure_proven=False,actual_flow_transfer_proven=False,evidence_type='legal_registration_witness_coverage_geocoding_sensitive',same_place_uid=r.id))
    e=pd.DataFrame(events)
    assert e.event_id.is_unique
    e.to_csv(O/'functional_change_evidence.csv',index=False);e.to_parquet(O/'functional_change_evidence.parquet',index=False)
    counts=e.groupby(['evidence_type','change_kind']).size().reset_index(name='n')
    counts.to_csv(O/'functional_change_summary.csv',index=False)
    audit={'events':len(e),'normative_provider_changes':int(e.documented_provider_change.sum()),'measured_flow_transfers':int(e.actual_flow_transfer_proven.sum()),'proven_physical_closures':int(e.physical_closure_proven.sum()),'conclusions':'Function transfer established only for one statutory school assignment; medical tariff/organization and RFSD changes remain distinct and do not establish physical functional loss.'}
    (O/'CHANGE_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2));print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':build()
