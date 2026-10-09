from pathlib import Path
import json,csv,gzip,hashlib,re,xlrd,pandas as pd
ROOT=Path('/workspace/russian-settlements-research');OUT=Path(__file__).parent;SRC=ROOT/'research_rebuild/evidence/over500_moscow_20261009/batch4_ownpoint_followup';pins={}
def pin(p):
 p=Path(p);pins[str(p)]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size};return p
proposal=pd.read_csv(pin(SRC/'component_partition_correction.csv'),dtype=str,keep_default_na=False);assert len(proposal)==1
proof=json.loads(pin(SRC/'Ivanovskoye_false_type_alias_sourceproof.json').read_text());assert pins[str(SRC/'Ivanovskoye_false_type_alias_sourceproof.json')]['sha256']==proposal.iloc[0].source_binding_proof_sha256
sources={}
raw2=pin(proof['source2002_path']);raw10=pin(proof['source2010_path']);assert pins[str(raw2)]['sha256']==proof['source2002_sha256'];assert pins[str(raw10)]['sha256']==proof['source2010_sha256']
s2=xlrd.open_workbook(str(raw2)).sheet_by_name('Sheet1');s10=xlrd.open_workbook(str(raw10)).sheet_by_name('Data Sheet')
for n,kind,pop,sub in [(270,'село',784,'Ченецкий'),(130,'деревня',15,'Кармановский')]:
 row=s2.row_values(n-1);assert row==proof['literal2002_rows'][str(n)];assert row[1].strip()==kind+' Ивановское'and int(row[2])==pop
 head=next((i+1,s2.row_values(i))for i in range(n-2,-1,-1)if 'сельский округ'in str(s2.cell_value(i,1)));assert sub in head[1][1]
 sources['2002:'+str(n)]=dict(source_sheet='Sheet1',source_physical_row=n,literal_name=row[1],population_raw=row[2],literal_subcounty_heading_row=head[0],literal_subcounty_heading=head[1][1])
for n,kind,pop in [(8075,'село',531),(8169,'деревня',16)]:
 row=s10.row_values(n-1);assert row==proof['literal2010_rows'][str(n)];assert row[3]==kind+' Ивановское'and int(row[4])==pop
 sources['2010:'+str(n)]=dict(source_sheet='Data Sheet',source_physical_row=n,printed_serial_number=row[0],literal_name=row[3],population_raw=row[4],literal_region=row[2],subcounty_not_printed_in_leaf_row=True,nearby_context=[dict(row=k,cells=s10.row_values(k-1)[:5])for k in range(n-4,n+3)])
articlepath=pin(proof['own_articles_path']);assert pins[str(articlepath)]['sha256']==proof['own_articles_sha256'];q=json.load(gzip.open(articlepath,'rt'))['query'];articles={p['title']:p for p in q['pages'].values()if'missing'not in p};a={}
for key,kind,sub in [('selo_own_article','село','Ченецкого'),('village_own_article','деревня','Кармановского')]:
 supplied=proof[key];actual=articles[supplied['title']];assert actual==supplied
 rv=actual['revisions'][0];text=rv['slots']['main']['*'];assert re.search(r'\|\s*статус\s*=\s*'+kind,text,re.I)and sub in text
 a[key]=dict(pageid=actual['pageid'],title=actual['title'],revision=rv['revid'],kind=kind,subcounty_literal_witness=[l for l in text.splitlines()if sub in l],own_point=actual['coordinates'][0])
# Verify exact committed baseline71 component membership, independently of the Moscow helper parquet.
SNAP=ROOT/'publication/stage71';m=json.loads(pin(SNAP/'release-assets-manifest.json').read_text());entries={x['name']:x for x in m['assets']}
cp=pin(SNAP/'applied_component_snapshot.csv.gz');op=pin(SNAP/'applied_state_observations.parquet')
for p in [cp,op]:assert pins[str(p)]['sha256']==entries[p.name]['sha256']and p.stat().st_size==entries[p.name]['bytes']
c=pd.read_csv(cp,dtype=str,keep_default_na=False);uids=json.loads(proposal.iloc[0].expected_before_members_JSON);roots=set(c[c.source_record_id.isin(uids)].root);assert len(roots)==1;root=roots.pop();members=c[c.root==root].source_record_id.tolist();assert set(members)==set(uids)
true2010=proof['true_selo2010_UID'];truevillage2002=proof['true_village2002_UID'];true_root=c[c.source_record_id==true2010].iloc[0].root;true_members=c[c.root==true_root].source_record_id.tolist();assert true2010 not in members
obs=pd.read_parquet(op,columns=['source_record_id','census_year','type_norm','population']);observed=obs[obs.source_record_id.isin(set(uids)|{true2010,truevillage2002})].to_dict('records');assert len(observed)==5
expected_after=json.loads(proposal.iloc[0].after_partition_JSON);assert len(expected_after)==2 and set(sum(expected_after,[]))==set(members)
wrong=next(v for v in members if v.endswith(':8169'));assert [wrong]in expected_after;assert true2010 not in sum(expected_after,[])
origin=pin(ROOT/'research_rebuild/evidence/current_component_name_alias_mass_20261008/accepted_identity_edge_delta.csv.gz');edges=pd.read_csv(origin,dtype=str);false=edges[(edges.from_source_record_id==wrong)&(edges.to_source_record_id.str.endswith(':270'))];assert len(false)==1
receipt=dict(status='independent_exact_Ivanovskoye_partition_verified',review_scope='One concrete baseline71 false-type-alias component only; no general audit or admissions',source_pins=pins,native_rows_replayed=sources,qualified_own_article_replays=a,baseline71_exact_component_root=root,baseline71_exact_component_members=sorted(members),baseline71_observation_values=observed,true_selo2010_existing_component_members=sorted(true_members),proposed_after_partition=expected_after,actual_false_baseline_edge=false.to_dict('records'),checks=dict(all_raw_population_values_preserved=True,raw2010_selo_population_531_not_16=True,village16_is_distinct_physical_object=True,two_original2002_types_and_subcounties_distinct=True,two_qualified_articles_distinct_own_objects=True,baseline_exact_three_members_verified_from_hash_pinned_committed_snapshot=True,partition_only_removes_wrong2010_village_from_selo_component=True,true2010_selo531_not_in_wrong_component_and_not_replaced=True,ordinary_new_identity_admission_made=False,coordinate_admission_made=False),limits=['2010 source workbook leaf rows print type/name/region/population, not original rural district; subcounty binding comes from independently replayed 2002 headings and qualified article history.','The partition operation alone preserves 2002selo→2021selo and isolates2010village16. It does not itself attach2010selo531; any typed same-place link for that actual independent observation is a separate admission.','No population equivalence, count substitution, boundary comparability, or historical coordinate measurement is claimed.'])
(OUT/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(status=receipt['status'],baseline_members=members,true_selo2010_existing_component_members=true_members,source_rows=list(sources),checks=receipt['checks']),ensure_ascii=False,indent=2))
