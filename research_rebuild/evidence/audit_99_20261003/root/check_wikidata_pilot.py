from pathlib import Path
import json, hashlib, time
import pandas as pd
import numpy as np

D=Path('/workspace/settlements-work/continuation_20261003/audit_99_20261003/wikidata')
F=Path('/workspace/settlements-delivery/continuation-consolidated-20261003')
O=D.parent/'root'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
t=time.monotonic()
s=json.loads((D/'wikidata_primary_pilot_summary.json').read_text())
c=pd.read_parquet(D/'wikidata_primary_core_candidates.parquet')
p=pd.read_csv(D/'large_pilot_pps_draws.csv',engine='python')
u=pd.read_csv(D/'large_pilot_sample_union.csv',engine='python')
for name, digest in s['outputs'].items(): assert sha(D/name)==digest
assert len(c)==12803 and c.current_population.sum()==3320225
assert c.source_record_id.is_unique
assert not set(c.source_record_id)&set(s['known_holds']['excluded_ids'])
assert c.candidate_status.eq('candidate_only_not_independently_reviewed_or_admitted').all()
assert c.P625_latitude.between(-90,90).all() and c.P625_longitude.between(-180,180).all()
assert all(all(json.loads(g).values()) for g in c.identity_candidate_gates_json)
large=c[c.current_population.ge(2000)].reset_index(drop=True)
assert len(large)==351 and large.current_population.sum()==2068453
assert len(p)==300 and p.pps_draw_index.tolist()==list(range(1,301))
weights=large.current_population.to_numpy(float)
prob=weights/weights.sum()
draws=np.random.default_rng(2026100301).choice(len(large),size=300,replace=True,p=prob)
assert p.source_record_id.tolist()==large.iloc[draws].source_record_id.tolist()
assert np.allclose(p.pps_draw_probability.to_numpy(),prob[draws],rtol=1e-12)
assert len(u)==200 and u.source_record_id.is_unique
assert set(p.source_record_id)<=set(u.source_record_id)<=set(large.source_record_id)
assert u.pps_draw_multiplicity.sum()==300
counts=p.source_record_id.value_counts().to_dict()
for r in u.itertuples(index=False):
 assert r.pps_draw_multiplicity==counts.get(r.source_record_id,0)
 assert json.loads(r.pps_draw_indices_json)==p.loc[p.source_record_id.eq(r.source_record_id),'pps_draw_index'].tolist()
targeted=int(u.targeted_strata_json.map(lambda v:bool(json.loads(v))).sum())
assert targeted==61
assert s['large_current_candidate_pool']['unique_candidates_in_PPS_or_targeted_union']==len(u)
assert s['large_current_candidate_pool']['targeted_unique_candidates']==targeted
accepted=pd.read_parquet(F/'accepted_point_uses.parquet',columns=['target_source_record_id'])
assert not set(c.source_record_id)&set(accepted.target_source_record_id)
result={'verdict':'PASS_CANDIDATE_EXPORT_AND_SAMPLE_INTEGRITY_ONLY','independent_geographical_review_performed':False,'new_point_or_identity_admissions':0,'core_rows':len(c),'core_population':int(c.current_population.sum()),'large_rows':len(large),'large_population':int(large.current_population.sum()),'seed':2026100301,'PPS_draws':len(p),'unique_PPS_candidates':int(p.source_record_id.nunique()),'unique_sample_union':len(u),'targeted_unique_candidates':targeted,'known_holds_excluded':True,'PPS_rng_and_multiplicity_verified':True,'outputs_sha256':s['outputs'],'seconds':round(time.monotonic()-t,3)}
(O/'wikidata_pilot_review.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
