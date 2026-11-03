#!/usr/bin/env python3
"""Extract the dated Ozon tariff geography; pilot exact named linkage in 3 regions.

Eligibility list is not operating pickup network, opening dates or actual users.
No fuzzy/nearest matching; repeated names remain unresolved.
"""
import argparse,collections,csv,hashlib,json,re,subprocess,unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
PDF_SHA='136f558365b6057335a209c2b6370527f049a2498e66e2f155cf620f66bb1150'
PILOTS={'Тверская область':'тверская','Нижегородская область':'нижегородская','Краснодарский край':'краснодарский'}
def norm(s):
 return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(s)).casefold().replace('ё','е')).strip()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--work',type=Path,default=ROOT/'work/ecommerce_next_20261103/identification')
 p.add_argument('--axis',type=Path,default=None,help='Optional census base for diagnostic name-only linkage. Omit for self-contained source extraction.')
 p.add_argument('--summary-output',type=Path,default=Path(__file__).resolve().parent/'eligibility_list_summary2022.json')
 args=p.parse_args();d=args.work;pdf=d/'tariff_20221022001416.pdf';assert hashlib.sha256(pdf.read_bytes()).hexdigest()==PDF_SHA
 txt=pdf.with_suffix('.txt');subprocess.run(['pdftotext','-layout',str(pdf),str(txt)],check=True)
 rows=[]
 for pg,page in enumerate(txt.read_text().split('\f'),1):
  for line in page.splitlines():
   line=line.strip()
   if not line or 'Населённый пункт' in line:continue
   cells=re.split(r'\s{2,}',line)
   if len(cells)!=2:raise ValueError(f'Unexpected columns on page{pg}: {line}')
   rows.append({'row_n':len(rows)+1,'pdf_page':pg,'region_source':cells[0],'name_source':cells[1]})
 counts=collections.Counter((r['region_source'],norm(r['name_source'])) for r in rows)
 with (d/'eligibility_20221022_rows.csv').open('w',newline='') as f:
  wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
 summary={'source_snapshot':'2022-10-22T00:14:16Z','pdf_sha256':PDF_SHA,'list_rows_n':len(rows),'distinct_literal_region_labels_n':len(set(r['region_source'] for r in rows)),'unique_region_normalized_name_pairs_n':len(counts),'repeated_pairs_n':sum(n>1 for n in counts.values()),'rows_in_repeated_pairs_n':sum(n for n in counts.values() if n>1),'rows_by_source_region':dict(sorted(collections.Counter(r['region_source'] for r in rows).items())),'geocodes_or_districts_available':False,'observed_network_or_opening_dates':False}
 args.summary_output.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 if args.axis is None:
  print(json.dumps(summary,ensure_ascii=False,indent=2));return
 import pandas as pd
 axis=pd.read_parquet(args.axis);axis['norm_name']=axis.name_2021.map(norm)
 all_links=[];summaries=[]
 for source_reg,reg in PILOTS.items():
  candidates=axis.loc[axis.region_2021.eq(reg)];grouped={k:g for k,g in candidates.groupby('norm_name')}
  selected=[r for r in rows if r['region_source']==source_reg];links=[]
  for row in selected:
   g=grouped.get(norm(row['name_source']));n=0 if g is None else len(g);repeats=counts[(source_reg,norm(row['name_source']))]
   link={**row,'region_base':reg,'base_candidates_n':n,'same_source_pair_rows_n':repeats,'link_status':'source_name_repeated' if repeats>1 else 'unmatched_exact_name' if n==0 else 'ambiguous_base_name' if n>1 else 'candidate_unique_region_and_exact_name'}
   if link['link_status']=='candidate_unique_region_and_exact_name':
    q=g.iloc[0];link.update(source_record_id_2021=q.source_record_id_2021,name_2021=q.name_2021,type_2021=q.type_2021,district_2021=q.district_2021,population_2021=float(q.population_2021))
   links.append(link)
  accepted=[r for r in links if r['link_status']=='candidate_unique_region_and_exact_name'];pops=[r['population_2021'] for r in accepted]
  summaries.append({'region_source':source_reg,'rows_n':len(selected),'link_status_counts':dict(collections.Counter(r['link_status'] for r in links)),'candidate_population2021_sum':sum(pops),'candidate_population_min':min(pops) if pops else None,'candidate_population_max':max(pops) if pops else None,'candidates_below1000_n':sum(x<1000 for x in pops),'candidates_above3500_n':sum(x>3500 for x in pops),'candidates_zero_population_n':sum(x==0 for x in pops)})
  all_links.extend(links)
 with (d/'eligibility_pilot_links.csv').open('w',newline='') as f:
  wr=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in all_links for k in r)));wr.writeheader();wr.writerows(all_links)
 out={'snapshot':'2022-10-22T00:14:16Z','pdf_sha256':PDF_SHA,'list_rows_n':len(rows),'distinct_literal_region_labels_n':len(set(r['region_source'] for r in rows)),'unique_region_normalized_name_pairs_n':len(counts),'repeated_pairs_n':sum(n>1 for n in counts.values()),'rows_in_repeated_pairs_n':sum(n for n in counts.values() if n>1),'source_rows_without_district_or_geocode':True,'pilot_linkage_method':'Region label mapped explicitly; case/yo/space-normalized full settlement name; unique in base and unique in source only. No nearest or fuzzy matches. Name-only matches are candidates, not independently confirmed identities.','population_source':'fixed census2021, not Ozon assignment running variable or population2022','axis_sha256':hashlib.sha256(args.axis.read_bytes()).hexdigest(),'pilots':summaries,'meaning':'dated tariff eligibility list, not openings or operated points'}
 (d/'eligibility_pilot_summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
