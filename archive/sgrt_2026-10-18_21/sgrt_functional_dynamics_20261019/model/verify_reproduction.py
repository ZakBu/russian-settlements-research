#!/usr/bin/env python3
"""Actually recompute all model tables into a new directory, then compare frames."""
from pathlib import Path
import tempfile,json
import pandas as pd
import build_integrated_graph,build_history_accounting,integrate_change_evidence,check_invariants,centre_periphery_demography

R=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='functional_graph_replay_') as tmp:
    out=Path(tmp)
    build_integrated_graph.build(out)
    build_history_accounting.build(out)
    integrate_change_evidence.build(out)
    centre_periphery_demography.build(out)
    check_invariants.O=out;check_invariants.run()
    compared=[]
    for expected in sorted((R/'results').glob('*.parquet')):
        got=out/expected.name
        assert got.exists(),expected.name
        a=pd.read_parquet(expected);b=pd.read_parquet(got)
        pd.testing.assert_frame_equal(a,b,check_exact=True)
        compared.append({'table':expected.name,'rows':len(a),'columns':len(a.columns),'exact_match':True})
    result={'status':'PASS','fresh_directory_recomputation':True,'comparison':'exact dataframe equality all values all columns','tables':compared,'n_tables':len(compared)}
    (R/'results/REPRODUCTION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
