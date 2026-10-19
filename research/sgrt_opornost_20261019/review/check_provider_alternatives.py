"""Independent replay of distance-only provider-removal diagnostics.

These are conditional distances within the inventoried municipality, not true
unavailability, schoolchild counts, social loss or budgetary return.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math

import numpy as np
import pandas as pd


def distance(row1,row2):
    def v(row):
        a,b=math.radians(float(row.lat)),math.radians(float(row.lon))
        return np.array([math.cos(a)*math.cos(b),math.cos(a)*math.sin(b),math.sin(a)])
    u,vv=v(row1),v(row2)
    return 6371.0088*math.atan2(float(np.linalg.norm(np.cross(u,vv))),float(u@vv))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--comparison",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    p=pd.read_parquet(a.root/"data/point_axis.parquet").set_index("id")
    inventory_path=a.root/"data/school_inventory_linked.csv"
    inv=pd.read_csv(inventory_path)
    m=json.loads((a.comparison/"manifest.json").read_text())
    assert hashlib.sha256(inventory_path.read_bytes()).hexdigest()==m["inputs"]["inventory"]
    rows=pd.read_csv(a.comparison/"documented_provider_alternatives.csv")
    diffs=[]
    for row in rows.itertuples():
        observed=inv[(inv.source_id==row.source_id)&inv.service_level.ne("evening_general")]
        provider_ids=sorted(set(observed.id.dropna()).intersection(p.index))
        assert row.documented_center_uid in provider_ids
        ori=p.loc[row.origin_uid]
        original=distance(ori,p.loc[row.documented_center_uid])
        available=[(distance(ori,p.loc[x]),x) for x in provider_ids if x!=row.documented_center_uid]
        available.sort()
        expected=available[0][0] if available else math.nan
        assert np.isclose(row.distance_to_documented_center_km,original,atol=1e-8)
        if available:
            assert row.nearest_observed_alternative_uid in provider_ids
            assert row.nearest_observed_alternative_uid!=row.documented_center_uid
            actual=distance(ori,p.loc[row.nearest_observed_alternative_uid])
            assert np.isclose(actual,expected,atol=1e-8)
            assert np.isclose(row.nearest_observed_alternative_distance_km,expected,atol=1e-8)
            assert np.isclose(row.alternative_minus_documented_distance_km,expected-original,atol=1e-8)
            diffs.append(float(expected-original))
        else:
            assert pd.isna(row.nearest_observed_alternative_distance_km)
        assert row.population_2021_origin_all_ages==ori.population_2021
        assert row.capacity_of_alternative_established is False or row.capacity_of_alternative_established==False
        assert row.interpretation=="distance_diagnostic_not_measured_social_loss"
    result={"status":"PASS_DISTANCE_DIAGNOSTICS_ONLY","n_rows_fully_recomputed":len(rows),
            "n_alternative_geometrically_closer_than_documented_provider":sum(x<0 for x in diffs),
            "n_alternative_geometrically_farther_than_documented_provider":sum(x>0 for x in diffs),
            "minimum_delta_km":min(diffs) if diffs else None,"maximum_delta_km":max(diffs) if diffs else None,
            "author_code_imported":False,"all_school_alternatives_independently_recomputed":True,
            "critical_interpretation_limits":[
                "Municipality-limited inventory: closer suppliers across boundaries may be absent.",
                "TV2021 inventory has unresolved supplier locations; NV2026/TV2021 links not grade-specific.",
                "Distance change is not travel-time change or realised closure effect.",
                "Population weights are all-age2021residents, not pupil counts.",
                "Negative distance delta means another observed school node is closer; it must not be truncated into a positive social-loss claim."
            ],"comparison_manifest_sha256":hashlib.sha256((a.comparison/"manifest.json").read_bytes()).hexdigest()}
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":main()
