from pathlib import Path
import json,hashlib,collections
import pandas as pd
O=Path(__file__).parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
f=pd.read_csv(O.parent/'current_missing_point_mass_20261008/prioritized_unresolved_after_all_packets.csv.gz',dtype=str,keep_default_na=False)
e=pd.read_csv(O/'accepted_source_bound_ownpoint_evidence.csv.gz',dtype=str,keep_default_na=False)
a=pd.read_csv(O/'all_article_binding_checks.csv.gz',dtype=str,keep_default_na=False)
h=pd.read_csv(O/'article_binding_holds.csv.gz',dtype=str,keep_default_na=False)
h=h[~h.source_record_id.isin(e.source_record_id)]
reasons=h.groupby('source_record_id').hold_reasons.agg(lambda s:';'.join(sorted(set(';'.join(s).split(';'))))).to_dict()
rem=f[~f.source_record_id.isin(e.source_record_id)].copy()
rem['round2_article_hold_reasons']=rem.source_record_id.map(reasons).fillna('')
rem['round2_source_status']=rem.source_record_id.map(lambda s:'source_article_binding_held' if s in reasons else 'no_reviewed_own_article_source_positive')
rem.to_csv(O/'prioritized_unresolved_after_round2.csv.gz',index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
h.to_csv(O/'unresolved_article_source_binding_holds.csv.gz',index=False,compression={'method':'gzip','mtime':0,'compresslevel':9})
pop=lambda s:float(pd.to_numeric(s,errors='coerce').sum())
r=json.loads((O/'stage62_point_admission_receipt.json').read_text())
r.update(unresolved_after_round2_rows=len(rem),unresolved_after_round2_known_population2021=pop(rem.population),unresolved_reviewed_article_binding_held_NPs=h.source_record_id.nunique(),unresolved_reviewed_article_comparison_holds=len(h),positive100_remaining_rows=int((pd.to_numeric(rem.population,errors='coerce')>=100).sum()),source_population_unknown_not_imputed=True)
(O/'final_handoff_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
(O/'README.md').write_text('''# Current positive residual ownpoint sources, stage 62 → 63

Frozen replay packet: **133 current settlement ownpoints, 43,145 known 2021 residents**. 132 points are literal coordinates from an explicitly associated physical settlement Wikipedia article revision/own infobox. One point uses the original unique owncoded FIAS level 6 provider coordinate after independent article identity support; its provider identifier binding is asserted separately. All other supplier identifier bindings are unasserted.

`accepted_point_use_delta.csv.gz` is the canonical point-use delta; `accepted_source_bound_ownpoint_evidence.csv.gz` carries original native NP rows, article name/type/region/county/parish, literal coordinates, revision identifiers, complete source file hashes/locators, and same-county native rivals. Complete API responses are retained in revision batch gzip files. Discovery search results confer no acceptance. HTTPS requests used normal certificate verification.

Admission requires positive physical NP typing, exact closed name normalization or directly reopened own full NP code, proper regional and county context, and an own code or specific parish when native same-county rivals exist. Multiple positively associated articles are held. Only own NP infobox coordinates are extracted. The additional coded provider point has its own raw code, name/type, unique FIAS settlement-level identity and unique native raw code checks. Raw present-day representative points are not census-date coordinate measurements or population boundary comparability proofs.

Actual stage 62 component and active-point snapshots were used without loading State. All 133 pass component 5 km consistency, existing current exact-point occupancy, and joint newpoint distinctness. Zero spatial/duplicate holds. Source counts, populations, qualities, and identity graph remain unchanged. One accepted row representing 290 residents already has primary-axis credit; actual coverage gain requires root's canonical stage 63 replay.

43 unresolved NPs have 69 explicit article comparison holds, preserved in `unresolved_article_source_binding_holds.csv.gz`. Rejected articles for an accepted NP remain in the complete review ledger, but are not counted as unresolved NPs. Classifier mirrors fetched for homonym context do not supply an undocumented old-code replacement or parent bridge. `prioritized_unresolved_after_round2.csv.gz` retains every remaining row, including unknown/zero population without imputation.

Frozen manifest pins every packet asset. Existing large upstream snapshots and original raw sources are referenced by their file hashes, not copied. No fresh large source download, canonical code/ledger change, diary edit, or graph-edge claim is included.
''')
files=[p for p in O.iterdir() if p.is_file() and p.name!='frozen_asset_manifest.json']
manifest={'packet_status':'frozen_ready_root_canonical63_replay','accepted_current_ownpoints':133,'accepted_known_population2021':43145,'assets':{str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(files)},'generated_total_bytes':sum(p.stat().st_size for p in files),'budget_bytes':20_000_000,'upstream_pins':r['input_pins']}
assert manifest['generated_total_bytes']<manifest['budget_bytes']
(O/'frozen_asset_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k not in ['input_pins','output_pins']},ensure_ascii=False));print('bytes',manifest['generated_total_bytes']);print('manifest_sha256',sha(O/'frozen_asset_manifest.json'))
