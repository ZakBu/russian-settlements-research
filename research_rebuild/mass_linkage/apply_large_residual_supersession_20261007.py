"""Apply reviewed identities and a separately recorded coordinate supersession."""
import json
import pandas as pd

from current_chain_state_20261007 import sha, distance_km
from working_state_20261007 import load, E

REVIEW = E / "large_residual_temporal_batch_20261007"
OUT = E / "large_residual_temporal_application_20261007"


def main():
    state = load(stage=2)
    before = state.metrics()
    review_edges = REVIEW / "accepted_identity_edge_delta.csv"
    new_edges = []
    for r in pd.read_csv(review_edges, keep_default_na=False).to_dict("records"):
        a,b = r["from_source_record_id"], r["to_source_record_id"]
        if state.uf.find(a) != state.uf.find(b):
            new_edges.append(r)
    rejection = REVIEW / "point_rejections.csv"
    state.reject_point_uses(rejection)
    replacement = REVIEW / "reviewed_point_supersession_delta.csv"
    for r in pd.read_csv(replacement, keep_default_na=False).to_dict("records"):
        anchor = state.point_rows[r["coordinate_source_record_id"]]
        if distance_km((float(r["latitude"]),float(r["longitude"])),(anchor["latitude"],anchor["longitude"])) > .000001:
            raise ValueError("Supersession point differs from the accepted own locality donor")
    state.add_deltas([review_edges],[replacement])
    after = state.metrics()
    OUT.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(new_edges).to_csv(OUT/"accepted_identity_edge_delta.csv",index=False)
    receipt = {"status":"applied_reviewed_identity_and_coordinate_supersession", "new_edges":len(new_edges), "redundant_reviewed_edges":len(pd.read_csv(review_edges))-len(new_edges), "coordinate_claims_rejected":len(pd.read_csv(rejection)), "point_replacements":len(pd.read_csv(replacement)), "baseline":before, "after":after, "population_gain":{y:after[y]["covered_population"]-before[y]["covered_population"] for y in before}, "historical_native_code_object_binding_rejected":False, "source_population_values_modified":False, "auxiliary_2010_observation_admitted_to_selected":False, "inputs":{str(p):sha(p) for p in state.inputs+list(REVIEW.glob("*.json"))+[OUT/"accepted_identity_edge_delta.csv"]}}
    (OUT/"application_receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:receipt[k] for k in ("new_edges","point_replacements","population_gain","after")},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
