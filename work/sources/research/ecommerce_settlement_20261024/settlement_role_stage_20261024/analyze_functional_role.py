"""Functional concentration: centre share in observed physical-shop registers.

No causal effect or actual closures are inferred from differences in entries.
"""
from pathlib import Path
import json
import hashlib
import pandas as pd

OUT=Path(__file__).resolve().parent


def main():
    source=OUT/'shops/choya_centre_surroundings_reviewed_sensitivity.csv'
    x=pd.read_csv(source)
    source_audit=json.loads((OUT/'shops/extraction_summary.json').read_text())
    bad=set(source_audit['count_discrepancy_years'])
    rows=[]
    for year,g in x.groupby('year'):
        assert len(g)==2 and set(g.role)=={'centre','surroundings'}
        c=g.loc[g.role.eq('centre')].iloc[0]
        o=g.loc[g.role.eq('surroundings')].iloc[0]
        for kind in ['all_observed','nonfood','food','mixed']:
            total=int(c[kind]+o[kind])
            assert total>0
            rows.append(dict(
                year=int(year), category=kind,
                centre_listed_entries=int(c[kind]),surrounding_listed_entries=int(o[kind]),
                total_listed_entries=total,centre_share_pct=100*c[kind]/total,
                reported_totals_conflict=bool(year in bad),
                duplicate_dated_content_warning=bool(year in [2022,2023]),
                address_spelling_sensitivity=True,
                actual_closures_confirmed=False,
            ))
    result=pd.DataFrame(rows)
    result.to_csv(OUT/'choya_functional_concentration.csv',index=False)
    contrasts=[]
    for category in ['all_observed','nonfood']:
        g=result.loc[result.category.eq(category)].set_index('year')
        for start,end in [(2019,2024),(2021,2024),(2019,2026),(2024,2026)]:
            a,b=g.loc[start],g.loc[end]
            contrasts.append(dict(
                category=category,start_year=start,end_year=end,
                centre_stock_change_n=int(b.centre_listed_entries-a.centre_listed_entries),
                surroundings_stock_change_n=int(b.surrounding_listed_entries-a.surrounding_listed_entries),
                centre_share_change_pp=float(b.centre_share_pct-a.centre_share_pct),
                either_endpoint_total_conflict=bool(a.reported_totals_conflict or b.reported_totals_conflict),
                interpretation='listed_register_stock_and_share; not_verified_closures_or_platform_effect',
            ))
    pd.DataFrame(contrasts).to_csv(OUT/'choya_functional_contrasts.csv',index=False)
    summary={
        'source':str(source.relative_to(OUT)),
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'category_count_unit':'numbered ordinary shop entries after source-section exclusions',
        'roles':'Choya village versus other observed district settlements; reviewed11 spelling aliases',
        'ordinary_shop_stock_is_not_legal_entities':True,
        'district_not_national_sample':True,
        'contrasts':contrasts,
        'limits':[
            'A decline of centre entries need not mean declining centre share.',
            'Missing settlements are unknown, not zero shops; analysis describes listed entries.',
            '2022 and2023 contents are identical without the date title.',
            '2025 and2026 source totals conflict with rows; their changes require confirmation.',
            'No explicit marketplace markers does not establish no combined shop/pickup functions.',
            'No actual opening/closure dates or causal platform effect inferred.',
        ],
    }
    (OUT/'functional_role_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(contrasts,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
