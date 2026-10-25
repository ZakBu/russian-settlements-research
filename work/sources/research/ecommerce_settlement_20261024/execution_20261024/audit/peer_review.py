"""Independent recalculation of headline outputs from the other two agents."""
from pathlib import Path
from collections import defaultdict
import csv
import json
import math
import pyarrow.parquet as pq

OUT = Path(__file__).resolve().parent
EXEC = OUT.parent
BASE = EXEC.parent
rows = pq.read_table(BASE/'national/ozon_WB_comparison_main_target_experimental.parquet').to_pylist()
checks = []


def verify(name, actual, expected):
    passed = abs(actual - expected) < 1e-6
    checks.append({'name': name, 'status': 'PASS' if passed else 'FAIL',
                   'independent': actual, 'peer': expected})


geo = json.loads((EXEC/'geography/summary.json').read_text())['national']
verify('national_population_sum', sum(r['population_2021'] for r in rows), geo['population2021'])
verify('wb_object_sum', sum(r['WB_focus20261021_count'] or 0 for r in rows), geo['WB_positive_objects_n'])
either = [r for r in rows if r['WB_evidence_status'] == 'positive' or
          r['ozon_pickup_inferred_accepted_5km_count'] > 0]
verify('either_positive_settlements', len(either), geo['either_positive_np_n'])
verify('either_positive_population2021', sum(r['population_2021'] for r in either),
       geo['either_positive_population2021'])

standardized = list(csv.DictReader((EXEC/'demography/trajectory_standardized.csv').open()))
sample = [r for r in rows if r['population_value_quality_2002'] == 'direct_published_census_value'
          and r['population_value_quality_2021'] == 'direct_published_census_value'
          and r['population_2002'] is not None and r['population_2002'] > 0
          and r['population_2021'] > 0]
for exposure in ['wb_positive', 'either_5km_positive']:
    strata = defaultdict(lambda: [0, 0, 0, 0])
    eligible = 0
    for r in sample:
        wb = r['WB_evidence_status'] == 'positive'
        ozon = r['ozon_pickup_inferred_accepted_5km_count'] > 0
        positive = wb if exposure == 'wb_positive' else wb or ozon
        unknown = r['WB_evidence_status'].startswith('unknown')
        if unknown and (exposure == 'wb_positive' or not positive):
            continue
        eligible += 1
        kind = 'urban' if r['type_2021'] in ['город', 'пгт'] else 'rural'
        key = (r['region_2021'], r['size2021'], kind)
        decline = r['population_2021'] < r['population_2002']
        offset = 0 if positive else 2
        strata[key][offset] += 1
        strata[key][offset+1] += decline
    support = [v for v in strata.values() if v[0] >= 5 and v[2] >= 5]
    n = sum(v[0]+v[2] for v in support)
    p = sum((v[0]+v[2])*v[1]/v[0] for v in support)*100/n
    q = sum((v[0]+v[2])*v[3]/v[2] for v in support)*100/n
    result = next(r for r in standardized if r['period']=='2002_2021' and
                  r['exposure']==exposure and r['strata']=='region_size2021_type')
    for field, actual in [('eligible_n',eligible), ('supported_n',n),
                          ('standardized_decline_positive_pct',p),
                          ('standardized_decline_no_positive_pct',q),
                          ('difference_percentage_points',p-q)]:
        verify(exposure+'_'+field, actual, float(result[field]))

baseline = list(csv.DictReader((EXEC/'demography/trajectory_baseline2002_standardized.csv').open()))
limits = [100,500,1000,3000,10000,50000,100000,500000,float('inf')]
for result in baseline:
    exposure = result['exposure']
    strata = defaultdict(lambda: [0,0,0,0])
    eligible = 0
    for r in rows:
        if not (r['population_value_quality_2002'] == 'direct_published_census_value' and
                r['population_value_quality_2021'] == 'direct_published_census_value' and
                r['population_2002'] is not None and r['population_2002'] > 0):
            continue
        if result['endpoint_filter'] == 'positive_population2021' and r['population_2021'] <= 0:
            continue
        wb = r['WB_evidence_status'] == 'positive'
        unknown = r['WB_evidence_status'].startswith('unknown')
        if exposure == 'wb_positive':
            positive = wb
            if unknown:
                continue
        else:
            radius = exposure.split('_')[1]
            ozon = r[f'ozon_pickup_inferred_accepted_{radius}_count'] > 0
            positive = ozon if exposure.startswith('ozon') else wb or ozon
            if exposure.startswith('either') and unknown and not positive:
                continue
        eligible += 1
        size = next(i for i, maximum in enumerate(limits) if r['population_2002'] <= maximum)
        key = (r['region_2021'], size)
        if result['strata'].endswith('current_type'):
            key += ('urban' if r['type_2021'] in ['город','пгт'] else 'rural',)
        offset = 0 if positive else 2
        strata[key][offset] += 1
        strata[key][offset+1] += r['population_2021'] < r['population_2002']
    minimum = int(result['min_n_per_group'])
    support = [v for v in strata.values() if v[0] >= minimum and v[2] >= minimum]
    n = sum(v[0]+v[2] for v in support)
    p = sum((v[0]+v[2])*v[1]/v[0] for v in support)*100/n
    q = sum((v[0]+v[2])*v[3]/v[2] for v in support)*100/n
    overlap_sum = sum(v[0]*v[2]/(v[0]+v[2]) for v in support)
    op = sum(v[0]*v[2]/(v[0]+v[2])*v[1]/v[0] for v in support)*100/overlap_sum
    oq = sum(v[0]*v[2]/(v[0]+v[2])*v[3]/v[2] for v in support)*100/overlap_sum
    label = '_'.join([exposure, result['strata'], result['endpoint_filter'], str(minimum)])
    for field,actual in [('eligible_n',eligible),('supported_n',n),
                         ('difference_percentage_points',p-q),
                         ('overlap_weighted_difference_pp',op-oq)]:
        verify('baseline2002_'+label+'_'+field, actual,float(result[field]))

transitions = []
for low,high in [(1,5),(5,10),(1,10)]:
    before = {r['source_record_id_2021'] for r in rows if
              r[f'ozon_pickup_inferred_accepted_{low}km_count'] > 0}
    after = {r['source_record_id_2021'] for r in rows if
             r[f'ozon_pickup_inferred_accepted_{high}km_count'] > 0}
    transitions.append({'radii_km':[low,high],'gained_positive_settlements':len(after-before),
                        'lost_positive_settlements':len(before-after)})
review = {
    'checks': checks,
    'scope': 'Independent recomputation of geography totals, region×size2021×type standardization and all baseline2002 standardization estimates (two weighting rules, three support minima).',
    'ozon_nonmonotone_presence_transitions': transitions,
    'interpretation_cautions': [
        '2021 population weights describe settlement population distribution at census2021, not customers or current2026 population.',
        'Conditioning on size2021, an endpoint of change2002–21, is composition standardization; not control of pre-treatment covariates or a causal adjustment.',
        'WB support region×size×type covers24.4% of eligible inhabited settlements; either-platform support69.8%. Both are supported-subset results.',
        '2010 strict-quality sample is a small selected subset, not a representative national pretrend.',
        'Current platform points were measured in2026; even population2023–25 predates their measurement and is not an observed post-opening outcome.',
        'No longitudinal change or actual centre-periphery flow established by these cross-sectional results.',
        'Ozon positive presence is not monotone in linkage radius: a larger radius may introduce a second same-name candidate and reject a previously unique match.',
    ],
}
(OUT/'peer_review.json').write_text(json.dumps(review, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'checks':len(checks), 'failures':sum(c['status']=='FAIL' for c in checks)}))
assert all(c['status']=='PASS' for c in checks)
