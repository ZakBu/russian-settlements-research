"""Prepare new endpoint pairs and preserve redundant reviewed confirmations."""
from pathlib import Path
import csv,json,hashlib,duckdb
REPO=Path(__file__).resolve().parents[2]
BASE=Path('/workspace/settlements-work/continuation_20261004')
REVIEW=BASE/'independent_review/wd_two_year_signature_194'
PRODUCER=BASE/'R4/wide_qid_homonym_full_entity_retrieval_20261004_v2/entity_fetch_and_replay'
OUT=BASE/'root/next_batch_manifest_preparation/reviewed_wd193_extension'
PINS={REVIEW/'independent_review_receipt.json':'4da6bd297ad91599d24d218df1d6aa90993b7f1281689e2704053818a9b72a97',REVIEW/'eligible_identity_edges.csv':'6fb0d014501216cb7360a11f33bb5881689033d8f20d0fb8872db8fa9abd5ff8',REVIEW/'eligible_qid_pairs.csv':'08783bd39dd0d10ff2bb5510645a138372aecc2389ecafbd685736d3f25392fd'}
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):return {'path':str(p),'sha256':sha(p)}
def write(p,rows,fields):
 with p.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def main():
 for p,s in PINS.items():assert sha(p)==s
 cfg=json.loads((REPO/'config/mass_joint_20261004.json').read_text());g=Path(cfg['working_identity_graph']);assert sha(g)==cfg['working_identity_graph_sha256']
 con=duckdb.connect(config={'threads':1,'memory_limit':'1GB'})
 existing={tuple(sorted((a,b))) for a,b in con.execute('select from_source_record_id,to_source_record_id from read_parquet(?)',[str(g)]).fetchall()}
 approved=list(csv.DictReader((REVIEW/'eligible_identity_edges.csv').open()))
 producer=list(csv.DictReader((PRODUCER/'conditional_identity_edges.csv').open()))
 actual={(r['from_source_record_id'],r['to_source_record_id'],r['candidate_rule']):r for r in producer}
 new=[];confirmation=[]
 for r in approved:
  key=tuple(r[k] for k in ['from_source_record_id','to_source_record_id','candidate_rule']);assert key in actual
  for fld in ['wikidata_qid','from_year','to_year','population_2002_delta','population_2010_delta','match_quality']:
   assert r[fld]==actual[key][fld]
  (confirmation if tuple(sorted(key[:2])) in existing else new).append(r)
 assert len(new)==214 and len(confirmation)==172
 OUT.mkdir(parents=True,exist_ok=False);fields=list(approved[0]); cand=OUT/'new_214_reviewed_identity_edges.csv';over=OUT/'additional_172_reviewed_confirmations.csv'
 write(cand,new,fields);write(over,confirmation,fields)
 spec={'candidate':pin(cand),'eligible':pin(REVIEW/'eligible_identity_edges.csv'),'review_receipt':pin(REVIEW/'independent_review_receipt.json'),'candidate_columns':{'from':'from_source_record_id','to':'to_source_record_id','family':'candidate_rule','status':'review_status'},'eligible_columns':{'from':'from_source_record_id','to':'to_source_record_id','family':'candidate_rule'},'accepted_candidate_statuses':['eligible'],'canonical_columns':{'relation':'relation'},'additional_review_receipts':[pin(PRODUCER/'receipt.json')]}
 (OUT/'identity_source_spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
 receipt={'status':'reviewed_inputs_preparation_only_no_admissions','approved193_current_subjects':193,'reviewed386_edges':386,'new_endpoint_pairs':214,'additional_existing_pair_confirmations':172,'base_graph':pin(g),'reviewed_input_pins':{str(p):s for p,s in PINS.items()},'producer_candidates':pin(PRODUCER/'conditional_identity_edges.csv'),'outputs':{str(p):sha(p) for p in [cand,over,OUT/'identity_source_spec.json']},'script_sha256':sha(__file__)}
 (OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
