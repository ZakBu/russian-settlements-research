"""Record final reviewed identities and ensure independent audits bind to them."""
from pathlib import Path
import hashlib
import json
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    finish=json.loads((ROOT/"model/FINISHED.json").read_text())
    for item in finish["files"]:
        path=ROOT/"model"/item["file"]
        assert path.stat().st_size==item["bytes"],str(path)
        assert sha(path)==item["sha256"],str(path)
    graph_audit=json.loads((HERE/"documented_graph_audit.json").read_text())
    alternative_audit=json.loads((HERE/"provider_alternatives_audit.json").read_text())
    assert graph_audit["graph_manifest_sha256"]==sha(ROOT/"model/documented_graph/manifest.json")
    assert alternative_audit["comparison_manifest_sha256"]==sha(ROOT/"model/inventory_comparison/manifest.json")
    inv=pd.read_csv(ROOT/"services/school_inventory.csv")
    assert len(inv)==52 and inv.inventory_id.is_unique
    assert inv.groupby("source_id").size().to_dict()=={"NV2026":15,"SV2025":9,"TV2021":28}
    registry=pd.read_csv(ROOT/"model/school_candidate_external_evidence.csv")
    assert len(registry)==32
    assert registry.external_relation_evidence_status.value_counts().to_dict()=={
        "no_external_edge_extracted_not_function_absence":15,
        "documented_external_relation":13,
        "document_names_host_only_for_this_function":4}
    assert registry.full_SGRT_certified.eq(False).all()
    predictions=pd.read_csv(ROOT/"model/inventory_comparison/all_origin_model_comparisons.csv")
    held=predictions[predictions.status.ne("conditional_comparison")]
    assert len(predictions)==1319 and len(held)==8
    assert held.status.value_counts().to_dict()=={"unresolved_origin":7,"coordinate_conflict_quarantined":1}
    assert not held.duplicated(["source_id","origin_name"]).any()
    paths=[ROOT/"model/FINISHED.json", ROOT/"model/MODEL_CONTRACT.md",
           ROOT/"model/documented_graph/manifest.json", ROOT/"model/inventory_comparison/manifest.json",
           ROOT/"model/scenario_school_SV2025/manifest.json", ROOT/"data/point_axis.parquet",
           ROOT/"data/service_edges_linked.csv", ROOT/"data/school_inventory_linked.csv",
           ROOT/"services/service_edges.csv", ROOT/"services/source_audit.json",
           ROOT/"services/school_inventory.csv", ROOT/"model/coordinate_quarantine.csv"]
    paths.extend(sorted(HERE.glob("check_*.py")))
    paths.extend([HERE/"documented_graph_audit.json",HERE/"service_extract_audit.json",
                  HERE/"provider_alternatives_audit.json",HERE/"functional_field_audit_SV2025.json"])
    result={"status":"ACCEPTED_IN_REVIEWED_PILOT_SCOPE_WITH_SUBSTANTIVE_LIMITS",
            "full_national_functional_sgrt_acceptance":False,
            "empirically_calibrated_outside_acceptance":False,
            "policy_return_on_investment_acceptance":False,
            "n_final_model_files_checked":len(finish["files"]),
            "school_inventory":dict(institutions=52,settlement_nodes=32,external_document_witness=13,self_only_document=4,not_extracted_external_unknown=15),
            "missing_comparison_ledger_loss_fixed":True,
            "canonical_graph":dict(edges=79,linked_external=72,geometry_eligible=71,document_centers=15,coordinate_quarantine=1),
            "scope":"Numerical/service-source pilot; independent comparison model audit belongs to separate statistician",
            "frozen_files":[{"file":str(p.relative_to(ROOT)),"bytes":p.stat().st_size,"sha256":sha(p)} for p in paths]}
    (HERE/"FINAL_REVIEW.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="frozen_files"},ensure_ascii=False))


if __name__=="__main__":main()
