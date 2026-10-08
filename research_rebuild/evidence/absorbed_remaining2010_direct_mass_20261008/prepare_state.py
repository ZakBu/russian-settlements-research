"""Freeze actual51 residuals and accepted receiving NP cores for a direct sidecar."""
import collections
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[3];E=ROOT/'research_rebuild/evidence';OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import sha,normalize
def main():
    state=load(51);pins={str(p):sha(p) for p in state.inputs}
    bad=~state.obs.source_record_id.isin(state.point_rows)|~np.isfinite(state.obs.population)
    badroots=set(state.obs.loc[bad,'root'])|{state.uf.find(i) for i in state.conflicting_point_targets}
    roots={r for r in state.obs.root.unique() if state.years[r]=={2002,2010,2021} and r not in badroots}
    finiteids=set(state.obs.loc[state.obs.root.isin(roots),'source_record_id'])
    original=set(finiteids);direct=set();formation=set();fifty=E/'native2010_remaining_county_rule_mass_20261008'
    for name,target in [('complete_publisher_partition_members.csv',original),('qualified_scope_source_id_credit_union.csv',original),
        ('named_merger_lineage_constituents.csv',original),('complete_territorial_scope_constituents.csv',original),
        ('direct_inclusion_transformation_path_native_credit_union.csv',direct),('formation_path_native_credit_union.csv',formation)]:
        source=fifty/('baseline49_union_'+name+'.gz');pins[str(source)]=sha(source)
        frame=pd.read_csv(source,keep_default_na=False);target.update(frame.source_record_id.astype(str))
    credit=original|direct|formation
    rows=state.obs[state.obs.census_year.eq(2010)&state.obs.is_additive_settlement_record.fillna(False)&~state.obs.region_norm.isin(['москва','санкт петербург','севастополь'])&~state.obs.source_record_id.isin(credit)].sort_values('population',ascending=False)
    rows=rows[np.isfinite(rows.population)]
    rows.to_csv(OUT/'actual51_remaining2010_native_rank.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    top=rows.head(399)
    keys={(row.region_norm,normalize(row.settlement_name)) for row in top.itertuples()}
    historical=state.obs[state.obs.census_year.isin([2002,2010])&state.obs.apply(lambda row:(row.region_norm,normalize(row.settlement_name)) in keys,axis=1)].copy()
    historical['already_original_mixed_credited']=historical.source_record_id.isin(original)
    historical['already_direct_or_formation_credited']=historical.source_record_id.isin(direct|formation)
    historical['existing_own_point_json']=historical.source_record_id.map(lambda sid:json.dumps(state.point_rows.get(sid,{}),ensure_ascii=False,default=str))
    historical.to_csv(OUT/'actual51_top400_historical_native_context.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    cores=state.obs[state.obs.root.isin(roots)&state.obs.type_norm.isin(['город','пгт'])].copy()
    cores['existing_own_point_json']=cores.source_record_id.map(lambda sid:json.dumps(state.point_rows[sid],ensure_ascii=False,default=str))
    cores.to_csv(OUT/'actual51_finite_receiving_urban_NP_context.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    import duckdb
    db=duckdb.connect();extra=db.execute("SELECT source_record_id,region_raw,source_name_raw,source_row,source_sheet FROM read_parquet(?) WHERE census_year IN (2002,2010)",[str(state.inputs[0])]).fetchdf();db.close()
    extra=extra[extra.source_record_id.isin(set(historical.source_record_id)|set(cores.source_record_id))]
    extra.to_csv(OUT/'native_raw_metadata.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    receipt=dict(status='actual51_residual_and_receiving_context_frozen',working_stage=51,finite_histories_all_grains=len(roots),
        all_remaining2010_native_rows=len(rows),remaining2010_native_population=int(rows.population.sum()),
        ranked_first399_population=int(top.population.sum()),direct_prior_source_ids=len(direct),formation_source_ids=len(formation),
        input_pins=pins,output_pins={p.name:sha(p) for p in OUT.glob('*.csv.gz')},code_sha256=sha(Path(__file__)))
    (OUT/'baseline51_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['status','all_remaining2010_native_rows','remaining2010_native_population','ranked_first399_population']}))
if __name__=='__main__':main()
