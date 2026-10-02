import unittest

from research_rebuild.mass_linkage.source_registry import MANIFEST, ROOT_ROLES, SOURCE_REGISTRY, validate_registry


class MassSourceRegistryTests(unittest.TestCase):
    def test_builtin_registry_has_complete_provenance_fields(self):
        validate_registry()
        self.assertEqual(len({row["source_id"] for row in SOURCE_REGISTRY}), len(SOURCE_REGISTRY))
        for row in SOURCE_REGISTRY:
            with self.subTest(source_id=row["source_id"]):
                self.assertTrue(row["paths"])
                self.assertTrue(row["source_fields"])
                self.assertTrue(row["rights"])
                self.assertTrue(row["manifest_path"])

    def test_paths_are_root_relative_and_local_roots_are_injected(self):
        self.assertEqual(MANIFEST["root_role"], "baseline_root")
        self.assertNotIn("/workspace", str(MANIFEST))
        self.assertIn("raw_root", ROOT_ROLES)
        for row in SOURCE_REGISTRY:
            for path, role in row["path_root_roles"].items():
                self.assertFalse(path.startswith("/"))
                self.assertIn(role, ROOT_ROLES)

    def test_only_census_primary_candidates_can_be_denominator_candidates(self):
        for row in SOURCE_REGISTRY:
            if row["may_be_denominator"]:
                self.assertEqual(row["population_role"], "census_primary_candidate")
                self.assertTrue(row["observed_years"])
                self.assertIn("census", row["reference_date"].lower())
        nonprimary = [row for row in SOURCE_REGISTRY if row["population_role"] != "census_primary_candidate"]
        self.assertTrue(nonprimary)
        self.assertTrue(all(not row["may_be_denominator"] for row in nonprimary))

    def test_municipal_economy_and_annual_secondary_claims_are_not_denominators(self):
        by_id = {row["source_id"]: row for row in SOURCE_REGISTRY}
        muni = by_id["rosstat_municipal_economy_annual"]
        self.assertEqual(muni["grain"], "municipality × indicator × year, not settlement")
        self.assertFalse(muni["may_be_denominator"])
        self.assertIn("No population metric", " ".join(muni["limits"]))
        self.assertFalse(by_id["wikidata_population_claims"]["may_be_denominator"])
        self.assertFalse(by_id["wikipedia_statistical_modules"]["may_be_denominator"])

    def test_registry_rejects_nonprimary_denominator_and_interpolation(self):
        source = dict(SOURCE_REGISTRY[0])
        source["source_id"] = "bad-annual-source"
        source["population_role"] = "auxiliary_candidate"
        with self.assertRaisesRegex(ValueError, "non-primary source"):
            validate_registry([source | {"may_be_denominator": True}])

        source["may_be_denominator"] = False
        source["may_interpolate"] = True
        with self.assertRaisesRegex(ValueError, "interpolation"):
            validate_registry([source])

    def test_duplicate_ids_are_rejected(self):
        source = dict(SOURCE_REGISTRY[0])
        with self.assertRaisesRegex(ValueError, "duplicate source_id"):
            validate_registry([source, dict(source)])


if __name__ == "__main__":
    unittest.main()
