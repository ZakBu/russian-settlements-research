#!/usr/bin/env python3
"""Independent spherical KD-tree readback of the SQL 1-km experiment."""
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
from scipy.spatial import cKDTree

BASE = Path(__file__).resolve().parent
receipt = json.loads((BASE / "receipt.json").read_text())
inputs = receipt["input_files"]
con = duckdb.connect()
for key in ("selected", "points", "edges"):
    p = Path(inputs[key]["path"])
    with p.open("rb") as f:
        assert hashlib.file_digest(f, "sha256").hexdigest() == inputs[key]["sha256"]
    con.read_parquet(str(p)).create_view(key)
status_sql = ",".join("'"+x+"'" for x in receipt["point_status_allowlist"])
rows = con.execute(f"""SELECT s.census_year,s.source_record_id,s.region_norm,s.name_norm,s.type_norm,p.latitude,p.longitude
    FROM selected s JOIN points p ON p.target_source_record_id=s.source_record_id
    WHERE p.coordinate_admission_status IN ({status_sql}) AND coalesce(s.name_norm,'')!='' AND coalesce(s.type_norm,'')!=''""").fetchall()
parent = {sid:sid for sid, in con.execute("SELECT source_record_id FROM selected").fetchall()}
def find(x):
    while parent[x]!=x:
        parent[x]=parent[parent[x]]
        x=parent[x]
    return x
edge_sql=",".join("'"+x+"'" for x in receipt["edge_status_allowlist"])
for a,b in con.execute(f"SELECT from_source_record_id,to_source_record_id FROM edges WHERE relation='same_place' AND decision_status IN ({edge_sql})").fetchall():
    a,b=find(a),find(b)
    if a!=b:parent[b]=a
by_year={y:[r for r in rows if r[0]==y] for y in (2002,2010,2021)}
xyz={}
for y,rs in by_year.items():
    lat=np.radians([r[5] for r in rs]);lon=np.radians([r[6] for r in rs])
    xyz[y]=np.column_stack((np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)))
trees={y:cKDTree(v) for y,v in xyz.items()}
radius=2*np.sin(1000/(2*6371008.8))
results=[]
for ya,yb in ((2002,2010),(2002,2021),(2010,2021)):
    candidate_count=connected=0
    neighbours=trees[ya].query_ball_tree(trees[yb],radius)
    for i,js in enumerate(neighbours):
        a=by_year[ya][i]
        for j in js:
            b=by_year[yb][j]
            if a[2:5]!=b[2:5]:continue
            candidate_count+=1
            connected+=find(a[1])==find(b[1])
    expected=next(r for r in receipt["exact_name_proximity_experiment"] if r["from_year"]==ya and r["to_year"]==yb and r["radius_m"]==1000)
    assert candidate_count==expected["candidate_pairs"],(ya,yb,candidate_count,expected)
    assert connected==expected["already_connected_pairs"],(ya,yb,connected,expected)
    results.append({"from_year":ya,"to_year":yb,"radius_m":1000,"candidate_pairs":candidate_count,"already_connected_pairs":connected})
output={"status":"independent_KDTree_vs_SQL_all_three_year_pairs_agree","receipt_sha256":hashlib.sha256((BASE/"receipt.json").read_bytes()).hexdigest(),"script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"results":results}
(BASE/"independent_candidate_readback.json").write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(output,ensure_ascii=False))
