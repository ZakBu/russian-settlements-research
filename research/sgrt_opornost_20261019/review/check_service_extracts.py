"""Independent row-local audit of curated E2 service edges.

Does not import the author's builder or GROUPS. Each edge must belong to its
specific provider row, not merely occur somewhere in the source document.
This checks extraction fidelity, not the legal validity or realised utilisation.
"""
from pathlib import Path
import csv
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
S = HERE.parent / "services"

# Source locators independently inspected in rendered web extractions. NV2026
# source was available as colleague's saved extraction; independent live fetch
# returned an explicit accessibility error and is not claimed successful.
RANGES = {
    ("SV2025", "Нижняя Тура"): [(18, 18)],
    ("SV2025", "Косья"): [(20, 20)],
    ("SV2025", "Сигнальный"): [(21, 21)],
    ("SV2025", "Платина"): [(22, 22)],
    ("TV2021", "Козлово"): [(124, 124)],
    ("TV2021", "Селихово"): [(126, 126)],
    ("TV2021", "Ручьи"): [(129, 129)],
    ("NV2026", "Быньги"): [(778, 783), (854, 859)],
    ("NV2026", "Аятское"): [(784, 793), (860, 868)],
    ("NV2026", "Конево"): [(794, 799), (869, 874)],
    ("NV2026", "Калиново"): [(800, 803), (875, 878)],
    ("NV2026", "Ребристый"): [(805, 807), (880, 882)],
    ("NV2026", "Невьянск"): [(808, 810), (883, 885)],
    ("BA_MED", "Малоказаккулово"): [(102, 102)],
    ("BA_MED", "Батталово"): [(103, 103)],
}


def norm(x):
    return re.sub(r"\s+", " ", x.casefold().replace("ё", "е")).strip()


def main():
    audits = json.loads((S / "source_audit.json").read_text())
    source_by_id = {r["source_id"]: r for r in audits}
    texts = {}
    for row in audits:
        path = S / "captures" / row["capture"]
        b = path.read_bytes()
        assert hashlib.sha256(b).hexdigest() == row["capture_sha256"]
        lines = []
        for line in b.decode("utf-8").splitlines():
            m = re.match(r"^L(\d+)(?:@P\d+(?:-\d+)?)?:\s*(.*)$", line)
            if m:
                lines.append((int(m.group(1)), m.group(2)))
        texts[row["source_id"]] = lines
    with (S / "service_edges.csv").open() as f:
        edges = list(csv.DictReader(f))
    details = []
    for e in edges:
        blocks = RANGES[(e["source_id"], e["provider_settlement"])]
        local_checks = []
        for low, high in blocks:
            text = norm(" ".join(t for i, t in texts[e["source_id"]] if low <= i <= high))
            local_checks.append(norm(e["origin_name"]) in text)
        details.append({"edge_id": e["edge_id"], "source_id": e["source_id"],
                        "origin": e["origin_name"], "provider": e["provider_settlement"],
                        "row_ranges": blocks, "all_relevant_appendices_match": all(local_checks)})
    assert all(r["all_relevant_appendices_match"] for r in details)
    assert len({e["edge_id"] for e in edges}) == len(edges)
    assert all(e["flow_count"] == "" and e["actual_travel_observed"] == "False" for e in edges)
    summary = {
        "status": "PASS_FOR_EXTRACTION_FIDELITY_ONLY",
        "n_edges": len(edges), "n_providers": len(RANGES),
        "n_source_captures_hash_verified": len(audits),
        "n_edges_row_locally_verified": sum(r["all_relevant_appendices_match"] for r in details),
        "independent_live_sources_reopened": ["SV2025", "TV2021", "BA_MED"],
        "live_reopen_unavailable": ["NV2026"],
        "live_source_refs": ["turn87view0", "turn87view1", "turn88view1"],
        "live_failure_ref": "turn88view0",
        "substantive_limits": [
            "Sources establish E2 service/administrative links, not observed trips.",
            "TV2021 contains more providers than the selected three edge groups; the selected providers are not a complete alternatives set.",
            "NV2026 independently checked against saved source capture; live source reopening failed.",
            "Dates differ across documents and unknown publication date persists for BA_MED.",
            "Checks do not establish national completeness or functional SGRT boundaries."
        ], "details": details,
    }
    out = HERE / "service_extract_audit.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "details"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
