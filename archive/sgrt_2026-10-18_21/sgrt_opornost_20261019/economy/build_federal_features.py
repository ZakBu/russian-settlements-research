#!/usr/bin/env python3
"""Two federal-city legal-territory aggregates, not point geocoding."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from build_point_features import COLS,GROUPS,SECTIONS,sha,dump
from build_coded_features import codes

def run(root,out,year):
    out.mkdir(parents=True,exist_ok=True);source=root/f'inputs/recovery_inputs/enrichment/rfsd_{year}_selected.parquet'
    sums={};sections={};raw={'45':0,'40':0}
    labels={'45':'RU-FED-MOW','40':'RU-FED-SPB'}
    expected={'retail47':'G','food56':'I','accommodation55':'I','education85':'P',
      'health86':'Q','social8788':'Q','repair95':'S','personal96':'S','finance64to66':'K','admin84':'O'}
    for prefix in labels:
        for mode in ['federal_coded_baseline','federal_coded_strict_house']:
            sums[prefix,mode]={'id':labels[prefix],'year':year,'quality_mode':mode,'legal_entities':0,
             'exact_federal_territory_code':True,'point_location_asserted':False,'financial_eligible_reports':0,
             'known_nominal_revenue_thousand_rub':0.,'entities_geocoding_house':0,'entities_geocoding_street':0,
             'entities_geocoding_city':0,'entities_geocoding_missing_or_other':0,
             **{'section_'+s+'_legal_entities':0 for s in 'GIPQ'},**{g+'_legal_entities':0 for g in GROUPS}}
            sections[prefix,mode]={s:0 for s in SECTIONS}
    for b in pq.ParquetFile(source).iter_batches(batch_size=100000,columns=COLS+['oktmo']):
        d=b.to_pandas();pc=codes(d.oktmo).str[:2];inn=d.inn.notna()&d.inn.fillna('').str.strip().ne('')
        for pre in labels:
            z=d[pc.eq(pre).fillna(False)&inn];raw[pre]+=len(z)
            for mode in ['federal_coded_baseline','federal_coded_strict_house']:
                v=z if mode.endswith('baseline') else z[z.geocoding_quality.eq('house')]
                r=sums[pre,mode];r['legal_entities']+=len(v)
                sec=v.okved_section.fillna('UNKNOWN');prefs=v.okved.fillna('').str.extract(r'^(\d{2})',expand=False)
                for s,k in sec.value_counts().items():sections[pre,mode][s if s in SECTIONS else 'UNKNOWN']+=int(k)
                for s in 'GIPQ':r['section_'+s+'_legal_entities']+=int(sec.eq(s).sum())
                for g,ps in GROUPS.items():r[g+'_legal_entities']+=int((prefs.isin(ps)&sec.eq(expected[g])).sum())
                q=v.geocoding_quality.fillna('missing_or_other')
                for quality in ['house','street','city']:
                    r['entities_geocoding_'+quality]+=int(q.eq(quality).sum())
                r['entities_geocoding_missing_or_other']+=int((~q.isin(['house','street','city'])).sum())
                f=v.eligible.eq(1)&v.filed.eq(1)&v.articulated.eq(1)&v.outlier.eq(0)&v.line_2110.notna()&v.line_2110.ge(0)
                if mode.endswith('house'):f &= v.imputed.eq(0)
                r['financial_eligible_reports']+=int(f.sum());r['known_nominal_revenue_thousand_rub']+=float(v.loc[f,'line_2110'].sum())
    result=[]
    for k,r in sums.items():
        counts=np.array(list(sections[k].values())[:-1]);total=counts.sum();shares=counts/total if total else counts
        r['section_diversity']=int((counts>0).sum());r['section_shannon']=float(-(shares*np.log(np.where(shares>0,shares,1))).sum())
        r['unknown_section_legal_entities']=sections[k]['UNKNOWN'];r['broad_service_legal_entities']=sum(r['section_'+s+'_legal_entities'] for s in 'GIPQ')
        gs=['retail47','food56','education85','health86','social8788','repair95','personal96']
        r['direct_consumer_service_legal_entities']=sum(r[g+'_legal_entities'] for g in gs);r['direct_consumer_function_diversity']=sum(r[g+'_legal_entities']>0 for g in gs)
        result.append(r)
    df=pd.DataFrame(result);df.to_parquet(out/'federal_legal_territory_features.parquet',index=False);df.to_csv(out/'federal_legal_territory_features.csv',index=False)
    pd.testing.assert_frame_equal(df,pd.read_parquet(out/'federal_legal_territory_features.parquet'))
    dump(out/'federal_provenance.json',{'source_sha256':sha(source),'code_sha256':sha(Path(__file__)),
      'raw_entity_counts':raw,'level':'federal_city_territory_legal_registration_not_settlement_point',
      'code_prefixes':labels,'baseline_entities_balance':int(df[df.quality_mode.eq('federal_coded_baseline')].legal_entities.sum())==sum(raw.values()),'readback_pass':True})
    print(df[['id','year','quality_mode','legal_entities','direct_consumer_service_legal_entities']].to_json(orient='records'),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--restored',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    for y in [2021,2016]:run(a.restored,a.out/str(y),y)
