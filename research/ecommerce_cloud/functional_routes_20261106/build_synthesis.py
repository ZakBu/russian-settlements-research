"""Join hand-read place evidence to the unchanged census and fixed centre frame.

Seven rows are place-level illustrations, not observations for an effect estimator.
Unknown reviewer origins stay empty. Source truth is assessed by reading, not asserts.
"""
from pathlib import Path
import csv, hashlib, json
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE = ROOT / 'work/sources/research/ecommerce_settlement_20261024'
INPUTS = {
    'axis': (BASE/'national/national_target_source2021.parquet',
             '89fce76fe330dd33bd3b5f8496f3e46e7faffaf55d045193bd4070f8a2d017f2'),
    'centres': (BASE/'settlement_role_stage_20261024/system/centre_system_demography.csv',
                'c2fa7ab6874ebe32709a8737599e3a0c9d02305501a2a85104f76eaba29ae57e')}

# Place identities are manual source-backed decisions; no nearest-point assignment.
# current place id, prior centre id, date, operator, source type, origin explicitly
# named, current-status evidence, source and inherited/new provenance.
CASES = [
    (57566,57560,'2024-07-29','Wildberries','public_review',False,
     'self_reported_destination_change',
     'https://yandex.com/maps/org/wildberries/46722379084/reviews/',
     '../observed_operations_20261104/DESTINATION_CHANGE_RU.md',False),
    (57842,57560,'2023-12-26','Ozon','public_review',False,
     'self_reported_destination_change_other_old_destination_Retyun_also_named',
     'https://yandex.com/maps/org/ozon/132706536016/reviews/',
     '../observed_operations_20261104/SYSTEMATIC_REVIEW_LEN_RU.md',False),
    (142806,142746,'2023-10-30/2024-02-04','Ozon','public_reviews_same_card',False,
     'self_reported_destination_change_old_channel_unspecified',
     'https://yandex.com/maps/org/ozon/96580335216/reviews/',
     '../observed_operations_20261104/SYSTEMATIC_REVIEW_NN_TVER_RU.md',False),
    (47702,49226,'2025-10-20','Wildberries','advertising_report',True,
     'reported_old_shopping_destination_and_current_local_receipt',
     'https://ngs24.ru/text/gorod/2025/10/20/76079580/',
     '../observed_operations_20261104/NEW_ROUTES_RU.md',False),
    (80217,80161,'2025-11-30','Ozon','public_review',False,
     'self_reported_prior_destination_and_current_receipt_old_channel_unspecified',
     'https://yandex.com/maps/org/ozon/168953117131/reviews/',
     'observed_west/OBSERVED_WEST_RU.md',True),
    (69477,69320,'2025-02-09/2025-08-04','Wildberries','public_reviews_same_card',False,
     'self_reported_destination_change_two_reviews_one_place',
     'https://yandex.com/maps/org/wildberries/148433571902/reviews/',
     'observed_west/OBSERVED_WEST_RU.md',True),
    (165960,166010,'2024-01-19','Wildberries','local_news_opening_report',True,
     'named_old_residential_link_working_local_alternative_after_trips_unmeasured',
     'https://prochukotku.ru/news/msp/pervyy_punkt_wildberries_otkrylsya_v_poselke_ugolnye_kopi/',
     'observed_east/OBSERVED_EAST_RU.md',True),
]

def main():
    for path, digest in INPUTS.values():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path
    axis=pd.read_parquet(INPUTS['axis'][0]).set_index('source_record_id_2021')
    centres=pd.read_csv(INPUTS['centres'][0]).set_index('source_record_id_2021')
    assert axis.index.is_unique and len(axis)==144151
    assert int(centres.medium_primary2002.sum())==1273
    prefix='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:'
    rows=[]
    for cur, prior, date, operator, kind, origin_known, status, url, lineage, new in CASES:
        curid,priorid=prefix+str(cur),prefix+str(prior)
        a,b=axis.loc[curid],axis.loc[priorid]
        assert bool(centres.loc[priorid,'medium_primary2002'])
        assert (HERE/lineage).is_file(), lineage
        rows.append(dict(current_place_id=curid,current_receipt_place=a.name_2021,
            current_place_type=a.type_2021,current_place_region=a.region_2021,
            current_place_district=a.district_2021,
            prior_centre_id=priorid,prior_centre=b.name_2021,
            prior_centre_population2002=int(b.population_2002),prior_centre_fixed1273=True,
            residential_origin=a.name_2021 if origin_known else '',
            origin_status='explicit_in_article' if origin_known else 'unknown',
            operator=operator,source_report_date=date,source_kind=kind,evidence_status=status,
            after_trip_reduction_measured=False,physical_goods_bypass_proven=False,
            first_added_in_this_pass=new,source_url=url,lineage_note=lineage))
    result=pd.DataFrame(rows)
    assert result.current_place_id.is_unique
    result.to_csv(HERE/'functional_evidence.csv',index=False)
    summary=dict(place_cases=len(rows),distinct_prior_fixed_centres=result.prior_centre_id.nunique(),
        new_place_cases=int(result.first_added_in_this_pass.sum()),
        new_prior_fixed_centres=result.loc[result.first_added_in_this_pass,'prior_centre_id'].nunique(),
        quantified_after_trip_reductions=0,physical_goods_bypasses_proven=0,
        denominator_is_probability_sample=False,
        interpretation='Counts of typed place illustrations, not effect prevalence or independent respondents.',
        inputs={k:dict(path=str(p.relative_to(ROOT)),sha256=h)for k,(p,h)in INPUTS.items()})
    (HERE/'synthesis_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
