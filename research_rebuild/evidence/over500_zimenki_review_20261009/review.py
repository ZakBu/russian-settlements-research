from pathlib import Path
import pandas as pd,json,gzip,hashlib,xlrd
R=Path('/workspace/russian-settlements-research');P=R/'research_rebuild/evidence/over500_north_remaining_points_20261009';O=Path(__file__).parent;pins={}
def pin(p):
 p=Path(p);pins[str(p)]=dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size);return p
proposal=pd.read_csv(pin(P/'component_partition_correction_07.csv')).iloc[0];f=pin(P/'Zimenki_false_homonym_sourceproof_07.json.gz');assert pins[str(f)]['sha256']==proposal.source_binding_proof_sha256;j=json.load(gzip.open(f,'rt'));pin(P/'manifest_07.json');rows={};books={}
for x in [j['native_major2002'],j['native_minor2002'],j['native_major2010']]+j['all_reopened_distinct_native_source_successors']:
 sf=pin(x['source_file']);assert pins[str(sf)]['sha256']==x['source_sha256'];key=(str(sf),x['source_sheet']);s=books.setdefault(key,xlrd.open_workbook(str(sf)).sheet_by_name(x['source_sheet']));n=int(x['source_row']);r=s.row_values(n-1);expected=json.loads(x['raw_row_cells_json']);assert r==expected;rows[x['source_record_id']]=r[:6]
s=books[(j['native_major2002']['source_file'],'11')]
for key,n,name in [('actual_raw_major_parish',3966,'Зименковский'),('actual_raw_minor_parish',4088,'Успенский')]:
 assert s.row_values(n-1)==j[key]['rawcells']and name in s.cell_value(n-1,0)
assert s.cell_value(3966,0).strip()=='село Зименки'and int(s.cell_value(3966,1))==545
assert s.cell_value(4093,0).strip()=='деревня Зименки'and int(s.cell_value(4093,1))==0
# Actual successors same oldmajor parish, independent two-name sourceorder corroboration.
for n in[3968,3969]:assert next(i+1 for i in range(n-2,-1,-1)if'сельсовет'in str(s.cell_value(i,0)))==3966
S=R/'publication/stage71';m=json.loads(pin(S/'release-assets-manifest.json').read_text());assets={x['name']:x for x in m['assets']};cp=pin(S/'applied_component_snapshot.csv.gz');op=pin(S/'applied_state_observations.parquet')
for q in[cp,op]:assert pins[str(q)]['sha256']==assets[q.name]['sha256']
c=pd.read_csv(cp,dtype=str);uids=json.loads(proposal.expected_before_members_JSON);root=c[c.source_record_id==uids[0]].iloc[0].root;members=c[c.root==root].source_record_id.tolist();assert set(members)==set(uids);after=json.loads(proposal.after_partition_JSON);assert after==j['after_partition'];minor=j['native_minor2002']['source_record_id'];assert[minor]in after and set(sum(after,[]))==set(members)
obs=pd.read_parquet(op,columns=['source_record_id','census_year','population','type_norm','okato']);current=obs[obs.source_record_id.eq(j['own_native_current2021']['source_record_id'])].iloc[0];assert current.population==482 and current.type_norm=='деревня'
major=j['native_major2002']['source_record_id'];majorroot=c[c.source_record_id==major].iloc[0].root;majormembers=c[c.root==majorroot].source_record_id.tolist();assert major not in members
for group in after:
 yrs=obs[obs.source_record_id.isin(group)].census_year.tolist();assert len(yrs)==len(set(yrs))
a=j['own_current_article'];af=pin(a['source']);assert pins[str(af)]['sha256']==a['source_sha256'];payload=json.load(gzip.open(af,'rt'));q=payload.get('payload',payload)['query']['pages'];q=list(q.values())if isinstance(q,dict)else q;art=next(x for x in q if x.get('pageid')==a['pageid']);rv=art['revisions'][0];t=rv['slots']['main'].get('content',rv['slots']['main'].get('*'));assert t==a['own_text']and'22437844008'in t and'Шалдежский'in t
r=dict(status='PASS_independent_exact_Zimenki_partition',source_pins=pins,native_rows_replayed=rows,major_parish=j['actual_raw_major_parish'],minor_parish=j['actual_raw_minor_parish'],baseline_exact_members=sorted(members),major2002_existing_members=majormembers,after_partition=after,positive_pair='2010major3224→2021major75861 retained; major2002separate until subsequent reviewed join',qualified_article=dict(title=art['title'],revid=rv['revid'],proper_own_code='22437844008',ownpoint=art.get('coordinates')),checks=dict(published_minor_zero_preserved=True,two_actual_original_parishes_distinct=True,two_distinct_immediate_native_peers_reopened=True,baseline_exact_three_verified=True,no_two_same_year_after_partition=True,reported_selo_to_derevnya_roles_preserved=True),limits=['2010leaf prints no parish; two independent neighbouring own names support oldmajor sourceblock binding.','Actual2021 providerOKATO duplicated wrongminor code is not identity proof; propercode from separately replayed ownarticle retained withoutbackfilling native.','Exact legaltypechange date UNKNOWN; reportedtypes remain unchanged.','Root must assert live ActualStateAPI exactbaseline component before all new edges.','Reviewonly, no admissions or sourcecounts modified.']);(O/'receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(r['status'])
