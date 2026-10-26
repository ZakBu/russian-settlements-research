"""Audit public KOUZH schemas, weights and questionnaire comparability.

Only aggregate metadata leave the ignored work directory. No record, household
identifier or inferred settlement identity is printed or published.
"""
from pathlib import Path
import hashlib
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
WORK = ROOT/'work/ecommerce_flows_20261026'


def main():
    results, published, compositions = [], [], []
    fields = ['H00_02', 'H00_04', 'H00_06', 'H00_07', 'hhId', 'H01_02',
              'H01_12', 'I00_09', 'I00_10', 'I00_11', 'R_1', 'R_1_1', 'KVZV']
    fields += [f'I04_0{q}_0{k}' for q in (3, 4) for k in (1, 2, 3)]
    for year in (2018, 2022, 2024):
        path = WORK/f'{year}_individual.csv'
        columns = pd.read_csv(path, sep=';', nrows=0).columns
        frame = pd.read_csv(path, sep=';', usecols=[c for c in fields if c in columns], low_memory=False)
        age15 = frame.H01_02.ge(15)
        food = frame.I04_03_01
        weight = frame.KVZV
        assert weight.notna().all() and weight.gt(0).all()
        assert frame.R_1.equals(frame.H00_04)
        assert frame.R_1_1.equals(frame.H00_07)
        assert set(frame.R_1) <= {1, 2} and set(frame.R_1_1) <= set(range(1, 11))
        assert frame[['H00_02', 'R_1', 'R_1_1']].notna().all().all()
        assert not (food.notna() & ~age15).any()
        keys = ['hhId'] if 'hhId' in frame else ['H00_02', 'H00_04', 'H00_06']
        hh_weights = frame.groupby(keys, dropna=False).KVZV.nunique()
        assert hh_weights.eq(1).all()
        question_stats = []
        for question in (3, 4):
            for group in (1, 2, 3):
                col = f'I04_0{question}_0{group}'
                assert set(frame[col].dropna().unique()) <= {-7, 1, 2, 3, 4}
                question_stats.append(dict(variable=col,
                    nonmissing_n=int(frame[col].notna().sum()),
                    age15_missing_n=int((age15 & frame[col].isna()).sum()),
                    dont_know_n=int(frame[col].eq(-7).sum()),
                    valid_1to4_n=int(frame[col].isin([1, 2, 3, 4]).sum())))
        missing = age15 & food.isna()
        rural = frame.loc[frame.R_1.eq(2)]
        rural_info = rural.loc[rural.H01_02.ge(15) & rural.I04_03_01.notna()]
        for size, group in rural.groupby('R_1_1'):
            info = rural_info.loc[rural_info.R_1_1.eq(size)]
            compositions.append(dict(year=year, size=int(size), all_members_n=len(group),
                all_members_weight_sum=float(group.KVZV.sum()),
                all_members_rural_share_pct=float(100*group.KVZV.sum()/rural.KVZV.sum()),
                adult_info_n=len(info), adult_info_weight_sum=float(info.KVZV.sum()),
                adult_info_rural_share_pct=float(100*info.KVZV.sum()/rural_info.KVZV.sum()),
                unweighted_adult_info_rural_share_pct=float(100*len(info)/len(rural_info))))
        results.append(dict(year=year, file=str(path.relative_to(ROOT)),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            rows_n=len(frame), columns_n=len(columns), age15_n=int(age15.sum()),
            food_response_n=int(food.notna().sum()), age15_food_missing_n=int(missing.sum()),
            age15_food_missing_with_no_information_code99_n=int((missing & frame.H01_12.eq(99)).sum()),
            region_codes_n=int(frame.H00_02.nunique()),
            geography_missing_n={c:int(frame[c].isna().sum()) for c in ['H00_02', 'R_1', 'R_1_1']},
            urban_rural_alias_exact=True, size_alias_exact=True,
            household_weight_constant_n=int(hh_weights.eq(1).sum()), household_groups_n=len(hh_weights),
            weight_sum_all_members=float(weight.sum()), weight_sum_age15=float(weight[age15].sum()),
            weight_sum_food_response=float(weight[food.notna()].sum()),
            interview_month_nonmissing_counts={str(k):int(v) for k,v in frame.loc[food.notna(), 'I00_10'].value_counts().items()},
            question_schema=question_stats))
        if year == 2022:
            # Bondarenko2023 table3, based on KOUZH2022. Preserve DK=-7 in
            # denominator and show a valid-response alternative separately.
            targets = {'rural_all': [77.8, 21.7, .5, 0, 0],
                       'rural_le200': [52.4, 45.9, 1.6, 0, .1],
                       'rural_201to1000': [68.4, 31.2, .3, .1, 0],
                       'rural_1001to5000': [83, 16.4, .5, 0, 0],
                       'rural_gt5000': [92.8, 6.8, .4, 0, 0]}
            for label, size in [('rural_all', None), ('rural_le200', 7), ('rural_201to1000', 8),
                                ('rural_1001to5000', 9), ('rural_gt5000', 10)]:
                domain = age15 & frame.R_1.eq(2) & food.notna()
                if size is not None:
                    domain &= frame.R_1_1.eq(size)
                denom = weight[domain].sum()
                valid = domain & food.isin([1, 2, 3, 4])
                for j, answer in enumerate([1, 2, 3, 4, -7]):
                    percentage = 100*weight[domain & food.eq(answer)].sum()/denom
                    published.append(dict(year=year, domain=label, answer=answer,
                        response_n=int(domain.sum()), weighted_response_population=float(denom),
                        weighted_share_pct=float(percentage),
                        published_share_pct=targets[label][j],
                        same_at_1decimal=round(float(percentage), 1) == targets[label][j],
                        valid_1to4_alternative_home_pct=float(100*weight[valid & food.eq(1)].sum()/weight[valid].sum())))
    report = dict(method='schema and aggregate-weight audit; no variance-design or causal validation',
                  years=results,
                  online_question_comparability={
                      '2018':'post OR Internet, year-to-date; September interviews',
                      '2022':'post OR Internet, year-to-date; May/June interviews',
                      '2024':'Internet ONLY in questionnaire; codebook labels still mention post OR Internet'},
                  regional_map='2024 codebook sheet3 lists85 named region labels for H00_02; 2018/2022 no value-label list found there',
                  no_settlement_deanonymization=True)
    (HERE/'schema_weights_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    pd.DataFrame(published).to_csv(HERE/'published_food_table_reproduction.csv', index=False)
    pd.DataFrame(compositions).to_csv(HERE/'rural_size_composition_weights.csv', index=False)
    print(json.dumps(dict(years=[dict(year=r['year'], rows_n=r['rows_n'], age15_n=r['age15_n'],
        food_response_n=r['food_response_n'], age15_food_missing_n=r['age15_food_missing_n']) for r in results],
        published_cells=len(published), published_rounded_matches=sum(r['same_at_1decimal'] for r in published)), ensure_ascii=False))


if __name__ == '__main__':
    main()
