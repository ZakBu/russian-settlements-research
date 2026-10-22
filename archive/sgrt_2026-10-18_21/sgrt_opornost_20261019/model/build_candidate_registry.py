"""Keep all school provider nodes, including those with no extracted external relation."""
from pathlib import Path
import json
import unicodedata
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def norm(s):
    return unicodedata.normalize('NFC', str(s)).casefold().replace('ё', 'е').strip()


def main():
    nodes = pd.read_csv(ROOT / 'data/school_feature_nodes_linked.csv')
    edges = pd.read_csv(ROOT / 'model/documented_graph/service_edges_calculated.csv')
    own_only = pd.read_csv(ROOT / 'services/document_self_only.csv')
    records = []
    for _, row in nodes.iterrows():
        source = row.source_ids
        dest = row.id
        matched = edges[edges.source_id.eq(source) & edges.destination_uid.eq(dest)] if pd.notna(dest) else edges.iloc[:0]
        self_evidence = own_only[own_only.source_id.eq(source) & own_only.settlement.map(norm).eq(norm(row['name']))]
        status = ('documented_external_relation' if len(matched) else
                  'document_names_host_only_for_this_function' if len(self_evidence) else
                  'no_external_edge_extracted_not_function_absence')
        records.append({**row.to_dict(), 'external_relation_evidence_status': status,
                        'n_extracted_external_edges': len(matched),
                        'n_external_origins_geographically_linked': int(matched.is_external_resolved.sum()),
                        'full_SGRT_certified': False,
                        'school_count_is_capacity': False,
                        'evidence_year': {'SV2025': 2025, 'NV2026': 2026, 'TV2021': 2021}[source]})
    result = pd.DataFrame(records)
    assert len(result) == len(nodes) == 32
    result.to_csv(ROOT / 'model/school_candidate_external_evidence.csv', index=False)
    print(json.dumps(result.external_relation_evidence_status.value_counts().to_dict(), ensure_ascii=False))


if __name__ == '__main__':
    main()
