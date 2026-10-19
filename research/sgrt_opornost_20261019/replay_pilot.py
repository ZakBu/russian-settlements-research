"""Recompute the frozen E2 graph, comparable models and scenario tables."""
from __future__ import annotations
import argparse,json,subprocess,sys,hashlib
from pathlib import Path
import pandas as pd
from pandas.testing import assert_frame_equal


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    r=a.root.resolve();o=a.out.resolve()
    if o.exists() and any(o.iterdir()):raise RuntimeError('Replay directory must be empty')
    o.mkdir(parents=True,exist_ok=True)
    commands=[
        [sys.executable,str(r/'model/service_graph.py'),'--axis',str(r/'data/point_axis.parquet'),'--edges',str(r/'data/service_edges_linked.csv'),'--out',str(o/'documented_graph'),'--coordinate-quarantine',str(r/'model/coordinate_quarantine.csv')],
        [sys.executable,str(r/'model/compare_inventory.py'),'--root',str(r),'--graph',str(o/'documented_graph'),'--out',str(o/'inventory_comparison')],
        [sys.executable,str(r/'model/functional_fields.py'),'--origins',str(r/'model/scenario_inputs_SV2025/origins.parquet'),'--candidates',str(r/'model/scenario_inputs_SV2025/candidates.parquet'),'--q-columns','q_documented_schools','--out',str(o/'scenario_school_SV2025')]
    ]
    for i,cmd in enumerate(commands):
        cp=subprocess.run(cmd,cwd=r,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (o/f'command_{i+1}.log').write_text(cp.stdout)
        if cp.returncode:raise RuntimeError(f'Replay command {i+1} failed: {cp.stdout[-2000:]}')
    checks=[]
    for folder in ['documented_graph','inventory_comparison','scenario_school_SV2025']:
        for fresh in sorted(p for p in (o/folder).iterdir() if p.suffix in {'.csv','.parquet'}):
            reference=r/'model'/folder/fresh.name
            if not reference.exists():raise RuntimeError(f'Missing reference {reference}')
            if fresh.suffix=='.parquet':
                x=pd.read_parquet(reference);y=pd.read_parquet(fresh)
            else:
                x=pd.read_csv(reference,float_precision='round_trip');y=pd.read_csv(fresh,float_precision='round_trip')
            assert_frame_equal(x,y,check_dtype=True,check_exact=False,rtol=0,atol=1e-12)
            checks.append({'table':f'{folder}/{fresh.name}','rows':len(y),'columns':len(y.columns),'status':'PASS','whole_table_compared':True})
    result={'status':'PASS','commands':commands,'relative_tolerance':0,'absolute_tolerance':1e-12,'checks':checks,'checks_passed':len(checks),'interpretation':'Reproduction of the frozen pilot; neither new source acquisition nor national validation.'}
    (o/'REPLAY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
