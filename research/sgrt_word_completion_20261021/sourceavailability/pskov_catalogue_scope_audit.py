from pathlib import Path
from bs4 import BeautifulSoup
import json,hashlib
R=Path(__file__).resolve().parent;P=Path('/workspace/scratch/sgrt_demography2010/pskov_catalog_archived.html');s=BeautifulSoup(P.read_bytes(),'html.parser');links=[]
for a in s.find_all('a',href=True):
 h=a['href'];t=a.parent.parent.get_text(' ',strip=True)
 if '/storage/'in h:links.append(dict(href=h,title=t))
attachments=[]
for p in Path('/workspace/scratch/sgrt_demography2010/pskov_source_check/attachments').glob('*.htm'):
 s=BeautifulSoup(p.read_bytes(),'html.parser');txt=s.get_text(' ',strip=True);attachments.append(dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),HTML_table_rows=len(s.select('tr')),heading=txt[:430],grain='municipal_aggregates_or_population_groups_not_all_physical_NP'))
r=dict(official_catalogue='https://60.rosstat.gov.ru/vpn2010',catalogue_cached_bytes=P.stat().st_size,catalogue_sha256=hashlib.sha256(P.read_bytes()).hexdigest(),catalogue_download_links=links,actual_attachment_review=attachments,actual_primary_documents_downloaded=['t1_Итоги-ВПН2010.pdf: city/pgt/district only, no full rural NP list','t1_pub-01-01_Терр=58000000.pdf: size-group aggregate counts only','приложения.rar: 8 HTML tables, municipality and age/sex/group aggregates'],new_verified_full_NP_primary_rows=0,full_physical_NP_scope_not_recovered=True,secondary_citations_have_title_but_no_download_URL=True,secondary_citation_inspected='https://www.wikidata.org/wiki/Q18772480, 2010 population reference gives only title; this does not expose original publication',conclusion='Full all-NP primary2010 publication not recovered through these actual official catalogue files. This proves these inspected files have wrong grain, not that a full publication does not exist. No protected Pskov row upgraded.',do_not_promote_municipal_aggregate_as_NP=True)
(R/'pskov_full_NP_scope_audit.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print('Official links',len(links),'attachments',len(attachments),'new primary full-NP rows',0)
