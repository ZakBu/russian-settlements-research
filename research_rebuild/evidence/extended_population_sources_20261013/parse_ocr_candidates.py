from pathlib import Path
import csv,collections,re,json,hashlib
base=Path('/workspace/shared/extended-population-20261013');out=Path('/workspace/russian-settlements-research/research_rebuild/evidence/extended_population_sources_20261013');result=[];region='';typ='';headers=[]
for page in range(85,126):
 for side in ['left','right']:
  if page==85 and side=='left':continue
  p=base/f'ocr_{page:03d}_{side}.tsv'
  if not p.exists():continue
  lines=collections.defaultdict(list)
  for r in csv.DictReader(p.open(),delimiter='\t',quoting=csv.QUOTE_NONE):
   if r['level']=='5' and r['text'].strip():lines[(r['block_num'],r['par_num'],r['line_num'])].append(r)
  cut=[0,290,385,470,555,638,720,800,900] if side=='left' else [0,345,430,510,595,680,765,840,950]
  for line,words in lines.items():
   words=sorted(words,key=lambda r:int(r['left']));raw=' '.join(r['text'] for r in words)
   if re.search('област|край|АССР|автономн',raw,re.I) and sum(bool(re.search('[0-9]{3}',r['text'])) for r in words)<2:
    region=raw;headers.append({'pdf_page':page,'side':side,'line':line,'region_ocr_raw':region});continue
   if re.search('^Города[ .|]*$',raw):typ='Города';continue
   if 'оселки' in raw and 'типа' in raw:typ='Поселки городского типа';continue
   groups=[[] for _ in range(8)]
   for r in words:
    x=int(r['left'])+int(r['width'])/2
    for i in range(8):
     if cut[i]<=x<cut[i+1]:groups[i].append(r);break
   vals=[' '.join(r['text'] for r in group) for group in groups]
   normalized=[re.sub(r'[|\[\]{}]+','',v).strip() for v in vals]
   numeric=[v if re.fullmatch(r'\d{1,7}',v) else '' for v in normalized]
   if sum(bool(x) for x in numeric[2:6])<3:continue
   result.append({'source_pdf_page_1based':page,'scan_side':side,'ocr_line_key':':'.join(line),'region_ocr_raw':region,'type_ocr_raw':typ,'name_ocr_raw':vals[0],'name_contains_cyrillic':bool(re.search('[А-Яа-яЁё]',vals[0])),'formation_year_ocr_raw':vals[1],'population_1979_present_ocr_raw':vals[2],'population_1979_permanent_ocr_raw':vals[3],'population_1989_present_ocr_raw':vals[4],'population_1989_permanent_ocr_raw':vals[5],'ratio_present_ocr_raw':vals[6],'ratio_permanent_ocr_raw':vals[7],'population_1979_present_candidate':numeric[2],'population_1979_permanent_candidate':numeric[3],'population_1989_present_candidate':numeric[4],'population_1989_permanent_candidate':numeric[5],'ocr_line_raw':raw,'ocr_min_word_confidence':min(float(w['conf']) for w in words),'source_pdf_sha256':'e0144d44e94b0c324ad573daeb80621265a0ce01e03bdc9c3e676eaf5ec892a9','ocr_tsv_sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest(),'status':'candidate_ocr_unreviewed_not_admitted','context_status':'OCR_region_type_header_carry_unreviewed','identity_status':'not_matched'})
if result:
 with (out/'bulk_ocr_locality_candidates.csv').open('w') as f:w=csv.DictWriter(f,list(result[0]));w.writeheader();w.writerows(result)
(out/'bulk_header_candidates.json').write_text(json.dumps(headers,ensure_ascii=False,indent=2))
print('candidate_rows',len(result),'pages',len(set(r['source_pdf_page_1based'] for r in result)))
