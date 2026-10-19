"""Independent full replay of the small E2 graph's distances and summaries."""
from pathlib import Path
import argparse
import hashlib
import json
import math

import numpy as np
import pandas as pd
from scipy.stats import rankdata


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def spherical(a, b):
    def xyz(row):
        la, lo = math.radians(float(row.lat)), math.radians(float(row.lon))
        return np.array([math.cos(la)*math.cos(lo), math.cos(la)*math.sin(lo), math.sin(la)])
    u, v = xyz(a), xyz(b)
    return 6371.0088 * math.atan2(float(np.linalg.norm(np.cross(u, v))), float(u @ v))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--axis",type=Path,required=True)
    ap.add_argument("--linked-edges",type=Path,required=True)
    ap.add_argument("--graph",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    p=pd.read_parquet(a.axis).set_index("id")
    original=pd.read_csv(a.linked_edges)
    e=pd.read_parquet(a.graph/"service_edges_calculated.parquet")
    m=json.loads((a.graph/"manifest.json").read_text())
    assert sha(a.axis)==m["input_sha256"]["axis"]
    assert sha(a.linked_edges)==m["input_sha256"]["linked_edges"]
    assert e.edge_id.tolist()==original.edge_id.tolist()
    checks=[]
    maxdiff=0.0
    for row in e.itertuples():
        both=row.origin_uid in p.index and row.destination_uid in p.index
        assert (row.geography_status=="both_exactly_linked")==both
        if not both:
            assert pd.isna(row.distance_km)
            continue
        expected=spherical(p.loc[row.origin_uid],p.loc[row.destination_uid])
        maxdiff=max(maxdiff,abs(row.distance_km-expected))
        if getattr(row, "geometry_status", "") == "coordinate_conflict_quarantined":
            assert pd.isna(row.distance_km)
            assert np.isclose(row.distance_km_from_input_unverified,expected,atol=1e-8,rtol=1e-11)
        else:
            assert np.isclose(row.distance_km,expected,atol=1e-8,rtol=1e-11)
        for side,uid in [("origin",row.origin_uid),("destination",row.destination_uid)]:
            for year in [2002,2010,2021]:
                assert getattr(row,f"population_{year}_{side}")==p.loc[uid,f"population_{year}"]
    checks.append({"check":"all_resolved_edges_distances_and_6_population_values","pass":True})
    centers=pd.read_csv(a.graph/"documented_functional_centers.csv")
    gradients=pd.read_csv(a.graph/"documented_catchment_gradients.csv")
    coverage=pd.read_csv(a.graph/"source_coverage.csv")
    used=e[e.is_external_resolved].copy()
    for (source,dest),g in used.groupby(["source_id","destination_uid"]):
        unique=g.drop_duplicates("origin_uid")
        got=centers[(centers.source_id==source)&(centers.destination_uid==dest)].iloc[0]
        assert got.n_documented_external_origins_linked==len(unique)
        for year in [2002,2010,2021]:
            assert got[f"external_census_population_{year}"]==sum(p.loc[x,f"population_{year}"] for x in unique.origin_uid)
            assert got[f"own_census_population_{year}"]==p.loc[dest,f"population_{year}"]
        geo=unique[unique.distance_km.notna()]
        d=geo.distance_km.to_numpy(float)
        y=np.array([math.log1p(p.loc[x,"population_2021"])-math.log1p(p.loc[x,"population_2010"]) for x in geo.origin_uid])
        gr=gradients[(gradients.source_id==source)&(gradients.destination_uid==dest)].iloc[0]
        if "n_geometry_eligible_origins" in gr:
            assert gr.n_geometry_eligible_origins==len(geo)
        if len(geo)>=5 and np.ptp(d)>0:
            slope=float(np.dot(d-d.mean(),y-y.mean())/np.dot(d-d.mean(),d-d.mean()))
            assert np.isclose(gr.slope_log1p_population_change_per_km,slope,atol=1e-12,rtol=1e-9)
            if np.ptp(y)>0:
                rho=float(np.corrcoef(rankdata(d),rankdata(y))[0,1])
                assert np.isclose(gr.spearman_distance_log1p_change,rho,atol=1e-12,rtol=1e-9)
        else:
            assert pd.isna(gr.slope_log1p_population_change_per_km)
    checks.append({"check":"all_document_centers_external_population_and_gradients","pass":True})
    for source,g in used.groupby("source_id"):
        unique=g.drop_duplicates("origin_uid")
        cov=coverage[coverage.source_id==source].iloc[0]
        assert cov.n_resolved_external_edges==len(g)
        assert cov.n_unique_external_origins==len(unique)
        assert cov.external_origin_census_population_2021_unique==unique.population_2021_origin.sum()
        assert cov.n_population2010_zero_origins_retained==unique.population_2010_origin.eq(0).sum()
    checks.append({"check":"all_source_coverage_unique_origins_and_population2010_zeros","pass":True})
    assert e.measured_trips_claim.eq(False).all() and m["full_SGRT_claim"] is False
    checks.append({"check":"no_measured_trip_or_full_sgrt_claim","pass":True})
    result={"status":"PASS_FOR_DOCUMENTED_GRAPH_CALCULATIONS", "n_all_edges":len(e),
            "n_resolved_external_edges":len(used), "n_unresolved_edges":int(e.geography_status.ne("both_exactly_linked").sum()),
            "n_document_centers":len(centers), "max_distance_difference_km":maxdiff,
            "n_coordinate_quarantined":int(e.get("geometry_status",pd.Series(dtype=str)).eq("coordinate_conflict_quarantined").sum()),
            "n_external_origins_population2010_zero":int(used.drop_duplicates("origin_uid").population_2010_origin.eq(0).sum()),
            "checks":checks,"author_code_imported":False,
            "evidence_scope":"E2 document assertions; contemporary/2021 service territory with retrospective census cohort; not actual trips or national zones",
            "graph_manifest_sha256":sha(a.graph/"manifest.json")}
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":main()
