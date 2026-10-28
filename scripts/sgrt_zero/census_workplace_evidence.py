#!/usr/bin/env python3
"""Extract observed census workplace-location counts, NOT origin-destination flows.

Inputs are archived public Jina text renderings of official Rosstat spreadsheets/PDF.
No inferred rural settlement-to-NP joins, no replacement of suppressed K with zero.
Run with --input-dir extracted_raw_directory --output-dir output_directory.
Optional --population-reference adds exact unique Buryatia urban NP joins.
"""
from pathlib import Path
import re, json, csv, argparse, hashlib


def observed_count(token):
 """A dash is published zero; confidential K and absent cells are unknown."""
 if token is None or token in {'K', 'К'}:return None
 if token == '-':return 0
 if not re.fullmatch(r'\d[\d,]*',token):raise ValueError(f'Unrecognized count token: {token!r}')
 return int(token.replace(',',''))


def regional_geography(name):
 """Published administrative units overlap; no count-based geography guessing."""
 geography_type='federal_district' if 'федеральный округ' in name else 'subject_remainder_without_autonomous_okrug' if 'без автономн' in name else 'federal_subject'
 overlap=('федеральный округ' in name or name in ['Архангельская область','Ненецкий автономный округ','Тюменская область','Ханты-Мансийский автономный округ – Югра','Ямало-Ненецкий автономный округ'])
 return geography_type,overlap


def outside_np_components(all_employed,same_np,same_region,other_region,abroad,unknown_territory,outside_np):
 """Table12 may establish outsideNP even when destination subject is unknown."""
 values=[all_employed,same_np,same_region,other_region,abroad,unknown_territory,outside_np]
 if any(v is None for v in values):raise ValueError('Cannot derive exact outside shares from missing counts')
 if any(v<0 for v in values):raise ValueError('Counts must be nonnegative')
 if same_np>same_region:raise ValueError('OwnNP must be part of own subject')
 if same_region+other_region+abroad+unknown_territory!=all_employed:raise ValueError('Workplace subject categories do not exhaust denominator')
 known_outside=same_region-same_np+other_region+abroad
 if not known_outside<=outside_np<=known_outside+unknown_territory:raise ValueError('OutsideNP contradicts known or unknown workplace categories')
 return {'same_subject_other_np':same_region-same_np,'outside_np_with_unknown_territory':outside_np-known_outside,'unresolved_np_location':all_employed-same_np-outside_np}

def parse_regional(root,name,width):
 text=(root/name).read_text(); text=text.replace('**Республика Северная Осетия – Алания****270,511','**Республика Северная Осетия – Алания**\n**Городское и сельское население****270,511'); ls=[]; pending=''
 for line in text.splitlines():
  if pending:
   pending+=' '+line.strip()
   if '**' in line:ls.append(pending);pending=''
  elif line.startswith('**') and line.count('*')==2:pending=line
  else:ls.append(line)
 region=None; out={}
 for i,l in enumerate(ls):
  clean=re.sub(r'\s+',' ',l.replace('*',' ')).strip()
  if l.startswith('**') and not re.search(r'\d',l) and clean and not any(s in clean for s in ['население','занятые','ежедневно','раз в','Указавшие','работающие','указавшие','том числе','и реже','в возрасте','владельцы','индивидуальные','самозанятые','помогающие']):region=clean
  for cat in ['Городское и сельское население','Городское население','Сельское население']:
   if clean.startswith(cat) and re.search(r'\d',clean):
    vals=[int(x.replace(',','')) for x in re.findall(r'\d[\d,]*',clean)]
    if len(vals)!=width:raise ValueError((i,vals))
    out[(region,cat)]={'values':vals,'line':i+1}
    if width==10:
     for x in ls[i+1:i+8]:
      for key,prefix in [('same_region','своего субъекта'),('same_np','из них на территории своего населенного пункта'),('other_region','другого субъекта'),('abroad','на территории иностранного'),('unknown_territory','не указавшие территорию')]:
       if x.startswith(prefix):
        tokens=re.findall(r'\d[\d,]*|[KК]|-',x[len(prefix):])
        out[(region,cat)][key]=observed_count(tokens[0] if tokens else None)
 return out

def extract_2021(root):
 a=parse_regional(root,'2021_table10.md',10);b=parse_regional(root,'2021_table12.md',8);rows=[]
 for k,x in a.items():
  if k not in b:continue
  y=b[k];v=x['values'];w=y['values'];r={'region':k[0],'population_category':k[1],'census_year':2021,'employed_age15plus':v[0],**{z:x[z] for z in ['same_np','same_region','other_region','abroad','unknown_territory']},'outside_np':w[0],'outside_daily':w[2],'outside_several_week':w[3],'outside_several_month':w[4],'outside_month_or_less':w[5],'outside_remote':w[6],'outside_frequency_unspecified':w[7],'table10_normalized_line':x['line'],'table12_normalized_line':y['line']}
  r.update(outside_np_components(v[0],x['same_np'],x['same_region'],x['other_region'],x['abroad'],x['unknown_territory'],w[0]))
  r['outside_fraction_all_employed']=w[0]/v[0];r['daily_outside_fraction_all_employed']=w[2]/v[0];r['outside_fraction_known_np_location']=w[0]/(w[0]+x['same_np']);r['outside_fraction_upper_if_all_unresolved_outside']=(w[0]+r['unresolved_np_location'])/v[0];rows.append(r)
 with (root/'regional_commuting_vpn2020_2021.csv').open('w') as f:
  wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
 (root/'regional_commuting_vpn2020_2021.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
 return rows

def extract_2010(root):
 s=(root/'2010_buryatia_table9.md').read_text();rows=[];unresolved=[]
 pat=re.compile(r'^([^\n]*?)Городское и сельское население\s+([^\n]+)',re.M)
 for m in pat.finditer(s):
  name=m.group(1).strip();total=m.group(2).split()[0]
  if not name:unresolved.append({'position':m.start(),'preceding_text':s[max(0,m.start()-750):m.start()]});continue
  block=s[m.end():];n=re.search(r'(?:Городское население|Сельское население|Городское и сельское население)',block);block=block[:n.start()] if n else block
  d={'source_year':2010,'geography_label':name,'geography_type':'settlement_np' if name.startswith(('г.','пгт ')) else 'urban_okrug_and_np' if '– г.' in name else 'municipality','employed_age15_72_raw':total,'source_char_position':m.start()}
  for key,prefix in [('same_np','из них на территории своего населенного пункта'),('same_subject','на территории своего субъекта'),('other_subject','на территории другого субъекта'),('abroad','на территории других стран'),('unknown_workplace','без указания территории нахождения работы')]:
   mm=re.search(re.escape(prefix)+r'\s+([\dKК\-]+)',block);d[key+'_raw']=mm.group(1) if mm else None
  for key in ['employed_age15_72','same_np','same_subject','other_subject','abroad','unknown_workplace']:
   raw=d[key+'_raw'];d[key]=observed_count(raw)
  if all(d[k] is not None for k in ['employed_age15_72','same_np','unknown_workplace']):
   d['outside_np_known']=d['employed_age15_72']-d['same_np']-d['unknown_workplace'];assert d['outside_np_known']>=0,d
   d['outside_np_fraction_all_employed']=d['outside_np_known']/d['employed_age15_72'] if d['employed_age15_72'] else None
   d['outside_np_fraction_upper_unknown_all_outside']=(d['employed_age15_72']-d['same_np'])/d['employed_age15_72'] if d['employed_age15_72'] else None
  rows.append(d)
 (root/'buryatia_commuting_vpn2010.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));(root/'buryatia_unresolved_heading_vpn2010.json').write_text(json.dumps(unresolved,ensure_ascii=False,indent=2))
 keys=list(dict.fromkeys(k for r in rows for k in r))
 with (root/'buryatia_commuting_vpn2010.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
 return rows


def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--input-dir',type=Path,default=Path(__file__).resolve().parents[2]/'references/primary/census_workplace_20261027')
 ap.add_argument('--output-dir',type=Path,required=True)
 ap.add_argument('--population-reference',type=Path)
 ap.add_argument('--source-manifest',type=Path,default=Path(__file__).resolve().parents[2]/'references/provenance/census_workplace_20261027.json')
 args=ap.parse_args(); args.output_dir.mkdir(parents=True,exist_ok=True)
 manifest=json.loads(args.source_manifest.read_text())
 for source in manifest['sources']:
  path=args.input_dir/Path(source['source_file']).name
  actual_sha=hashlib.sha256(path.read_bytes()).hexdigest()
  if actual_sha!=source['source_markdown_sha256']:raise ValueError(f'Pinned source SHA256 mismatch: {path.name}')
 import tempfile,shutil
 with tempfile.TemporaryDirectory(prefix='census-workplace-') as tmp:
  root=Path(tmp)
  for n in ['2021_table10.md','2021_table12.md','2010_buryatia_table9.md']:
   shutil.copyfile(args.input_dir/n,root/n)
  regions=extract_2021(root); municipalities=extract_2010(root)
  parent_district=None
  for r in municipalities:
   label=r['geography_label']
   if 'муниципальный район' in label:parent_district=label
   if label.startswith('Городской округ'):parent_district=None
   r['parent_municipal_district_label']=parent_district
   if label=='Республика Бурятия':r['geography_type']='federal_subject'
   elif 'муниципальный район' in label:r['geography_type']='municipal_district'
   elif label.startswith(('Сельское поселение','Городское поселение')):r['geography_type']='municipal_settlement'
   elif label.startswith('Городской округ'):r['geography_type']='urban_okrug_and_np' if '– г.' in label else 'urban_okrug'
   elif not label.startswith(('г.','пгт ')):r['geography_type']='subcity_district_or_unresolved_named_geography'
   r['aggregate_overlap']=r['geography_type']!='settlement_np'
   component_keys=['same_subject','other_subject','abroad','unknown_workplace']
   if all(r[k] is not None for k in component_keys):assert sum(r[k] for k in component_keys)==r['employed_age15_72']

  for r in regions:
   name=r['region']; r['same_subject_other_np']=r['same_region']-r['same_np']
   r['geography_type'],r['aggregate_overlap']=regional_geography(name)
   assert r['same_region']+r['other_region']+r['abroad']+r['unknown_territory']==r['employed_age15plus']
   assert sum(r[k] for k in ['outside_daily','outside_several_week','outside_several_month','outside_month_or_less','outside_remote','outside_frequency_unspecified'])==r['outside_np']
  if args.population_reference:
   import pyarrow.parquet as pq
   base=[r for r in pq.read_table(args.population_reference).to_pylist() if 'бурят' in str(r['region']).lower()]
   for r in municipalities:
    if r['geography_type'] not in ['settlement_np','urban_okrug_and_np']:continue
    name=re.split(r'г\. |пгт ',r['geography_label'])[-1].lower().replace('ё','е')
    matches=[b for b in base if b['name'].lower().replace('ё','е')==name]
    r['population_join_candidate_count']=len(matches)
    if len(matches)==1:
     match=matches[0]
     for key in ['root','source_record_id','source_record_id_2010','population_2010','population_value_quality_2010','lat','lon']:
      r['population_base_'+key]=match[key]
     r['population_join_method']='exact_unique_name_within_Buryatia_urban_NP_only'
     if r['employed_age15_72'] is not None and match['population_2010'] is not None:assert r['employed_age15_72']<=match['population_2010']
  for filename,data in [('regional_commuting_vpn2020_2021',regions),('buryatia_commuting_vpn2010',municipalities)]:
   (args.output_dir/(filename+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
   keys=list(dict.fromkeys(k for row in data for k in row))
   with (args.output_dir/(filename+'.csv')).open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=keys);writer.writeheader();writer.writerows(data)
  shutil.copyfile(root/'buryatia_unresolved_heading_vpn2010.json',args.output_dir/'buryatia_unresolved_heading_vpn2010.json')
 print(json.dumps({'regional_rows':len(regions),'geography_labels':len(set(r['region'] for r in regions)),'municipality_and_urban_rows2010':len(municipalities),'municipality_exact_outside2010':sum('outside_np_known'in r for r in municipalities),'np_joins2010':sum(r.get('population_join_candidate_count')==1 for r in municipalities)},ensure_ascii=False))

if __name__=='__main__':main()
