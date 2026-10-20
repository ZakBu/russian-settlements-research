#!/usr/bin/env python3
"""Current legal municipal designation; never equate it to physical industrial decline."""
from pathlib import Path
import re,json,hashlib
import pandas as pd
from lxml import html
H=Path(__file__).resolve().parent
norm=lambda x:re.sub(r'[^а-яa-z0-9]+',' ',str(x).lower().replace('ё','е')).strip()
def reg(x):
 x=norm(x).replace('кемеровская область кузбасс','кемеровская область')
 return norm(re.sub(r'республика|область|край|автономный округ|автономная|ао','',x))
a=pd.read_parquet(H.parent/'axis/full_settlement_axis.parquet');a['_n']=a.name.map(norm);a['_r']=a.region.map(reg)
p=H/'sources/monotowns2026_bazanpa.html';table=html.fromstring(p.read_text()).xpath('//table')[1]
rows=[];category=None
for tr in table.xpath('.//tr'):
 x=[' '.join(' '.join(t.itertext()).split()) for t in tr.xpath('./td|./th')]
 if len(x)==1 and x[0].startswith('Категория'):category=int(re.search(r'Категория (\d)',x[0])[1])
 if len(x)!=3 or not re.fullmatch(r'\d+\.',x[0]):continue
 ix,label,region=x;nn=' '+norm(label)+' ';rr=reg(region)
 # A settlement must be literally named in the legal designation, in its region.
 # Adjectival district names are not mechanically converted to urban centers.
 c=a[a['_r'].eq(rr)&a['_n'].map(lambda n:bool(n) and (' '+n+' ') in nn and n not in (' '+norm(region)+' ') and n not in {'город','поселок','район','городское','сельское'})]
 if len(c):
  # Legal municipal labels can also contain names of villages. Historical registry
  # and urban source type disambiguate homonyms without choosing the largest town.
  urban=c[c.type.isin(['город','пгт','рабочий посёлок','посёлок городского типа'])]
  if len(urban):c=urban
  longest=c['_n'].str.len().max();c=c[c['_n'].str.len().eq(longest)]
  if c.population_2021.notna().any():c=c[c.population_2021.notna()]
 accepted=c.id.iloc[0] if len(c)==1 else None
 rows.append(dict(registry_row=int(ix[:-1]),municipal_designation=label,region=region,category2026=category,linked_id=accepted,candidate_count=len(c),link_status='literal_settlement_name_region_unique_municipal_label' if accepted else 'unresolved_adjectival_municipality_or_homonym_or_axis_scope',legal_entity_is_municipality=True,settlement_link_is_named_context=True,source_document_date='2026-03-11',source_amendment_date='2026-04-13',effective_date='2026-06-01',snapshot_date='2026-10-21',source_url='https://bazanpa.ru/pravitelstvo-rf-rasporiazhenie-n469-r-ot11032026-h7045605/',primary_publication_retrieval='HTTP503_not_retrieved',source_class='reproduced_official_legal_text'))
d=pd.DataFrame(rows);assert d.registry_row.tolist()==list(range(1,265));assert d.category2026.value_counts().to_dict()=={2:149,3:63,1:52}
d.to_csv(H/'current_monotowns2026.csv',index=False)
assert not d.loc[d.linked_id.notna(),'linked_id'].duplicated().any(), 'A named center unexpectedly represents multiple legal rows'
f=pd.read_parquet(H/'settlement_features.parquet');by=d[d.linked_id.notna()].set_index('linked_id')
f['current_monotown_category2026']=pd.array(f.id.map(by.category2026),dtype='Int8')
f['current_monotown_municipal_designation_evidence']=pd.array(f.current_monotown_category2026.notna().map({True:True,False:pd.NA}),dtype='boolean')
f['official_mono_difficulty_category1_evidence']=pd.array(f.current_monotown_category2026.eq(1).where(f.current_monotown_category2026.notna(),pd.NA),dtype='boolean')
f['monotown_current_legal_effective_date']=f.current_monotown_category2026.map(lambda x:'2026-06-01' if pd.notna(x) else None)
f.to_parquet(H/'settlement_features.parquet',index=False)
r={'rows':len(d),'category_counts':d.category2026.value_counts().to_dict(),'literal_named_settlement_links':int(d.linked_id.notna().sum()),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source_class':'reproduced_official_legal_text; primary publication retrieval failed HTTP503','semantics':'Municipal legal designation effective2026, not physical industrial decline during2002–2021. Unresolved adjectival names retained without invented centers.'}
(H/'current_monotowns_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(r)
