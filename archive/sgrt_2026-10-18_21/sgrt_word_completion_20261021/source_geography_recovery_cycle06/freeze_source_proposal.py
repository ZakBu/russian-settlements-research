from pathlib import Path
import hashlib,json,datetime
H=Path(__file__).resolve().parent

def main():
 p=H/'artifact_manifest.json';assert not p.exists();parts=[]
 for f in sorted(H.rglob('*')):
  if not f.is_file() or '__pycache__' in f.parts:continue
  parts.append({'path':str(f.relative_to(H)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
 out={'status':'FROZEN_SOURCE_PROPOSAL_NO_AXIS_ADOPTION','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'final_candidate_receipt':'finite_source_candidate_proposal_receipt.json','files':parts,'file_count':len(parts),'bytes':sum(x['bytes'] for x in parts),'independent_source_admission':'external guardian receipt required before versioned cycle07 adoption','original_accepted_axis_graph_matrix_and_model_untouched':True};p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'file_count':len(parts),'bytes':out['bytes'],'manifest_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
if __name__=='__main__':main()
