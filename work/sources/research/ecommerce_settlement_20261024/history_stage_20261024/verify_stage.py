"""Final reconciliation and input-protection checks for this empirical stage."""
from pathlib import Path
import csv
import hashlib
import json
import nbformat
import pyarrow.parquet as pq

OUT=Path(__file__).resolve().parent
BASE=OUT.parent


def main():
    previous=json.loads((BASE/'execution_20261024/input_manifest.json').read_text())
    for r in previous['inputs']:
        assert hashlib.sha256((BASE/r['path']).read_bytes()).hexdigest()==r['sha256']
    links=pq.read_table(OUT/'wb_history_symmetric_links.parquet').to_pylist()
    context=pq.read_table(OUT/'centres/settlement_admin_context_main2021.parquet').to_pylist()
    by_id={r['source_record_id_2021']:r for r in context}
    new_checks=[]
    for row in csv.DictReader((OUT/'wb_catalogue_footprint_changes.csv').open()):
        col='source_record_id_2021_'+row['radius_km']+'km'
        old={r[col] for r in links if r['archive_date']==row['older_date'] and r[col]}
        focus={r[col] for r in links if r['archive_date']=='2026-10-21'
               and r['typePoint'] in (8,34) and r[col]}
        added=focus-old
        centre=sum(by_id[k]['admin_centre_positive_20211103'] for k in added)
        other=sum(by_id[k]['context_status_20211103']=='accepted_administrative_parent_and_centre'
                  and not by_id[k]['admin_centre_positive_20211103'] for k in added)
        assert len(focus)==int(row['current_focus_nodes'])
        assert len(added)==int(row['current_focus_nodes_without_old_any_catalogue_record'])
        assert centre==int(row['focus_latter_documented_centres2021'])
        assert other==int(row['focus_latter_other_known_members2021'])
        new_checks.append({'date':row['older_date'],'radius_km':int(row['radius_km']),
                           'new_focus_records_without_old_any':len(added),
                           'documented_centres2021':centre,'other_known_members2021':other})
    conflicts=list(csv.DictReader((OUT/'retail/symmetric_link_explicit_city_type_conflicts.csv').open()))
    assert len(conflicts)==6 and {r['name_2021'] for r in conflicts}=={'Тельмана'}
    latest=OUT/'centres/raw/data-20261001T1110-structure-20260210T1102.csv'
    official=list(csv.reader(latest.open(encoding='utf-8-sig'),delimiter=';'))
    telmana=[r for r in official if len(r)>6 and ''.join(r[:4])=='41648109001']
    assert len(telmana)==1 and telmana[0][6]=='г Тельмана'
    n=nbformat.read(OUT/'history_research.ipynb',as_version=4)
    nbformat.validate(n)
    code=[c for c in n.cells if c.cell_type=='code']
    assert [c.execution_count for c in code]==list(range(1,len(code)+1))
    assert not any(o.output_type=='error' for c in code for o in c.outputs)
    assert sum('image/png' in o.get('data',{}) for c in code for o in c.outputs)==2
    result={
        'previous_input_hashes_unchanged':True,
        'new_focus_contrasts_verified':new_checks,
        'focus_checks_n':len(new_checks)*4,
        'telmana_type_case':{
            'all_six_cases_one_np':True,
            'census2021_type':'посёлок',
            'official_oktmo2026_type':'г Тельмана',
            'official_oktmo2026_code':'41648109001',
            'interpretation':'Actual documented category difference; not six demonstrated false links.',
        },
        'notebook':{'executed_code_cells':len(code),'error_outputs':0,'figures':2},
        'scope':'Computation and documented status checks, not field validation or causal identification',
    }
    (OUT/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('PASS: unchanged previous inputs;84 focus comparisons; Telmana official type case; executed notebook')


if __name__=='__main__':
    main()
