from pathlib import Path
import re,json,hashlib,pandas as pd
from pypdf import PdfReader
E=Path(__file__).resolve().parent;d=pd.read_csv(E/'ready_primary2010_regional_claims.csv.gz');reader=PdfReader(E/'tula_2010_official_Tom1.pdf');cache={};rows=[];fails=[];sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
for r in d.itertuples():
 pg=int(r.official_page)
 if pg not in cache:cache[pg]=reader.pages[pg-1].extract_text()
 label='\\s*'.join(re.escape(x)for x in re.sub(r'\s+','',r.official_raw_NP_caption));nums=[str(int(x))if pd.notna(x)else '-'for x in [r.official_population,r.official_men,r.official_women]];pattern=label+r'\s+'+r'\s+'.join(re.escape(x)for x in nums)+r'(?:\s|$)';hits=list(re.finditer(pattern,cache[pg]))
 if len(hits)!=1:fails.append({'sid':r.old_source_record_id,'caption':r.official_raw_NP_caption,'page':pg,'hits':len(hits)})
 else:rows.append({'old_source_record_id':r.old_source_record_id,'official_source_record_id':r.official_source_record_id,'official_source_locator':r.official_source_locator,'independent_pypdf_literal_caption_and_P_M_F':hits[0].group(),'count_readback':'PASS'})
pd.DataFrame(rows).to_csv(E/'tula_all_claims_independent_pypdf_readback.csv.gz',index=False,compression={'method':'gzip','mtime':0});r={'status':'PASS'if not fails else'HOLD_readback_exceptions','claims':len(d),'pypdf_actual_cells_PASS':len(rows),'exceptions':fails,'claim_sha256':sha(E/'ready_primary2010_regional_claims.csv.gz'),'output_sha256':sha(E/'tula_all_claims_independent_pypdf_readback.csv.gz'),'NULL_sex_preserved_rows':int((d.official_men.isna()|d.official_women.isna()).sum()),'no_count_used_for_binding':True};(E/'tula_all_claims_independent_readback_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False,indent=2)[:6000])
