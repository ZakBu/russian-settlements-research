import csv
import gzip
import tempfile
import unittest
from pathlib import Path

from research_rebuild.mass_linkage.candidate_graph_checks import (
    Node,
    ProposalEdge,
    YearConstrainedUnionFind,
    _candidate_blockers,
    _candidate_scenarios,
    _read_ambiguous_key_groups,
    _run_scenario,
    district_lineage_class,
)
import pandas as pd


def node(sid, year, *, population=10, aggregate=False, conflict=False, collision=False,
         typ="деревня", district="district", lineage="2002_source_row_district_heading_or_parent"):
    return Node(
        source_record_id=sid, census_year=year, population=population,
        population_scope="settlement", aggregate=aggregate,
        legacy_identity_conflict=conflict, legacy_same_year_collision=collision,
        type_norm=typ, region_norm="region", district_norm=district,
        district_raw=district, municipality_raw="mun", municipality_norm="mun",
        district_lineage_class=lineage, source_file="file", source_path="path",
        source_sheet="sheet", source_row="1", source_native_id="native",
        source_sha256="sha", source_locator="loc", source_selection_component="",
        entity_grain_status="atomic_settlement_source_row",
        population_value_quality="direct_published_census_value",
    )


def edge(edge_id, left, right, families=("region_district_name_type",)):
    return ProposalEdge(edge_id, left.census_year, right.census_year,
                        left.source_record_id, right.source_record_id,
                        ("CAND-" + edge_id,), families, left, right)


class CandidateGraphCheckTests(unittest.TestCase):
    def test_district_lineage_does_not_treat_tochno_parent_as_historical(self):
        self.assertEqual(
            district_lineage_class(2021, "data/interim/2021_tochno/data_allsettlements.parquet", None, None, "район"),
            "tochno_mun_upper_parent_raw_but_census_date_unestablished",
        )
        self.assertEqual(
            district_lineage_class(2002, "data/raw/2002/source.xls", None, None, "район"),
            "2002_source_row_district_heading_or_parent",
        )
        self.assertEqual(district_lineage_class(2010, "source.xlsx", None,
                         "national_2010_regional_primary_r2", "район"),
                         "reviewed_2010_primary_publication_parent_context")

    def test_union_find_rejects_duplicate_census_year_and_builds_single_full_chain(self):
        n02, n10a, n10b, n21 = (node("02-a", 2002), node("10-a", 2010),
                                node("10-b", 2010), node("21-a", 2021))
        edges = [edge("01", n02, n10a), edge("02", n02, n10b), edge("03", n10a, n21)]
        selected = pd.DataFrame([{"source_record_id": n.source_record_id, "census_year": n.census_year,
                                  "population": n.population} for n in (n02, n10a, n10b, n21)])
        run, conflicts = _run_scenario("test", edges, {n.source_record_id: n for n in (n02, n10a, n10b, n21)}, [], selected)
        self.assertEqual(run["summary"]["proposed_full_chain_components"], 1)
        self.assertEqual(run["summary"]["same_year_collision_components"], 0)
        self.assertEqual(run["summary"]["candidate_edges_blocked_by_same_year_overlap"], 1)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["compatibility_status"], "blocked_same_year_component_collision")
        graph = YearConstrainedUnionFind({n.source_record_id: n for n in (n02, n10a, n10b, n21)})
        self.assertEqual(graph.add_edge("02-a", "10-a")[0], "proposed_component_merge")
        self.assertEqual(graph.add_edge("02-a", "10-b")[:2],
                         ("blocked_same_year_component_collision", (2010,)))

    def test_aggregate_and_legacy_hard_conflicts_block_and_cross_family_pair_is_deduped(self):
        n02 = node("02-a", 2002, typ="город")
        n10 = node("10-a", 2010, typ="город", aggregate=True)
        self.assertIn("federal_or_admin_aggregate_scope", _candidate_blockers(edge("a", n02, n10)))
        n10 = node("10-a", 2010, typ="город", conflict=True)
        self.assertIn("legacy_identity_conflict", _candidate_blockers(edge("b", n02, n10)))
        pair = ("02-a", "10-a")
        values = {"year_from": 2002, "year_to": 2010, "candidate_ids": {"CAND-a", "CAND-b"},
                  "candidate_families": {"region_district_name_type", "region_name_type"},
                  "federal_aggregate_block": False, "legacy_identity_conflict_present": False,
                  "legacy_same_year_collision_present": False}
        scenarios = _candidate_scenarios({pair: values}, {"02-a": n02, "10-a": n10})
        self.assertEqual(len(scenarios["strict_region_district_name_type"]), 1)
        self.assertEqual(len(scenarios["urban_region_name_type"]), 1)
        self.assertEqual(scenarios["urban_region_name_type"][0].candidate_ids, ("CAND-a", "CAND-b"))

    def test_ambiguous_key_group_is_retained_without_cartesian_pair_expansion(self):
        fields = ["candidate_id", "candidate_kind", "candidate_family", "year_pair", "key_fields", "key_values",
                  "key_hash", "from_candidate_count", "to_candidate_count", "from_candidate_ids_json",
                  "to_candidate_ids_json", "potential_cartesian_pair_count_not_materialized", "from_known_population",
                  "to_known_population", "from_unknown_population_rows", "to_unknown_population_rows", "from_regions_json",
                  "to_regions_json", "region_risk_class", "federal_aggregate_block", "legacy_identity_conflict_present",
                  "legacy_same_year_collision_present", "ambiguity_flags_json"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "ledger.csv.gz"
            row = {key: "" for key in fields}
            row.update({"candidate_id": "CAND-ambiguous", "candidate_kind": "ambiguous_competing_key_group",
                        "candidate_family": "region_district_name_type", "year_pair": "2002-2010",
                        "from_candidate_count": "2", "to_candidate_count": "3",
                        "from_candidate_ids_json": '["02-a","02-b"]',
                        "to_candidate_ids_json": '["10-a","10-b","10-c"]',
                        "potential_cartesian_pair_count_not_materialized": "6"})
            with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow(row)
            groups = _read_ambiguous_key_groups(path)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["potential_cartesian_pair_count_not_materialized"], "6")
        self.assertFalse(groups[0]["cartesian_expansion_performed"])
        self.assertEqual(groups[0]["admission_status"], "candidate_only_no_admission")


if __name__ == "__main__":
    unittest.main()
