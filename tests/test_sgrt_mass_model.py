import sys
from pathlib import Path
import unittest
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/sgrt_mass'))
from model import unit_table,agri_profile,provenance_list


def reference():
    r=pd.DataFrame({'source_record_id':['a','b','c'],'name':['A','B','C'],'region':['r']*3,'population_role':['ordinary_settlement_record']*3})
    for y in [2002,2010,2021]:
        r[f'population_{y}']=[300,100,900]
        r[f'credit_{y}']=[True,True,False]
    return r


def members(provider):
    return pd.DataFrame({'origin_id':['a','b','c'],'provider_settlement_id':[provider]*3,
        'provider_site_id':['site']*3,'center_key':['site:site' if provider is None else 'np:'+provider]*3,
        'provider_name':['Site']*3,'provider_region':['r']*3,'provider_lat':[1.]*3,'provider_lon':[2.]*3,
        'center_identity_status':['unresolved_center_settlement_identity' if provider is None else 'known_settlement_id']*3,
        'cost_minutes':[0.,5.,8.],'point_separation_km':[0.,2.,3.],'local_supply_unknown':[False,True,True]})


class MassModelTest(unittest.TestCase):
    def test_mixed_source_years_preserve_unknown_and_array_encoding(self):
        self.assertEqual(provenance_list(2021.),'[2021]')
        self.assertEqual(provenance_list('["2026"]'),'["2026"]')
        self.assertIsNone(provenance_list(np.nan))
        self.assertIsNone(provenance_list(pd.NA))

    def test_unknown_site_ownership_does_not_prove_external_village(self):
        units,rows=unit_table(members(None),reference(),'school_general','physical_sites')
        self.assertEqual(units.external_records.iloc[0],0)
        self.assertEqual(units.n_populated_external.iloc[0],0)
        self.assertEqual(units.known_populated_origin_records.iloc[0],2)
        self.assertTrue(units.is_populated_site_service_cell.iloc[0])
        self.assertFalse(units.is_inhabited_external_candidate_cell.iloc[0])
        self.assertTrue(pd.isna(units.external_population_2021.iloc[0]))
        self.assertEqual(units.type_code.iloc[0],'center_settlement_identity_unknown')

    def test_uncredited_positive_record_is_not_added_as_population(self):
        units,rows=unit_table(members('a'),reference(),'medical_basic_primary','registry_or_address_np')
        self.assertEqual(units.external_records.iloc[0],2)
        self.assertEqual(units.n_populated_external.iloc[0],1)
        self.assertEqual(units.external_population_2021.iloc[0],100)
        self.assertEqual(units.external_population_unresolved_records.iloc[0],1)
        self.assertEqual(units.comparable_external_records_02_21.iloc[0],1)

    def test_municipal_crop_values_remain_context_and_ties_not_arbitrary(self):
        d=pd.DataFrame({'agri_sown_area_ha_2021_municipal_context':[100.,100.,np.nan],
            'agri_grain_sown_ha_2021_municipal_context':[60.,50.,20.],
            'agri_feed_sown_ha_2021_municipal_context':[20.,50.,10.],
            'agri_technical_sown_ha_2021_municipal_context':[10.,0.,np.nan]})
        p=agri_profile(d)
        self.assertEqual(p.agri_context_profile.tolist(),['grain_dominant_municipal_context','tied_selected_crop_groups','insufficient_municipal_data'])
        self.assertFalse(p.agri_profile_is_settlement_own_production.any())
        pd.testing.assert_series_equal(p.agri_sown_area_ha_2021_municipal_context,d.agri_sown_area_ha_2021_municipal_context)


if __name__=='__main__':unittest.main()
