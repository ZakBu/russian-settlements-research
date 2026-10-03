import json
import unittest

from research_rebuild.mass_linkage.annual_module_bindings import (
    _annual_group_status,
    _exact_title_entry,
    evaluate_entry,
)


def claim(code):
    return json.dumps([{"value_exact_digits": code, "value_raw": code}])


def wide(qid="Q1", code="123", name="Берёзовка", kind="деревня", region="Тверская область"):
    return {
        "wikidata_qid": qid,
        "wikidata_tsv_exact_p764_value_raw": code,
        "wikidata_truthy_exact_p764_claims_json": claim(code),
        "wikidata_truthy_exact_p764_match": True,
        "source_oktmo_exact_digits": code,
        "source_name": name,
        "source_type": kind,
        "source_region": region,
        "source_population_scope": "settlement",
        "wikidata_tsv_ru_labels_json": json.dumps([name], ensure_ascii=False),
        "wikidata_tsv_article_urls_json": json.dumps(["https://ru.wikipedia.org/wiki/" + name.replace(" ", "_")], ensure_ascii=False),
        "wikidata_tsv_matching_rows": 1,
        "wikidata_tsv_line_numbers_json": "[10]",
        "wikidata_name_exact_label": True,
        "wikidata_tsv_article_urls_json": "[]",
    }


def entry(title="Берёзовка", module="RUS-TVE", key="987"):
    return {
        "module_code": module,
        "module_key_raw": key,
        "entry_title_comment_raw": title,
        "title_comment_count": 1,
        "raw_row_count": 3,
        "observed_years": [1897, 1959, 2010],
        "module_sha256_values": ["a" * 64],
    }


def article(title="Берёзовка", region="Тверская область", is_np=True):
    return {
        "canonical_title": title,
        "pageid": 10,
        "revision_id": 20,
        "revision_timestamp": "2025-01-01T00:00:00Z",
        "revision_sha1": "abc",
        "retrieved_at_utc": "2026-08-31T00:00:00Z",
        "api_cache_path": "raw.json.gz",
        "api_cache_line": 1,
        "is_np_russia_template": is_np,
        "article_region_raw": region,
        "article_content_present": True,
    }


def current(code="123", name="Берёзовка", kind="деревня", region="Тверская область"):
    return [{
        "oktmo": code,
        "settlement_name": name,
        "settlement_type": kind,
        "region_raw": region,
        "source_record_id": "2021:source:1",
        "source_file": "source.xlsx",
        "source_row": 2,
    }]


class AnnualModuleBindingsTest(unittest.TestCase):
    def test_exact_actual_comment_title_case_is_required(self):
        # The raw RUS-AAA comment for this place is exactly "Воронеж".
        self.assertTrue(_exact_title_entry("Воронеж", "Воронеж"))
        self.assertTrue(_exact_title_entry("Берёзовка", "Берёзовка"))
        self.assertFalse(_exact_title_entry("Берёзовка", "берёзовка"))
        self.assertFalse(_exact_title_entry("Берёзовка", "Берёзовка (Тверская область)"))

    def test_aaa_aggregate_or_non_np_article_is_held(self):
        status, reason, candidate = evaluate_entry(
            entry(title="Адыгея", module="RUS-AAA"),
            [article(title="Адыгея", region="Республика Адыгея", is_np=False)],
            [wide(qid="Q1879", code="79700000000", name="Адыгея", kind="республика", region="Республика Адыгея")],
            {"79700000000": current(code="79700000000", name="Адыгея", kind="республика", region="Республика Адыгея")[0:1]},
        )
        self.assertEqual((status, reason, candidate), ("held", "raw_api_article_lacks_np_russia_template_or_is_aggregate", None))

    def test_mixed_region_homonym_candidates_are_held(self):
        rows = [
            wide(qid="Q101", code="123", name="Берёзовка", kind="деревня", region="Тверская область"),
            wide(qid="Q202", code="456", name="Берёзовка", kind="деревня", region="Псковская область"),
        ]
        status, reason, candidate = evaluate_entry(
            entry(), [article()], rows,
            {"123": current(), "456": current(code="456", region="Псковская область")},
        )
        self.assertEqual((status, reason, candidate), ("held", "wikidata_article_title_or_p764_metadata_ambiguous", None))

    def test_unique_article_qid_code_and_current_np_metadata_make_review_candidate(self):
        status, reason, candidate = evaluate_entry(
            entry(), [article()], [wide()], {"123": current()},
        )
        self.assertEqual(status, "candidate")
        self.assertEqual(reason, "")
        self.assertEqual(candidate["wikidata_qid"], "Q1")
        self.assertEqual(candidate["current_source_oktmo_exact_digits"], "123")
        self.assertFalse(candidate["place_identity_admission"])
        self.assertEqual(candidate["identity_chain_scope"], "source_named_history_series")

    def test_duplicate_year_values_are_held_and_exact_citation_duplicates_collapse(self):
        base = {
            "population_value_raw": "5", "source_key_raw": "1897A",
            "source_text_raw": "ref", "source_date_note_raw": "",
            "module_locator": "line:10",
        }
        status, records = _annual_group_status([base, {**base, "module_locator": "line:11"}])
        self.assertEqual(status, "exact_duplicate_collapsed")
        self.assertEqual(records[0]["module_locators_all"], '["line:10", "line:11"]')
        self.assertEqual(records[0]["raw_duplicate_count"], 2)
        status, records = _annual_group_status([base, {**base, "population_value_raw": "6", "module_locator": "line:12"}])
        self.assertEqual(status, "held_conflicting_values")
        self.assertEqual(len(records), 2)


if __name__ == "__main__":
    unittest.main()
