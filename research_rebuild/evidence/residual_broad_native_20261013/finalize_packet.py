from pathlib import Path
import pandas as pd,json,gzip,hashlib,xlrd,re
O=Path(__file__).parent;R=O.parents[2];w=pd.read_csv(O/'source_witnesses.csv.gz').fillna('');rv=pd.read_csv(O/'reviews.csv').fillna('');ed=pd.read_csv(O/'proposed_identity_edges.csv'); by=w.set_index('source_record_id').to_dict('index')
refpaths=set();refs=[]
for v in by.values():
 p=json.loads(v['accepted_point_provenance_json']);q=p.get('source_context_witness_file','')
 if q and Path(q).exists():refpaths.add(q)
for q in refpaths:
 if q.endswith('.json.gz'):
  x=json.load(gzip.open(q,'rt'));arr=x if isinstance(x,list) else [x]
 else:arr=pd.read_csv(q).fillna('').to_dict('records')
 for x in arr:
  sid=x.get('source_record_id',x.get('target_source_record_id',''))
  if sid in by:refs.append({'source_record_id':sid,'prior_primary_witness_file':q,'prior_primary_witness_sha256':hashlib.sha256(Path(q).read_bytes()).hexdigest(),'primary_witness_json':json.dumps(x,ensure_ascii=False)})
pd.DataFrame(refs).to_csv(O/'prior_primary_witnesses.csv.gz',index=False,compression={'method':'gzip','mtime':0})
# Explicit reviewed scope decisions rely on reopened native row plus already accepted county/own-site provenance.
accept={'мордовия:Первомайский':'literal native Ковылкинский county, Краснопресненский leaf roster and corrected current ownsite','чувашская:Чиршкасы':'native Чебоксарский, current exact recoded owncode97644482101 and historical Чиршкасинский roster','смоленская:Ново-Никольское':'old2002/2010 already same accepted component; merge separate2021 typed village in literal Вяземский county','тамбовская:Козьмодемьяновка':'native Лысогорский ownleaf roster9073/9074 distinguishes samecounty namesake; old/current Тамбовский','краснодарский:Южный':'native2002 explicit administration г.Армавира, 2010Армавир and currentАрмавир','краснодарский:Мирный':'native2002 explicit administration г.ГорячийКлюч,2010ГорячийКлюч and currentГорячийКлюч','адыгея:Подгорный':'native raw2010 cityМайкоп row227 ownrow231 before nextcity236; imported Шовгеновский discrepancy explicitly proven in accepted point binding','адыгея:Веселый':'native raw2010 cityМайкоп row227 ownrow234 before nextcity236; imported Шовгеновский discrepancy explicitly proven in accepted point binding','самарская:Александровка':'ownAlexandrovka council KinelCherkassky exact ordered native468-472 roster excludes Kinelsky namesake','самарская:Березовка':'native own Elkhovo Berezovka council297-299 roster excludes typed village rival','самарская:Тростянка':'prior independent lower/upper ownnative current flanks sameBogato county','самарская:Кашпир':'prior independent lower/upper ownnative flanks union bounded counties and unique exact typed ownleaf','волгоградская:Белогорский':'prior independent native lower/upper flanks bounded counties unique ownleaf','волгоградская:Веселый':'prior independent native lower/upper flanks bounded counties unique ownleaf','тамбовская:Александровка':'prior independent native lower/upper flanks sameZnamensky county','башкортостан:Надеждино':'native2010 afterПриютово beforeАксаково/Баженово/Екатериновка sameBelebey county ownсело/code80209801002','пермский:Березовка':'old2002/2010 accepted same component native cityУсолье+three ownUs olsky peer context;2021 merge requires documentedUs olsky→Berezniki county history','пермский:Романово':'separate2002 plus accepted2010/2021 same component; explicitUs olsky→Berezniki county history required'}
# Perm county modernization remains held until dated witness is supplied.
accept.pop('пермский:Березовка');accept.pop('пермский:Романово')
for i,v in rv.iterrows():
 if v['case'] in accept and v['status'] not in ('hold_nearby_namesake','hold_not_unique_full3','hold_native_type_variation'):
  rv.loc[i,'status']='proposed_native_scope_rule';rv.loc[i,'scope_binding_explanation']=accept[v['case']]
  # Nearest earlier printed county is a contextual locator only, not inferred target county.
rv['prior_county_heading_is_target_binding']=False
rv.to_csv(O/'reviews.csv',index=False)
out=ed[ed.case.isin(rv[rv.status.eq('proposed_native_scope_rule')]['case'])].copy()
# Keep one spanning connection per component pair, never redundant three-edge triangles.
parent={}
def root(x):
 parent.setdefault(x,x)
 if parent[x]!=x:parent[x]=root(parent[x])
 return parent[x]
f=pd.read_parquet('/workspace/scratch/residual-20261013/base15/applied_state_observations.parquet',columns=['source_record_id','root']).set_index('source_record_id')['root'].to_dict();keep=[]
for i,v in out.iterrows():
 a,z=root(f[v.from_source_record_id]),root(f[v.to_source_record_id])
 if a==z:continue
 parent[z]=a;keep.append(i)
out=out.loc[keep];out['decision_status']='checked_rule_accepted';out['admission_rule']=out.case.map(accept)+'; actual native sourceIDs/count/type reopened; accepted own-locality point provenance reused; no nearby namesake or repeated censusyear; modern point retrospective continuity, population/boundary equivalence unknown.';out['source_context_witness_file']=str(O/'source_witnesses.csv.gz');out['prior_primary_witness_file']=str(O/'prior_primary_witnesses.csv.gz');out.to_csv(O/'accepted_identity_edge_delta.csv',index=False)
m=json.loads((O/'manifest.json').read_text());m.update(status='bounded_full3_identity_packet_for_independent_root_review',proposed_accepted_cases=len(out.case.unique()),proposed_accepted_edges=len(out),review_note='Nearest preceding county headings may belong to unrelated earlier region; never used as target binding. Explicit scope_binding_explanation or existing native component required.',prior_primary_witness_hashes={q:hashlib.sha256(Path(q).read_bytes()).hexdigest() for q in refpaths},output_hashes={str(q):hashlib.sha256(q.read_bytes()).hexdigest() for q in O.glob('*.csv*')});(O/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2));print(out[['case','from_source_record_id','to_source_record_id']].to_string(index=False));print('cases',len(out.case.unique()),'edges',len(out))
