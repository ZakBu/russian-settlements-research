from pathlib import Path
import json,gzip,re,hashlib,pandas as pd
D=Path(__file__).parent;E=D.parent;pages={}
for f in [E/'moscow_large_residual_actionable_20261008/municipal_pages.json.gz',D/'missing_municipal_pages.json.gz',D/'klenovskoye_title_resolution_pages.json.gz']:
 for p in json.load(gzip.open(f,'rt'))['query']['pages'].values():
  if p.get('pageprops',{}).get('wikibase_item'):pages[p['pageprops']['wikibase_item']]=p
m=pd.read_csv(D/'candidate_native_scope_constituents.csv',keep_default_na=False);o=pd.read_csv(D/'candidate_scope_observations.csv');proof=[]
def norm(s):return re.sub(r'[^а-я0-9]','',s.lower().replace('ё','е'))
for scope,g in m[m.year.eq(2010)].groupby('scope_id'):
 q=o[o.scope_id.eq(scope)].municipal_entity.iloc[0];p=pages[q];t=p['revisions'][0]['slots']['main']['*'];section=re.search(r'^== (?:Насел[её]нные пункты|Состав поселения) ==\s*([\s\S]*?)(?=^== |\Z)',t,re.M).group(1);literal={}
 for z in re.finditer(r'^\s*\|[\s%|]*\[\[([^\]]+)\]\][^|\n]*\|\s*([^|]+)\|',section,re.M):
  a,_,b=z.group(1).partition('|');name=b or a;typ=z.group(2).strip().split(',')[0].split('+')[0].strip();literal[(norm(name),norm(typ))]=(name,typ)
 exact=set()
 for r in g.itertuples():
  label=r.raw_label.strip();typ,label=re.match(r'^(деревня|пос[её]лок|село|хутор)\s+(.+)$',label).groups();key=(norm(label),norm(typ))
  if key not in literal and label.startswith('станции '):key=(norm(label),norm('посёлок при станции'))
  if key not in literal:
   assert scope=='moscow_sourceyear_voskresenskoye' and r.raw_row_1based==10435 and norm(label)==norm('подсобного хозяйства Воскресенское')
   rule='Actualcomplete2010sourceyearlegacyproperNP;article separatelyexplicitlylistsпосёлокВоскресенское underofficial2012addressingappendix353-ПП,notmodernninevillagelegalroster'
   name,lt='посёлок Воскресенское','raw complete2010legacyproperNP'
  else:
   assert key not in exact;exact.add(key);name,lt=literal[key];rule='Exactliteraltypedmunicipalmember; e/yo,quotes,whitespace normalization only'
  proof.append(dict(scope_id=scope,year=2010,raw_row_1based=r.raw_row_1based,raw_label=r.raw_label,published_member_name=name,published_member_type=lt,article_revision=p['revisions'][0]['revid'],binding_rule=rule,source_record_id=r.source_record_id,raw_count_unknown=r.native_population_quality=='raw_count_blank_unknown_not_zero'))
 assert exact==set(literal),(scope,set(literal)-exact,exact-set(literal))
 assert len(g)==len(literal)+(scope=='moscow_sourceyear_voskresenskoye')
# Reopen exact complete2002named childrosters from own parent through next literalparent, including actual zeros.
import xlrd
s=xlrd.open_workbook('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls').sheet_by_index(0);closures=[]
for scope,g in m[m.year.eq(2002)].groupby('scope_id'):
 a=int(g.raw_row_1based.min())-1;b=int(g.raw_row_1based.max());rows=set(g.raw_row_1based.astype(int));atoms=set()
 for n in range(a+1,b+1):
  label=str(s.cell_value(n-1,1));count=s.cell_value(n-1,2)
  if re.match(r'^\s*(?:пос[её]лок|деревня|село|хутор|хутора)\s+',label,re.I):atoms.add(n);assert count!=''
 assert atoms==rows,(scope,atoms-rows,rows-atoms)
 assert float(s.cell_value(a-1,2))==g.raw_population.astype(float).sum()
 assert 'сельский округ' in str(s.cell_value(a-1,1)) and 'сельский округ' in str(s.cell_value(b,1))
 closures.append(dict(scope_id=scope,year=2002,printed_parent_row_1based=a,literal_parent_label=s.cell_value(a-1,1),whole_parent_count=float(s.cell_value(a-1,2)),all_original_named_atomic_rows_equal_native_rows=True,raw_atomic_count=len(rows),next_parent_row_1based=b+1,literal_next_parent_label=s.cell_value(b,1),zero_count_actual_raw_rows=int(g.raw_population.astype(float).eq(0).sum()),raw_unknown_count_imputed=False))
pd.DataFrame(proof).to_csv(D/'exact_literal2010_roster_to_raw_bindings.csv',index=False);pd.DataFrame(closures).to_csv(D/'literal2002_parent_nextparent_closures.csv',index=False)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();r=json.loads((D/'candidate_receipt.json').read_text());r.update(complete2002_literal_parent_nextparent_verified=True,complete2010_literal_typed_rosters_verified=True,legacy2010_properNP_in_voskresenskoye_preserved=True,source_counts_quality_unmodified=True,candidate_folder_frozen=True);r['outputs']={p.name:sha(p) for p in D.iterdir() if p.suffix=='.csv' or p.name.endswith('.csv.gz')};r['code_sha256']={p.name:sha(p) for p in D.glob('*.py')};(D/'candidate_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print('verified',len(proof),len(closures))
