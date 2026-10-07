"""Apply a source-backed point batch to already accepted three-year components."""
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from current_chain_state_20261007 import sha
from working_state_20261007 import load,E

REVIEW=E/"full_chain_missing_points_20261007/top30pointuses"
OUT=E/"top30_full_chain_points_application_20261007"


def main():
    s=load(stage=7)
    before=s.metrics()
    packet=pd.read_csv(REVIEW/"top30_point_use_delta.csv",keep_default_na=False)
    context=pd.read_csv(REVIEW/"source_context.csv",keep_default_na=False)
    point_counts=Counter((int(s.by_id.loc[sid,"census_year"]),p["latitude"],p["longitude"]) for sid,p in s.point_rows.items())
    current=s.obs[s.obs.census_year.eq(2021)&s.obs.is_additive_settlement_record.fillna(False)].copy()
    raw_counts=Counter((float(a),float(b)) for a,b in current[["latitude","longitude"]].itertuples(index=False,name=None) if pd.notna(a) and pd.notna(b))
    accepted,held=[],[]
    hashes={}
    for r in context.to_dict("records"):
        ids=str(r["source_record_ids_2002_2010_2021"]).split(" | ")
        if len(ids)!=3 or len({s.uf.find(sid) for sid in ids})!=1 or s.years[s.uf.find(ids[0])]!={2002,2010,2021}:
            raise ValueError("Point targets are not one accepted full chain")
        lat,lon=float(r["point_latitude"]),float(r["point_longitude"])
        reason=None
        if any(sid in s.point_rows for sid in ids):reason="point_already_present"
        if any(point_counts[(int(s.by_id.loc[sid,"census_year"]),lat,lon)] for sid in ids):reason="point_shared_by_another_accepted_same_year_record"
        if raw_counts[(lat,lon)]>1:reason="new_point_shared_in_selected_current_coordinates"
        if reason:
            held.append({"source_record_ids":json.dumps(ids,ensure_ascii=False),"reason":reason})
            continue
        source=Path(r["source_path"])
        hashes.setdefault(str(source),sha(source))
        if hashes[str(source)]!=r["source_sha256"]:raise ValueError("Point origin changed")
        use=packet[packet.target_source_record_id.isin(ids)]
        if len(use)!=3 or set(use.target_year.astype(int))!={2002,2010,2021}:raise ValueError("Point packet incomplete")
        if not use.latitude.eq(lat).all() or not use.longitude.eq(lon).all():raise ValueError("Point packet/context mismatch")
        accepted.extend(use.to_dict("records"))
    OUT.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(accepted,columns=packet.columns).to_csv(OUT/"accepted_point_use_delta.csv",index=False)
    pd.DataFrame(held,columns=["source_record_ids","reason"]).to_csv(OUT/"held_points.csv",index=False)
    s.add_deltas(point_paths=[OUT/"accepted_point_use_delta.csv"])
    after=s.metrics()
    receipt={"status":"applied_full_chain_named_locality_point_batch","new_point_uses":len(accepted),"components":len(accepted)//3,"held_components":len(held),"baseline":before,"after":after,"population_gain":{y:after[y]["covered_population"]-before[y]["covered_population"] for y in before},"raw_selected_current_coordinate_collisions_checked":True,"same_year_accepted_coordinate_collisions_checked":True,"native_provider_binding_asserted":False,"source_population_values_modified":False,"inputs":{str(p):sha(p) for p in s.inputs+list(REVIEW.glob("*.json"))+list(REVIEW.glob("*.csv"))},"source_origin_hashes":hashes,"outputs":{p.name:sha(p) for p in OUT.glob("*.csv")}}
    (OUT/"application_receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:receipt[k] for k in ("new_point_uses","components","held_components","population_gain")},ensure_ascii=False,indent=2))


if __name__=="__main__":main()
