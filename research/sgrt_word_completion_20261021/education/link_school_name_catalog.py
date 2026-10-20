#!/usr/bin/env python3
"""Bind explicit settlement names in the 2022 school-name catalog, preserving legal/name evidence."""
from pathlib import Path
import re,json
import pandas as pd
ROOT=Path(__file__).resolve().parent
def norm(s):return re.sub(r'[^а-яa-z0-9]+',' ',str(s).lower().replace('ё','е')).strip()
def stem(s):
 s=norm(s)
 return s[:-2] if s.endswith(('ая','ой','ия','ий','ый','ое')) else s
def run():
 axis=pd.read_parquet(ROOT.parent/'axis/full_settlement_axis.parquet');catalog=pd.read_parquet(ROOT/'school_website_catalog_2022.parquet')
 ref=axis[axis.population_2021.notna()].copy();ref['_name']=ref.name.map(norm)
 lookup={k:g for k,g in ref.groupby('_name')};regions={str(x):stem(x) for x in ref.region.dropna().unique()}
 maxwords=max(len(x.split()) for x in lookup)
 prefixes={'село','села','селе','с','деревня','деревни','деревне','д','поселок','поселка','поселке','п','пос','станица','станицы','станице','ст','хутор','хутора','х','аул','аула','город','города','г'}
 rows=[]
 for _,r in catalog.iterrows():
  text=norm(r.school_name);tokens=text.split();found=set()
  for i,t in enumerate(tokens):
   if t not in prefixes:continue
   for j in range(1,min(maxwords,len(tokens)-i-1)+1):
    x=' '.join(tokens[i+1:i+1+j])
    if x in lookup:found.add(x)
  candidates=[]
  for n in sorted(found):
   c=lookup[n]
   # Explicit region is mandatory; global name uniqueness is insufficient.
   c=c[c.region.map(lambda z:bool(regions.get(str(z))) and regions[str(z)] in text)]
   if len(c)>1:
    # District/municipal contextual names supplement the explicit region; never use population ranking.
    def context(x):
     vals=[x.get('district_raw_2002'),x.get('municipality_upper_2021')]
     for v in vals:
      words=[w for w in norm(v).split() if w not in {'район','муниципальный','округ','городской','none','nan'} and len(w)>4]
      if words and stem(words[0]) in text:return True
     return False
    c=c[c.apply(context,axis=1)]
   candidates.extend(c.id.tolist())
  candidates=sorted(set(candidates));row=r.to_dict();row.update(candidate_uids_json=json.dumps(candidates,ensure_ascii=False),explicit_place_names='|'.join(sorted(found)),settlement_uid=candidates[0] if len(candidates)==1 else None,link_status='explicit_settlement_type_name_and_region_unique' if len(candidates)==1 else 'ambiguous_named_institution' if candidates else 'not_linked_from_explicit_context',not_physical_site_coordinate=True)
  rows.append(row)
 d=pd.DataFrame(rows);d.to_parquet(ROOT/'school_website_named_settlements_2022.parquet',index=False)
 linked=d[d.settlement_uid.notna()];receipt={'source_rows':len(d),'linked_name_rows':len(linked),'linked_settlements':linked.settlement_uid.nunique(),'ambiguous':int(d.link_status.eq('ambiguous_named_institution').sum()),'meaning':'dated school-name/website catalog with explicit settlement context; not geocoded campuses nor source of observed trips','rule':'Explicit locality type and literal name, mandatory region text, unique after optional district context; never world/name-only uniqueness'}
 (ROOT/'school_name_linkage_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(receipt)
if __name__=='__main__':run()
