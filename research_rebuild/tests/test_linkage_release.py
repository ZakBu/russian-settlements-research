import unittest

import pandas as pd

from research_rebuild.linkage.build import release_coordinate_decisions


class ReleaseCoordinateSelectionTests(unittest.TestCase):
    def test_secondary_observation_admission_stays_in_ledger_but_not_release(self):
        decisions = pd.DataFrame([
            {"decision_type": "coordinate_admission", "event_action": "apply",
             "observation_id": "old-2010", "coordinate_claim_id": "old-claim"},
            {"decision_type": "coordinate_admission", "event_action": "apply",
             "observation_id": "selected-2010", "coordinate_claim_id": "selected-claim"},
            {"decision_type": "identity_link", "event_action": "apply",
             "observation_id": "old-2010", "coordinate_claim_id": None},
        ])
        release = release_coordinate_decisions(decisions, {"selected-2010"})
        self.assertEqual(release.observation_id.tolist(), ["selected-2010"])
        self.assertEqual(release.coordinate_claim_id.tolist(), ["selected-claim"])
        self.assertIn("old-2010", set(decisions.observation_id))

    def test_unselected_only_history_cannot_create_release_admission(self):
        decisions = pd.DataFrame([{"decision_type": "coordinate_admission", "event_action": "apply",
                                   "observation_id": "archived", "coordinate_claim_id": "claim"}])
        self.assertTrue(release_coordinate_decisions(decisions, {"selected"}).empty)


if __name__ == "__main__":
    unittest.main()
