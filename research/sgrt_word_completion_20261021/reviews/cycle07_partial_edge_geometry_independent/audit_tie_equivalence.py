from pathlib import Path
import json,hashlib,pandas as pd
H=Path(__file__).resolve().parent;R=H.parents[1];G=R/'transport/cycle07_geography_recovery_extension'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
w=pd.read_parquet(G/'all_equal_nearest_original_segment_witnesses_readback.parquet');a=pd.read_parquet(G/'equal_nearest_attachment_equivalence.parquet').set_index('id');approved=set(pd.read_parquet(R/'source_geography_recovery_cycle07/approved_coordinate_patch.parquet').id)
rows=[]
for uid,g in w.groupby('id',sort=False):
 g=g.sort_values(['way_id','segment_index']);base=g.iloc[0];eq=True
 for col in ['outgoing_seeds_json','incoming_seeds_json']:
  b={int(x['node']):float(x['minutes']) for x in json.loads(base[col])}
  for raw in g[col]:
   d={int(x['node']):float(x['minutes']) for x in json.loads(raw)}
   eq &= set(b)==set(d) and all(abs(b[k]-d[k])<=1e-7 for k in b) if set(b)==set(d) else False
 rows.append({'id':uid,'approved':uid in approved,'n_tied_segments':len(g),'directed_seed_maps_equivalent_within_1e7_minutes':bool(eq),'matches_producer_equivalence':bool(eq)==bool(a.loc[uid,'all_equal_nearest_directed_seed_attachments_equivalent'])})
t=pd.DataFrame(rows);t.to_parquet(H/'all479_tie_equivalence_readback.parquet',index=False)
checks={'all479_matches':len(t)==479 and t.matches_producer_equivalence.all(),'all45_ties':int(t.n_tied_segments.gt(1).sum())==45,'43_ties_equivalent':int((t.n_tied_segments.gt(1)&t.directed_seed_maps_equivalent_within_1e7_minutes).sum())==43,'two_not_equivalent_preserved':int((~t.directed_seed_maps_equivalent_within_1e7_minutes).sum())==2}
r={'status':'ACCEPTED_SCOPED_TIE_DISCLOSURE' if all(checks.values()) else 'REJECTED','all_checks_passed':bool(all(checks.values())),'checks':{k:bool(v) for k,v in checks.items()},'counts':{'diagnostic_points':len(t),'admitted_points':int(t.approved.sum()),'admitted_tied_points':int((t.approved&t.n_tied_segments.gt(1)).sum()),'admitted_nonequivalent_seed_maps':int((t.approved&~t.directed_seed_maps_equivalent_within_1e7_minutes).sum())},'non_equivalent_cases':t[~t.directed_seed_maps_equivalent_within_1e7_minutes].to_dict('records'),'interpretation':'43 of 45 tied points have equivalent directed seed maps. Two near-endpoint alternatives have additional seed nodes; these are disclosed, not declared identical. Primary attachment follows predeclared lexicographic original-segment rule, not fastest-route selection. Source access/cross-barrier permissions remain unobserved.','code_sha256':sha(__file__),'prerequisite_geometry_audit_sha256':sha(H/'audit.json')}
(H/'tie_equivalence_audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(r['counts']));assert r['all_checks_passed']
files=[p for p in H.iterdir() if p.is_file() and p.name!='review_freeze_manifest.json'];(H/'review_freeze_manifest.json').write_text(json.dumps({'scope':'Independent original-source segment geometry and directed partial-edge costs; 479 diagnostic / 477 admitted point identities','files':{p.name:sha(p) for p in files}},indent=2)+'\n')
