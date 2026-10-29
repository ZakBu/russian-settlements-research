import unittest
import pandas as pd
from scripts.sgrt_saratov.medical_competition import prepare_medical_seeds,display_groups,PITERKA

class MedicalNeedsRemainSeparate(unittest.TestCase):
    def test_many_basic_offers_do_not_become_a_physician_offer(self):
        catalog=pd.DataFrame({'catalog_id':['fap1','fap2','doctor','unroutable'],
            'family':['medical_basic','medical_basic','medical_physician','medical_physician'],
            'routable_provider':[True,True,True,False], 'correctsource_record_id':['a','b','c','d'],
            'location_precision':['point']*4})
        self.assertEqual(prepare_medical_seeds(catalog,'medical_basic').catalog_id.tolist(),['fap1','fap2'])
        self.assertEqual(prepare_medical_seeds(catalog,'medical_physician').catalog_id.tolist(),['doctor'])

    def test_both_functions_share_one_fixed_named_display_legend(self):
        tables=[pd.DataFrame({'destination_np_id':['a','a',PITERKA]}),pd.DataFrame({'destination_np_id':['b','a','c','d']})]
        roster=pd.DataFrame({'source_record_id':[PITERKA,'a','b','c','d'],'name':['Питерка','А','Б','В','Г']})
        classes,labels=display_groups(tables,roster)
        self.assertEqual(classes[PITERKA],0);self.assertEqual(labels['0'],'Питерка')
        self.assertEqual(len(classes),4);self.assertNotIn('d',classes)
        self.assertIn('Другие',labels['4'])

if __name__=='__main__':unittest.main()
