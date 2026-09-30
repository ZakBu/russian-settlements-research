"""Metadata-only correction to admissions R3 selected-row locator serialization."""
from __future__ import annotations
import argparse, hashlib, json, shutil, tempfile
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "research_rebuild/evidence"
R3 = EVIDENCE / "releases/national_reviewed_admissions_r3_20260930"
SELECTED = EVIDENCE / "releases/national_source_selection_r1_20260930/selected_observations.parquet"
OUT_ID = "national_reviewed_admissions_r4_metadata_20260930"
PINS = {
 R3 / "release_manifest.json": "0a6494cd149e334a60951538222519d595a3fd6d4fcd6f7a50b106f7b8b65ada",
 SELECTED: "dd8d437c1a1f5cebf2b45c55e7a6e2015f3c1a295cade827a71bb76189a485df",
}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def jval(v):
    if pd.isna(v): return None
    return v.item() if hasattr(v,"item") else v
def build(output: Path):
    output=output.resolve()
    if output.exists(): raise FileExistsError(output)
    for p,h in PINS.items():
        if not p.is_file() or sha(p)!=h: raise ValueError(f"pinned input mismatch: {p}")
    old=json.loads((R3/"release_manifest.json").read_text())
    for name,e in old["outputs"].items():
        p=R3/name
        if not p.is_file() or sha(p)!=e["sha256"]: raise ValueError(f"R3 output mismatch: {p}")
    selected=pd.read_parquet(SELECTED).set_index("source_record_id",drop=False)
    out=Path(tempfile.mkdtemp(prefix=f".{OUT_ID}.staging-",dir=output.parent))
    for p in R3.iterdir():
        if p.is_file(): shutil.copyfile(p,out/p.name)
    decisions=pd.read_csv(out/"tom11_bridge_decisions.csv")
    for idx,row in decisions.iterrows():
        ev=json.loads(row.evidence_json)
        sid=str(row.to_source_record_id)
        if sid not in selected.index: raise ValueError(f"selected endpoint absent: {sid}")
        src=selected.loc[sid]
        if int(src.census_year)!=2010: raise ValueError(f"wrong selected endpoint year: {sid}")
        # These locators describe the selected R1 observation. Table 5 is a
        # separate publication binding and remains in its own evidence object.
        raw_locator=jval(src.get("source_locator"))
        if isinstance(raw_locator,str) and raw_locator.strip().casefold() in {"none","nan","<na>",""}:
            raw_locator=None
        endpoint={
          "source_record_id":sid,
          "source_file":jval(src.get("source_file")),
          "source_sha256":jval(src.get("source_sha256")),
          "source_sheet":jval(src.get("source_sheet")),
          "source_row":jval(src.get("source_row")),
          "source_native_id":jval(src.get("source_native_id")),
          "source_locator":raw_locator,
          "source_locator_null_reason":("selected source observation has no populated source_locator; source_sheet/source_row/source_native_id identify the selected row" if raw_locator is None else None),
          "source_name_raw":jval(src.get("source_name_raw")),
          "population":int(src.population),
        }
        ev["selected_2010_endpoint"]=endpoint
        decisions.at[idx,"evidence_json"]=json.dumps(ev,ensure_ascii=False,sort_keys=True)
    decisions.to_csv(out/"tom11_bridge_decisions.csv",index=False)
    manifest={
      "release_id":OUT_ID,"parent_release_id":"national_reviewed_admissions_r3_20260930",
      "parent_manifest_sha256":sha(R3/"release_manifest.json"),
      "purpose":"metadata-only correction: selected 2010 row locator fields are serialized as typed values/null; Table5 proof locator remains separate",
      "scientific_content_invariant":True,
      "verified_inputs":{str(p.relative_to(ROOT)):sha(p) for p in PINS},
      "decisions":old["decisions"],"new_edge_mass_by_year":old["new_edge_mass_by_year"],
      "coverage":old["coverage"],"fixed_sample_review":old["fixed_sample_review"],
      "limitations":old["limitations"],"builder_sha256":sha(Path(__file__).resolve()),"outputs":{}
    }
    for p in sorted(out.iterdir()):
        if p.name!="release_manifest.json": manifest["outputs"][p.name]={"sha256":sha(p),"bytes":p.stat().st_size}
    (out/"release_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    out.rename(output)
    return manifest
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True);a=p.parse_args();print(json.dumps(build(a.output),ensure_ascii=False,indent=2))
