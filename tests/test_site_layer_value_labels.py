import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import site_content,build_site_data

PAYLOAD=b'id,name,value,lon,lat\na,First,0,45,51\nb,Last,3,46,52\n'
DATASET={'id':'labelled','url':'https://example.test/v1/points.csv','sha256':hashlib.sha256(PAYLOAD).hexdigest()}

def layer():
    return {'id':'labelled-layer','researchId':'sgrt','title':'Classes','description':'Four time bands',
            'datasetId':'labelled','adapter':'csv-points','geometry':'point',
            'fields':{'id':'id','name':'name','value':'value','longitude':'lon','latitude':'lat'},
            'palette':'categorical','unit':'class','period':'2021','evidence':'model','visibility':'published'}

class ClassLabelContract(unittest.TestCase):
    def test_optional_labels_leave_existing_layer_valid(self):
        self.assertEqual(site_content.layer_errors(layer(),{'labelled':DATASET},{'sgrt':{}}),[])
        row=layer();row['valueLabels']={'0':'0–10 мин','3':'30–60 мин'}
        self.assertEqual(site_content.layer_errors(row,{'labelled':DATASET},{'sgrt':{}}),[])

    def test_nonfinite_duplicate_or_blank_labels_are_rejected(self):
        for labels in ({},{'NaN':'Unknown'},{'0':'','3':'Last'},{'1':'One','1.0':'Duplicate'},{'0':'<script>bad</script>'}):
            row=layer();row['valueLabels']=labels
            with self.subTest(labels=labels):
                self.assertTrue(any(f=='valueLabels' for f,_ in site_content.layer_errors(row,{'labelled':DATASET},{'sgrt':{}})))

    def test_export_retains_labels_and_rejects_unlabelled_observed_class(self):
        for labels,works in [({'0':'0–10 мин','3':'30–60 мин'},True),({'0':'Only first'},False)]:
            with self.subTest(labels=labels),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);content=root/'content';(content/'layers').mkdir(parents=True)
                (content/'datasets.json').write_text(json.dumps([DATASET]));row=layer();row['valueLabels']=labels
                (content/'layers/labelled-layer.json').write_text(json.dumps(row))
                with patch.object(build_site_data,'layer_source',return_value=PAYLOAD):
                    if works:
                        registry=build_site_data.export_layers(content,root/'output',root/'cache',{})
                        self.assertEqual(registry[0]['valueLabels'],labels)
                    else:
                        with self.assertRaisesRegex(ValueError,'omit observed classes'):
                            build_site_data.export_layers(content,root/'output',root/'cache',{})
                        self.assertFalse((root/'output/custom-layers/labelled-layer.geojson').exists())

if __name__=='__main__':unittest.main()
