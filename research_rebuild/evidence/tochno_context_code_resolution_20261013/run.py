from pathlib import Path
import duckdb,json,hashlib,csv,re
from urllib.request import urlopen
H=Path(__file__).resolve().parent
SOURCE='/workspace/scratch/tochno-enrichment-20261013/raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'
BRIDGE='/workspace/scratch/tochno-np-attach-20261013/native_np_municipality_bridge.csv.gz'
DOC='/workspace/shared/tochno-20261013/bdmo_description.txt'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
pins={p:sha(p) for p in [SOURCE,BRIDGE,DOC]}
# Normative code formula, published as an explicit description of OK 033-2013.
u='https://classifikators.ru/oktmo#info';html=urlopen(u,timeout=20).read().decode();text=' '.join(re.sub('<[^>]+>',' ',html).split());start=text.index('С учетом разделов код ОКТМО имеет вид:');snippet=text[start:start+650]
assert 'муниципальные образования (8 знаков)' in snippet and 'населенные пункты (11 знаков)' in snippet
(H/'code_structure_excerpt.txt').write_text(snippet+'\n',encoding='utf-8')
c=duckdb.connect();c.execute('set threads=1')
c.execute("create temp table s as select file_row_number+1 as row1,object_level,object_name,oktmo,region,mun_upper,mun_lower,population from read_parquet(?,file_row_number=true)",[SOURCE])
c.execute("create temp table b as select * from read_csv(?,header=true,all_varchar=true,delim=',',quote='\"',escape='\"')",[BRIDGE])
c.execute("""create temp table targets as select b.source_record_id,b.root,b.municipality_role,b.context_status as prior_context_status,b.np_frozen_row_1based::bigint np_frozen_row_1based,s.object_name np_object_name,s.region region_raw,s.oktmo np_oktmo_raw,s.mun_upper np_mun_upper_raw,s.mun_lower np_mun_lower_raw,s.population np_population,case when regexp_full_match(s.oktmo,'[0-9]{10,11}') then left(lpad(s.oktmo,11,'0'),8) when regexp_full_match(s.oktmo,'[0-9]{8}') then s.oktmo else null end municipality_prefix8,case when regexp_full_match(s.oktmo,'[0-9]{10,11}') then 'documented_np11_prefix8_existing_municipality' when regexp_full_match(s.oktmo,'[0-9]{8}') then 'exact_existing_source_code8_no_hierarchy_derivation' else 'no_supported_code_structure' end code_basis from b join s on s.row1=b.np_frozen_row_1based::bigint where s.object_level='Населенный пункт' and ((b.municipality_role='upper' and b.context_status in ('ambiguous_source_context','no_exact_source_municipality')) or (b.municipality_role='lower' and b.context_status='ambiguous_source_context'))""")
c.execute("""create temp table m as select *,lpad(oktmo,8,'0') municipality_code8,count(*) over(partition by region,object_level,lpad(oktmo,8,'0')) as same_region_level_code_rows from s where object_level in ('Муниципалитет верхнего уровня','Муниципалитет нижнего уровня') and regexp_full_match(oktmo,'[0-9]{7,8}')""")
c.execute("""create temp table hits as select t.*,m.row1 municipality_frozen_row_1based,m.object_level municipality_object_level,m.object_name municipality_label_raw,m.oktmo municipality_oktmo_raw,m.municipality_code8 municipality_oktmo_code8,m.same_region_level_code_rows, t.np_mun_upper_raw=m.object_name upper_name_matches,t.np_mun_lower_raw=m.object_name lower_name_matches from targets t join m on m.region=t.region_raw and m.municipality_code8=t.municipality_prefix8 and m.object_level=case when t.municipality_role='upper' then 'Муниципалитет верхнего уровня' else 'Муниципалитет нижнего уровня' end where (m.same_region_level_code_rows=1 or t.municipality_role='lower') and ((t.municipality_role='upper' and (t.prior_context_status='no_exact_source_municipality' or m.object_name=t.np_mun_upper_raw)) or (t.municipality_role='lower' and m.object_name=t.np_mun_lower_raw and m.mun_upper=t.np_mun_upper_raw))""")
# Only one code-qualified hit can be admitted; no alternate prefix/level inference.
c.execute("""create temp table accepted as select *,(select object_name from s where object_level='Страна') country_raw,'RU_OKTMO' code_namespace,2021 source_census_year,'v20251217' source_dataset_version,true administrative_effective_date_unknown,false historical_membership_asserted,'checked_existing_source_context_code8' context_status from hits qualify count(*) over(partition by source_record_id,municipality_role)=1""")
c.execute("copy accepted to ? (header,delimiter ',')",[str(H/'accepted_context_delta.csv')])
c.execute("copy (select t.*,'held_no_unique_qualified_existing_source_code' reason from targets t anti join accepted a using(source_record_id,municipality_role)) to ? (header,delimiter ',')",[str(H/'held_context_rows.csv')])
counts=c.execute('select municipality_role,count(*),sum(np_population) from accepted group by 1 order by 1').fetchall();targets=c.execute('select count(*),sum(np_population) from targets').fetchone();held=c.execute('select count(*) from targets t anti join accepted a using(source_record_id,municipality_role)').fetchone()[0]
receipt={'inputs':pins,'code_structure_document':{'url':u,'fetched_html_sha256':hashlib.sha256(html.encode()).hexdigest(),'excerpt_path':str(H/'code_structure_excerpt.txt'),'status':'description_of_OK_033_2013_on_nonofficial_classifier_mirror','bdmo_primary_document':DOC,'bdmo_primary_statement':'Код ОКТМО муниципального образования (первые 8 цифр), attribute10'},'target_rows':targets[0],'target_record_population_sum':targets[1],'accepted_by_role':[{'role':a,'records':b,'population':z} for a,b,z in counts],'held_rows':held,'semantics':'Source administrative context only; no population/coordinate or cross-census identity admission; no dated membership claim; no derivation of upper first5 codes; no invented lower tier','outputs':{p.name:{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)} for p in [H/'accepted_context_delta.csv',H/'held_context_rows.csv',H/'code_structure_excerpt.txt']}}
(H/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(receipt,ensure_ascii=False))
