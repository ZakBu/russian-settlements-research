#!/usr/bin/env python3
from pathlib import Path
import pandas as pd,json,hashlib,datetime
H=Path(__file__).resolve().parent;ROOT=H.parents[1];REPO=ROOT.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.relative_to(REPO))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def run():
 source=ROOT/'geographic_context_cycle06/nonchernozem/settlement_historical_nonchernozem_context_1974.parquet';review=ROOT/'reviews/cycle06/nonchernozem_historical_source_visual_admission.json';admission=ROOT/'geographic_context_cycle06/nonchernozem/guardian_source_admission.json';freeze=ROOT/'geographic_context_cycle06/nonchernozem/freeze_manifest.json';out=H/'settlement_nonchernozem_hypothesis_only.parquet';assert not out.exists(),'Never overwrite projection'
 aj=json.loads(admission.read_text());assert aj['independent_review_sha256']==sha(review);assert json.loads(review.read_text())['status']=='ACCEPTED'
 # Source projection preserves every original value and the original row order.
 x=pd.read_parquet(source);assert not x.id.duplicated().any();col='nonchernozem_historical_regional_context_1974';v=x[col].astype('boolean');assert v.dropna().eq(True).all() and int(v.sum())==101453
 x['nonchernozem_geographic_evidence']=v;x['nonchernozem_exact_contemporary_geographic_evidence']=pd.array([pd.NA]*len(x),dtype='boolean');x['nonchernozem_operational_Word_type7_hypothesis_only']=True;x['nonchernozem_alias_is_modern_precise_zone_or_soil']=False;x.to_parquet(out,index=False)
 old=pd.read_parquet(source);new=pd.read_parquet(out);assert old.equals(new[old.columns]);assert new.nonchernozem_geographic_evidence.equals(v.rename('nonchernozem_geographic_evidence'));assert new.nonchernozem_exact_contemporary_geographic_evidence.isna().all()
 layer=dict(path=rel(out),key='id',prefix='',optional=False,retain_prefixes=['nonchernozem_']);dump(H/'additive_nonmass_layer_stanza.json',dict(layer=layer,provenance_sidecars=[rel(H/'receipt.json'),rel(review),rel(admission),rel(freeze)],add_to_future_final_config_clones_only=True,own_Mi_or_eligibility_changed=False))
 dump(H/'receipt.json',dict(status='HYPOTHESIS_ONLY_HISTORICAL_REGIONAL_OPERATIONAL_WORD_TYPE7',rows=len(x),historical_positive=101453,historical_unknown=int(v.isna().sum()),contemporary_exact_unknown=len(x),source_year=1974,publication_year=1975,scope='finite historical regional successor context; inherited coarse presence only',original_columns_order_rows_values_unchanged=True,modern_precise_zone_claim=False,own_soil_or_parcel_claim=False,causal_claim=False,nonmass=True,sufficient_literal_Word_type7_evidence=False,interpretation_approved_before_outcomes=True,model_outcomes_read=False,input_sha256={rel(p):sha(p) for p in [source,review,admission,freeze]},output_sha256=sha(out),code_sha256=sha(Path(__file__))))
 files=[p for p in H.iterdir() if p.is_file()];dump(H/'freeze_manifest.json',dict(status='FROZEN_HISTORICAL_CONTEXT_PROJECTION_ONLY',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files={p.name:sha(p) for p in files}));print(out)
if __name__=='__main__':run()
