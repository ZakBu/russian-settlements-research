#!/usr/bin/env python3
"""Explain inherited accepted population overrides without altering raw observations."""
from pathlib import Path
import hashlib,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run():
    ap=ROOT/'axis/full_settlement_axis.parquet';lp=ROOT/'axis/source_observations_all.parquet'
    cp=REPO/'research_rebuild/evidence/next_overlay_application68_20261008/normalized_cumulative_claims.csv.gz'
    a=pd.read_parquet(ap,columns=['id','name','region','source_record_id_2010','population_2010','population_value_quality_2010'])
    raw=pd.read_parquet(lp);raw=raw[raw.census_year.eq(2010)][['id','source_record_id','population','population_value_quality']]
    z=a.merge(raw,left_on=['id','source_record_id_2010'],right_on=['id','source_record_id'],how='inner',validate='one_to_one',suffixes=('_accepted','_raw'))
    unequal=(z.population_2010.notna()!=z.population.notna())|(z.population_2010.notna()&z.population.notna()&z.population_2010.ne(z.population))
    z=z[unequal].copy();assert z.population_value_quality_2010.eq('reviewed_primary_reported_value').all()
    c=pd.read_csv(cp,low_memory=False)
    c['effective_primary_value']=pd.to_numeric(c.new_population,errors='coerce').combine_first(pd.to_numeric(c.official_population,errors='coerce')).combine_first(pd.to_numeric(c.population,errors='coerce'))
    replacements={}
    restore_receipts=[ROOT/'axis/tula_original_primary_restore_receipt.json',ROOT/'sourceavailability/national2010_exact_restore_receipt.json']
    t=json.loads(restore_receipts[0].read_text());assert t['exact_expected_source_restored'];replacements[t['actual_sha256']]=t['restored_path']
    n=json.loads(restore_receipts[1].read_text())
    # The exact national source may have multiple restored copies; select by known SHA.
    for p in Path('/workspace/scratch/frozen_primary_recovery').glob('*.pdf'):
        if sha(p)=='42cb939d8024042ffcf8a708676cef3f159a93e4dad697086c80465d445887c3':replacements[sha(p)]=str(p);break
    proofs=[];files={}
    fields=['official_source_record_id','official_source_sha256','official_source_locator','official_source_path','official_source_sheet','official_source_row','official_page','official_line_start','official_line_end','population_admission_basis','decision_status','source_population_binding_review_status','census_reference_date']
    for row in z.itertuples():
        cc=c[c.old_source_record_id.eq(row.source_record_id_2010)]
        assert len(cc) and cc.effective_primary_value.nunique()==1 and cc.effective_primary_value.iloc[0]==row.population_2010
        assert cc.decision_status.eq('accepted_population_publication_binding').all()
        evidence=[]
        for _,claim in cc.iterrows():
            h=claim.official_source_sha256;p=Path(replacements.get(h,claim.official_source_path))
            if str(p) not in files:files[str(p)]={'sha256':sha(p) if p.exists() else None,'exists':p.exists()}
            assert files[str(p)]['sha256']==h
            e={k:None if pd.isna(claim[k]) else claim[k] for k in fields};e['verified_current_source_path']=str(p);e['verified_current_source_sha256']=h;e['effective_primary_value']=float(claim.effective_primary_value);evidence.append(e)
        proofs.append({'id':row.id,'name':row.name,'region':row.region,'census_year':2010,'raw_source_record_id':row.source_record_id_2010,'raw_observation_population':row.population,'raw_observation_quality':row.population_value_quality,'accepted_axis_population':row.population_2010,'accepted_axis_quality':row.population_value_quality_2010,'accepted_source_claims_json':json.dumps(evidence,ensure_ascii=False),'raw_ledger_is_not_effective_accepted_population':True,'new_primary_reading_claimed':False})
    d=pd.DataFrame(proofs);assert d.id.is_unique and len(d)==5719
    d.to_parquet(ROOT/'axis/inherited_reviewed_population2010_provenance_bridge.parquet',index=False)
    receipt={'status':'ALL_ACCEPTED_VS_RAW_VALUE_DIFFERENCES_EXPLAINED','rows':len(d),'raw_ledger_modified':False,'axis_modified':False,'all_effective_claim_values_unique_and_match_axis':True,'all_primary_source_bytes_verified':True,'primary_files':files,'source_claims_path':str(cp.relative_to(REPO)),'source_claims_sha256':sha(cp),'axis_sha256':sha(ap),'raw_ledger_sha256':sha(lp),'interpretation':'Historical accepted reviewed-primary overlay supersedes raw secondary count while preserving original source-record identity; this bridge discloses both values and primary locators, not a new identity or source reading'}
    (ROOT/'axis/inherited_population_bridge_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':run()
