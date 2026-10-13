"""Apply sourceable points and only proximity candidates with resolved source context."""
import json
from pathlib import Path

import pandas as pd

from current_chain_state_20261007 import sha,distance_km
from working_state_20261007 import load,E

POINT_REVIEW=E/"full_chain_missing_points_20261007/remaining_sourceable_pointuses"
EDGE_REVIEW=E/"residual_same_name_5km_batch_20261007"
OUT=E/"remaining_points_and_reviewed_proximity_application_20261007"


def main():
    state=load(stage=8)
    before=state.metrics()
    edgepath=EDGE_REVIEW/"root_eligible_candidate_identity_edges.csv"
    edges=pd.read_csv(edgepath,keep_default_na=False)
    for row in edges.to_dict("records"):
        a,b=row["from_source_record_id"],row["to_source_record_id"]
        ap,bp=state.point_rows[a],state.point_rows[b]
        if distance_km((ap["latitude"],ap["longitude"]),(bp["latitude"],bp["longitude"]))>5:
            raise ValueError("Reviewed near-name points no longer agree")
        if state.uf.find(a)==state.uf.find(b):raise ValueError("Reviewed edge is not new")
        state.union(a,b)
    edges["decision_status"]="checked_rule_accepted"
    points_path=POINT_REVIEW/"remaining_point_use_delta.csv"
    points=pd.read_csv(points_path,keep_default_na=False)
    context=pd.read_csv(POINT_REVIEW/"source_context.csv",dtype=str,keep_default_na=False)
    for row in context.to_dict("records"):
        ids=row["source_record_ids_2002_2010_2021"].split(" | ")
        if len(ids)!=3 or len({state.uf.find(sid) for sid in ids})!=1 or state.years[state.uf.find(ids[0])]!={2002,2010,2021}:
            raise ValueError("New point does not cover an existing accepted full chain")
        if any(sid in state.point_rows for sid in ids):raise ValueError("Point is not a new use")
        current=state.by_id.loc[ids[2]]
        if str(current.oktmo)!=row["provider_oktmo"] or row["fias_level_dadata"]!="6" or row["qc_geo_dadata"]!="3":
            raise ValueError("Named locality provider tuple gate differs")
    if len(points)!=3*len(context) or points.target_source_record_id.duplicated().any():raise ValueError("Duplicate or incomplete point targets")
    receipt=json.loads((POINT_REVIEW/"receipt.json").read_text())
    origin_hashes={}
    for row in points.to_dict("records"):
        source=Path(row["source"])
        origin_hashes.setdefault(str(source),sha(source))
        if origin_hashes[str(source)]!=row["source_sha256"]:raise ValueError("Provider source changed")
    OUT.mkdir(parents=True,exist_ok=True)
    edges.to_csv(OUT/"accepted_identity_edge_delta.csv",index=False)
    points.to_csv(OUT/"accepted_point_use_delta.csv",index=False)
    state.add_deltas(point_paths=[OUT/"accepted_point_use_delta.csv"])
    after=state.metrics()
    result={"status":"applied_sourceable_points_and_context_reviewed_proximity","new_edges":len(edges),"new_point_uses":len(points),"new_point_components":len(context),"original_proximity_candidates":11,"proximity_candidates_held_for_wrong_county":7,"baseline":before,"after":after,"population_gain":{y:after[y]["covered_population"]-before[y]["covered_population"] for y in before},"source_population_values_modified":False,"boundary_comparability_asserted":False,"inputs":{str(p):sha(p) for p in state.inputs+[edgepath,EDGE_REVIEW/"root_review_receipt.json",EDGE_REVIEW/"root_admission_recommendations.csv",points_path,POINT_REVIEW/"source_context.csv",POINT_REVIEW/"receipt.json"]},"point_origin_hashes":origin_hashes,"outputs":{p.name:sha(p) for p in OUT.glob("*.csv")}}
    (OUT/"application_receipt.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("new_edges","new_point_uses","population_gain","after")},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
