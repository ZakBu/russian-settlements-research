from pathlib import Path
import json,gzip,hashlib,xlrd,pandas as pd
R=Path('/workspace/russian-settlements-research');P=R/'research_rebuild/evidence/over500_moscow_20261009/batch7_postnikov_diagnostic';O=Path(__file__).parent;pins={}
def pin(p):
 p=Path(p);pins[str(p)]=dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size);return p
pr=pd.read_csv(pin(P/'component_partition_correction.csv')).iloc[0];proof=json.loads(pin(P/'Postnikovo_qualified_crosscounty_correction_sourceproof.json').read_text());assert pins[str(P/'Postnikovo_qualified_crosscounty_correction_sourceproof.json')]['sha256']==pr.source_binding_proof_sha256
for s in proof['native_source_hashes']:assert pins.setdefault(s['path'],dict(sha256=hashlib.sha256(Path(s['path']).read_bytes()).hexdigest(),bytes=Path(s['path']).stat().st_size))['sha256']==s['sha256']
s2=xlrd.open_workbook(proof['native_source_hashes'][0]['path']).sheet_by_name('Sheet1');s10=xlrd.open_workbook(proof['native_source_hashes'][1]['path']).sheet_by_name('Data Sheet');rows={}
for n,pop,head in [(866,0,'Якотский'),(3616,65,'Марушкинский')]:
 r=s2.row_values(n-1);assert r==proof['original2002rows'][str(n)];assert r[1].strip()=='деревня Постниково'and int(r[2])==pop
 h=next((i+1,s2.row_values(i))for i in range(n-2,-1,-1)if 'сельский округ'in str(s2.cell_value(i,1)));assert head in h[1][1];rows[str(n)]=dict(literal=r[:5],own_heading=h)
r=s10.row_values(11383);assert r==proof['original2010literal_target']and r[3]=='деревня Постниково'and r[4]==157;rows['2010:11384']=dict(literal=r[:5],subcounty_not_printed=True,context=[s10.row_values(i-1)[:5]for i in range(11375,11389)])
S=R/'publication/stage71';m=json.loads(pin(S/'release-assets-manifest.json').read_text());assets={x['name']:x for x in m['assets']};cp=pin(S/'applied_component_snapshot.csv.gz');op=pin(S/'applied_state_observations.parquet')
for p in [cp,op]:assert pins[str(p)]['sha256']==assets[p.name]['sha256']
c=pd.read_csv(cp,dtype=str);uids=json.loads(pr.expected_before_members_JSON);root=c[c.source_record_id==uids[0]].iloc[0].root;members=c[c.root==root].source_record_id.tolist();assert set(members)==set(uids)
after=json.loads(pr.after_partition_JSON);assert set(sum(after,[]))==set(members);sid=next(x for x in members if x.startswith('2010:'));assert[sid]in after
obs=pd.read_parquet(op,columns=['source_record_id','population','type_norm']);current=obs[obs.source_record_id.str.endswith(':66055')].iloc[0];assert current.population==1 and current.type_norm=='деревня'
a=json.load(gzip.open(pin(P/'Postnikovo_both_qualified_own_articles.json.gz'),'rt'));ars=[]
for x in a['query']['pages'].values():
 if 'missing'in x:continue
 t=x['revisions'][0]['slots']['main']['*'];ars.append(dict(title=x['title'],pageid=x['pageid'],revision=x['revisions'][0]['revid'],coordinates=x.get('coordinates'),county_witness=[l for l in t.splitlines()if'Наро-Фомин'in l or'Дмитров'in l or'Якотск'in l or'Марушкин'in l]))
naro=next(x for x in a['query']['pages'].values()if x.get('pageid')==4502517);t=naro['revisions'][0]['slots']['main']['*'];assert'65 человек'in t and'Наро-Фоминского района'in t and'Марушкинское'in t;co=naro['coordinates'][0];assert abs(co['lat']-55.6048083)<1e-5 and abs(co['lon']-37.2335417)<1e-5
old=proof['true_Naro2002_UID'];oldroot=c[c.source_record_id==old].iloc[0].root;oldmembers=c[c.root==oldroot].source_record_id.tolist();assert old not in members
receipt=dict(status='PASS_independent_Postnikovo_exact_partition',pins=pins,native_replayed=rows,current_Dmitrov_native_population=1,baseline_exact_members=sorted(members),true_Naro2002_existing_members=oldmembers,after_partition=after,own_articles=ars,correct_Naro_ownpoint=co,checks='wrong Naro2010 removed from Dmitrov02/21; literalzero and all counts/quality preserved; no above500 gain; partition must precede new Naro02→10 join',limits=['2010 raw leaf has no printedcounty; qualified ownNaro history and Marushkinsky native namedgroup bind county.','Root must assert exact component through ActualStateAPI immediately before all edits.','Review only; no admission or edits to Moscow packet.'])
(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(receipt['status'])
