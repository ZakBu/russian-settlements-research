#!/usr/bin/env python3
"""Compare locality-parser results on frozen operator rows without routing."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import pandas as pd

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from scripts.sgrt_zero import commerce


def preview(root,population,output):
    reference_path=root/'context/analysis_reference.parquet'
    reference=pd.read_parquet(reference_path)
    population_frame=pd.read_parquet(population,columns=['source_record_id_2021','settlement_type_2021'])
    parser_path=Path(commerce.__file__);parser_sha=commerce.digest(parser_path)
    output.mkdir(parents=True,exist_ok=True)
    summary={'completed':False,'parser_sha256':parser_sha,'preview_code_sha256':commerce.digest(Path(__file__)),
        'reference_sha256':commerce.digest(reference_path),'population_sha256':commerce.digest(population),'operators':{}}
    roles={'wildberries':'commerce/sites_wb_current.parquet','yandex':'commerce/yandex/sites_yandex_current.parquet',
        'fivepost':'commerce/fivepost/sites_5post_current.parquet'}
    names=reference.loc[reference.source_record_id.notna()].set_index('source_record_id')['name']
    for label,relative in roles.items():
        source=root/relative;before=pd.read_parquet(source);current=before.copy()
        valid=current.site_lat.between(-90,90)&current.site_lon.between(-180,180)
        links=commerce.match_wb_addresses(current.loc[valid],reference,population_frame)
        for col in links:
            if col!='known_foreign_source_country_label_conflict':current.loc[valid,col]=links[col]
        current=commerce.bind_explicit_city_contexts(current,reference)
        current=commerce.add_geographic_context(current,reference)
        protected=['provider_id','site_lat','site_lon','activity_address','source_address_locality',
            'source_region_literal','supply_status','source_year','source_snapshot','source_country_literal']
        if len(current)!=len(before) or any(not before[col].equals(current[col]) for col in protected if col in before):
            raise ValueError('A raw source/eligibility field changed during identity inspection: '+label)
        current['source_record_id_before_component_parser']=before.source_record_id
        current['identity_changed']=before.source_record_id.fillna('').ne(current.source_record_id.fillna(''))
        current['previous_reference_name']=before.source_record_id.map(names)
        current['new_reference_name']=current.source_record_id.map(names)
        current.to_parquet(output/(label+'_all_identity_comparisons.parquet'),index=False)
        changed=current.identity_changed
        summary['operators'][label]={'source_rows':len(current),'source_sha256':commerce.digest(source),
            'identity_changed_rows':int(changed.sum()),'became_unknown':int((changed&current.source_record_id.isna()).sum()),
            'changed_to_known_np':int((changed&current.source_record_id.notna()).sum()),
            'raw_source_and_eligibility_fields_unchanged':True,
            'identity_basis_counts':current.np_identity_basis.value_counts().to_dict()}
        (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'operator':label,**summary['operators'][label]},ensure_ascii=False),flush=True)
    if parser_sha!=commerce.digest(parser_path):raise RuntimeError('Parser changed during preview; outputs are not a frozen comparison')
    summary['completed']=True
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--population',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    preview(a.root,a.population,a.output)


if __name__=='__main__':main()
