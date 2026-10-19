"""Independently recalculate all school model ranks on identical source cohorts."""
from pathlib import Path
import argparse, hashlib, json
from itertools import product
import numpy as np
import pandas as pd


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();r=a.root.resolve();o=r/'data/statistics';o.mkdir(parents=True,exist_ok=True)
    p=pd.read_parquet(r/'data/point_axis.parquet').set_index('id');inv=pd.read_csv(r/'data/school_inventory_linked.csv')
    output=r/'model/inventory_comparison';manifest=json.loads((output/'manifest.json').read_text());pred=pd.read_csv(output/'all_origin_model_comparisons.csv')
    # The actual graph used by the comparison is identified by its recorded SHA.
    graph=[q for q in (r/'model').glob('documented_graph*/service_edges_calculated.csv') if sha(q)==manifest['inputs']['graph_edges']]
    assert len(graph)>=1
    e=pd.read_csv(graph[0]);checks=[]
    def ck(n,c,d=None):
        checks.append(dict(test=n,passed=bool(c),details=d));assert c,(n,d)
    ck('inventory_SHA_frozen',sha(r/'data/school_inventory_linked.csv')==manifest['inputs']['inventory'])
    ck('axis_SHA_frozen',sha(r/'data/point_axis.parquet')==manifest['inputs']['axis'])
    for f in manifest['outputs']:ck('output_SHA_'+f['file'],sha(output/f['file'])==f['sha256'])
    compared=pred[pred.status.eq('conditional_comparison')].copy()
    ck('same_origin_cohort_all19_models',compared.groupby(['source_id','origin_uid']).model.nunique().eq(19).all())
    errors=[];rebuilt=[]
    for source,rows in compared.groupby('source_id'):
        si=inv[inv.source_id.eq(source)&~inv.service_level.eq('evening_general')&inv.id.notna()]
        candidates=si.groupby('id').size().rename('school_count').sort_index()
        cp=p.loc[candidates.index];la=np.deg2rad(cp.lat.to_numpy());lo=np.deg2rad(cp.lon.to_numpy())
        for origin,rr in rows.groupby('origin_uid'):
            ip=p.loc[origin];ola,olo=np.deg2rad([ip.lat,ip.lon])
            # Independent spherical law of cosines, not author's haversine.
            d=6371.0088*np.arccos(np.clip(np.sin(ola)*np.sin(la)+np.cos(ola)*np.cos(la)*np.cos(lo-olo),-1,1))
            targets=set(e.loc[e.source_id.eq(source)&e.origin_uid.eq(origin),'destination_uid'].dropna())
            tm=np.array([uid in targets for uid in candidates.index]);assert tm.any()
            scores={'nearest':-d}
            for beta,d0 in product([1.5,2,3],[5,10,20]):
                scores[f'school_count_b{beta:g}_d{d0:g}']=candidates.to_numpy()/(1+d/d0)**beta
                scores[f'population2010_b{beta:g}_d{d0:g}']=cp.population_2010.to_numpy()/(1+d/d0)**beta
            ck('same_candidate_set_'+source+'_'+origin,rr.n_candidate_nodes.eq(len(cp)).all())
            for row in rr.itertuples():
                s=scores[row.model];rank=1+int((s>s[tm].max()+1e-12).sum());ties=np.isclose(s,s.max(),rtol=0,atol=1e-12)
                hit=bool((ties&tm).any());top=candidates.index[int(s.argmax())]
                ok=(rank==row.target_rank and hit==row.top1_hits_documented_target and (rank<=2)==row.top2_hits_documented_target and (rank<=3)==row.top3_hits_documented_target and top==row.selected_center_uid)
                if not ok:errors.append(dict(source=source,origin=origin,model=row.model,expected_rank=rank,stored_rank=row.target_rank,expected_top=top,stored_top=row.selected_center_uid))
                rebuilt.append(dict(source_id=source,origin_uid=origin,model=row.model,hit=hit))
    ck('all_conditional_predictions_ranks_reproduced',len(errors)==0,{'rows':len(compared),'mismatches':len(errors)})
    b=pd.DataFrame(rebuilt);summary=[]
    for (source,model),g in b.groupby(['source_id','model']):summary.append(dict(source_id=source,model=model,n=len(g),top1_numerator=int(g.hit.sum()),top1_fraction=float(g.hit.mean())))
    summary=pd.DataFrame(summary);summary.to_csv(o/'document_level_comparison_reproduced.csv',index=False)
    # Report the default beta=2,d0=10 alongside nearest; no best-parameter selection.
    main=summary[summary.model.isin(['nearest','school_count_b2_d10','population2010_b2_d10'])]
    main.to_csv(o/'document_level_main_comparison.csv',index=False)
    result=dict(status='PASS',checks_passed=len(checks),conditional_rows_reproduced=len(compared),
        author='anchor_data; demographic axis and identity linker author; independent of GIS algorithm',
        reference_graph=str(graph[0]),source_units=int(compared.source_id.nunique()),
        rows_not_independent_national_sample=True,pseudoreplicated_national_CI_calculated=False,
        parameter_choice='all frozen grid retained; main displayed beta2 d010; no selection by agreement',
        comparable_scope='one complete grade-specific source SV2025; NV2026/TV2021 exploratory; no across-boundary supplier completeness',
        input_hashes=manifest['inputs'],checks=checks)
    (o/'independent_experiment_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(main.to_string(index=False));print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
