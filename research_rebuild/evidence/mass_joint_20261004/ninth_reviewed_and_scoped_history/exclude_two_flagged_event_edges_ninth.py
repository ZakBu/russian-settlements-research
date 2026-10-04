from pathlib import Path
import csv,json,hashlib
C=Path('/workspace/settlements-work/continuation_20261004');D=C/'root/next_batch_manifest_preparation/ninth_reviewed_legacy204';M=D/'application_manifest.json'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
m=json.loads(M.read_text());spec=m['identity_sources'][0];p=Path(spec['candidate']['path']);assert sha(p)==spec['candidate']['sha256']
with p.open(newline='') as f:r=csv.DictReader(f);fields=r.fieldnames;original=list(r)
gate=C/'root/ninth_hard_event_gate_preflight.json';bad={r['sid'] for r in json.loads(gate.read_text())['hard_flagged_endpoints']}
kept=[r for r in original if not {r['from_source_record_id'],r['to_source_record_id']}&bad];held=[r for r in original if {r['from_source_record_id'],r['to_source_record_id']}&bad];assert len(kept)==202 and len(held)==2
out=D/'legacy_native_classifiers202_hard_event_clear_adapter.csv'
with out.open('x',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(kept)
record=D/'root_conservative_two_event_exclusions.json';record.write_text(json.dumps({'status':'root_conservative_exact_subset_of_independently_approved204','original_candidate':{'path':str(p),'sha256':sha(p)},'eligible_original204_unchanged':spec['eligible'],'independent_original_review_unchanged':spec['review_receipt'],'authoritative_flag_preflight':{'path':str(gate),'sha256':sha(gate)},'retained_exact_approved_rows':202,'held_exact_approved_rows':held,'reason':'Authoritative verified-successor event flags not considered in initial candidate/review gates. Hold these2 until finite typed receiver/predecessor review; no global hard gate bypass or invented ordinary identity.','selected_graph_population_modified':False},ensure_ascii=False,indent=2)+'\n')
spec['candidate']={'path':str(out),'sha256':sha(out)};m['root_conservative_hard_event_exclusions']={'path':str(record),'sha256':sha(record)}
new=D/'application_manifest_hard_event_clear202.json';new.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'manifest':str(new),'candidate_rows':202,'original_approved204_eligible_unchanged':True,'held_event_edges':2}))
