"""Export bounded active64 claim bindings; no admission, graph or point mutation."""
from pathlib import Path
import json,hashlib
import pandas as pd
import duckdb
OUT=Path(__file__).resolve().parent;E=OUT.parent;BASE=E/'main_axis_residual_application64_20261008';Z=E/'shared_ownpoint_conflict_route_20261008'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=json.loads((BASE/'application_receipt.json').read_text());assert sha(BASE/'application_receipt.json')=='adac8a1b1204d1aa5e59e64f35ca078cc2a65d1d7b2375ed2dea6513c047768d'
for n in ['applied_component_snapshot.csv.gz','applied_point_snapshot.parquet','applied_state_observations.parquet']:assert sha(BASE/n)==r['output_pins'][n]['sha256']
g=pd.read_csv(Z/'RCSI_GN_corroboration.csv',dtype=str,keep_default_na=False);g=g[g.within_1km.eq('1')&g.all_candidates_gt5km_except_near.eq('True')];assert len(g)==44 and g.target_source_record_id.is_unique
p=pd.read_csv(Z/'proposed_RCSI_current_point_replacements_not_applied.csv.gz',dtype=str,keep_default_na=False);p=p[p.target_source_record_id.isin(g.target_source_record_id)];assert len(p)==44 and p.target_source_record_id.is_unique
cs=pd.read_csv(BASE/'applied_component_snapshot.csv.gz',dtype=str,keep_default_na=False);roots=set(cs.loc[cs.source_record_id.isin(p.target_source_record_id),'root']);members=cs[cs.root.isin(roots)];ids=members.source_record_id.tolist();c=duckdb.connect(config={'threads':1});q=','.join('?' for _ in ids)
points=c.execute('SELECT * FROM read_parquet(?) WHERE source_record_id IN ('+q+')',[str(BASE/'applied_point_snapshot.parquet'),*ids]).fetchdf();obs=c.execute('SELECT * FROM read_parquet(?) WHERE source_record_id IN ('+q+')',[str(BASE/'applied_state_observations.parquet'),*ids]).fetchdf();c.close();assert len(obs)==len(ids) and points.source_record_id.is_unique
active=points.set_index('source_record_id');by=obs.set_index('source_record_id')
for row in p.to_dict('records'):
 sid=row['target_source_record_id'];old=active.loc[sid];native=by.loc[sid];assert int(native.census_year)==2021 and (float(old.latitude),float(old.longitude))==(float(row['old_latitude']),float(row['old_longitude']))
 assert str(native.oktmo).removesuffix('.0')==row['native_OKTMO']
 assert old.point_ledger_path and old.point_origin_file and old.point_origin_sha256
points.to_parquet(OUT/'RCSI44_actual64_active_component_point_claims.parquet',index=False,compression='zstd');obs.to_parquet(OUT/'RCSI44_actual64_native_component_observations.parquet',index=False,compression='zstd');members.to_csv(OUT/'RCSI44_actual64_component_members.csv.gz',index=False,compression={'method':'gzip','mtime':0});p.to_csv(OUT/'RCSI44_root_authorized_sourcepositive_proposals_not_applied.csv.gz',index=False,compression={'method':'gzip','mtime':0})
result={'status':'bounded_actual64_active_claim_bindings_only_no_admission_or_mutation','proposal_targets':44,'component_observations':len(obs),'active_component_points':len(points),'all_old_coords_and_native_codes_match_actual64':True,'input_pins':{str(f):sha(f) for f in [BASE/'application_receipt.json',BASE/'applied_component_snapshot.csv.gz',BASE/'applied_point_snapshot.parquet',BASE/'applied_state_observations.parquet',Z/'proposed_RCSI_current_point_replacements_not_applied.csv.gz',Z/'RCSI_GN_corroboration.csv']},'output_pins':{f.name:sha(f) for f in OUT.glob('RCSI44_*') if f.is_file()}};(OUT/'RCSI44_active_binding_receipt.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['input_pins','output_pins']}))
