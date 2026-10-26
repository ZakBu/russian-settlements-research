import sys
from pathlib import Path
import unittest
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/sgrt_zero'))
from centrality_profiles import medical_counts, assemble, feature_counts


class CentralityEvidenceTests(unittest.TestCase):
    def medical(self):
        return pd.DataFrame({'UIDSPMO': ['d1', 'd1', 'd2'], 'IDADDRESS': ['a1'] * 3,
                             'service_code': ['hospital', 'specialized', 'hospital'],
                             'medical_need_scope': ['therapy', 'therapy', 'surgery']})

    def test_services_and_subdivisions_do_not_multiply_one_address(self):
        address = pd.DataFrame({'UIDSPMO': ['d1', 'd2'], 'IDADDRESS': ['a1', 'a1'], 'source_record_id': ['n', 'n']})
        out, _ = medical_counts(self.medical(), address)
        self.assertEqual(out.loc['n', 'medical_care_address_ids_known'], 1)
        self.assertEqual(out.loc['n', 'medical_subdivision_ids_known'], 2)
        self.assertEqual(out.loc['n', 'medical_clinical_profiles_known'], 2)

    def test_conflicting_address_identity_is_not_split_between_cities(self):
        address = pd.DataFrame({'UIDSPMO': ['d1', 'd2'], 'IDADDRESS': ['a1', 'a1'], 'source_record_id': ['n', 'other']})
        with self.assertRaises(ValueError):
            medical_counts(self.medical(), address)

    def test_missing_inventory_is_not_zero(self):
        ref = pd.DataFrame(dict(source_record_id=['a', 'b'], name=['A', 'B'], region='r',
                                lat=50., lon=40., population_2021=[100., 1000.], population_role='ordinary_settlement_record'))
        med = pd.DataFrame({'medical_care_address_ids_known': [2]}, index=pd.Index(['a'], name='source_record_id'))
        out = assemble(ref, med).set_index('source_record_id')
        self.assertTrue(pd.isna(out.loc['b', 'medical_care_address_ids_known']))
        self.assertTrue(pd.isna(out.loc['b', 'independent_positive_medical_stock_proxy']))
        self.assertFalse(out.loc['a', 'capacity_and_patient_flow_established'])

    def test_duplicate_physical_objects_and_rejected_identity_do_not_inflate_features(self):
        frame = pd.DataFrame(dict(source_record_id=['a', 'a', 'a'], canonical_site_id=['s', 's', 't'],
                                  service_code='school', supply_status='observed', eligible=[True, True, False]))
        out, _ = feature_counts(frame, site_column='canonical_site_id', prefix='school_', admission_columns=['eligible'])
        self.assertEqual(out.loc['a', 'school_school'], 1)


if __name__ == '__main__':
    unittest.main()
