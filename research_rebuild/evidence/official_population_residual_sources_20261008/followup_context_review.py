from pathlib import Path
import pandas as pd,xlrd,re,json,hashlib,collections
O=Path(__file__).resolve().parent
D=O/'reviewed_primary_override_delta_512.csv.gz'
P=Path('/workspace/settlements-raw/data/raw/2010/001_723371ec84_1._20NW_2010.xls')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(x):return re.sub(r'[^а-яa-z0-9]+',' ',str(x).casefold().replace('ё','е').replace('ѐ','е')).strip()
T={'г.':'город','г.п.':'пгт','дер.':'деревня','с.':'село','пос.':'поселок','п.ст.':'поселок','хут.':'хутор','корд.':'кордон','мест.':'местечко'}
a=pd.concat([pd.read_csv(O/'parsed/leningrad_2010_explicit_locality_values_ge100.csv.gz'),pd.read_csv(O/'parsed/leningrad_2010_named_localities_without_values.csv.gz')],ignore_index=True)
for page,line,name in [(41,28,'Ладожский трудпосёлок'),(65,15,'Большая Пустомержа'),(92,32,'Дом отдыха Живой Ручей')]:a.loc[(a.page==page)&(a.line==line),'name_raw']=name
# Railway-station labels retain their explicit station component; do not merge station and ordinary settlement keys.
a['key']=a.apply(lambda r:(T.get(r.type_raw,norm(r.type_raw)),norm(('станция ' if r.type_raw=='п.ст.' else '')+r.name_raw)),axis=1)
ac=a.key.value_counts(); ai={r['key']:r for r in a.to_dict('records') if ac[r['key']]==1}
sh=xlrd.open_workbook(P).sheet_by_name('NW');seq=[]
pat=re.compile(r'^(деревня|пос[её]лок|село|город|пгт|хутор|кордон|местечко)\s+(.+)$',re.I)
for i in range(sh.nrows):
 vals=sh.row_values(i)
 if vals[2]!='Ленинградская':continue
 m=pat.match(str(vals[4]).strip())
 if not m:continue
 k=(norm(m[1]),norm(m[2]));seq.append({'row':i+1,'raw_label':vals[4],'key':k,'primary':ai.get(k)})
sc=collections.Counter(r['key'] for r in seq)
for r in seq:
 if sc[r['key']]!=1:r['primary']=None
byrow={r['row']:i for i,r in enumerate(seq)};d=pd.read_csv(D);out=[];w=[]
for r in d.to_dict('records'):
 n=int(r['old_source_row']);i=byrow[n];target=seq[i];official=ai.get(target['key']);assert official and sc[target['key']]==1
 assert int(official['population'])==int(r['population'])
 muni=official['municipal_unit_source_label'];sp=official['settlement_group_source_label'];neighbors=[]
 for j in range(max(0,i-7),min(len(seq),i+8)):
  if j==i:continue
  q=seq[j];p=q['primary']
  if not p:continue
  neighbors.append({'offset':j-i,'raw_one_based_row':q['row'],'raw_label':q['raw_label'],'official_name':p['name_raw'],'official_type':p['type_raw'],'official_page':p['page'],'official_line':p['line'],'official_municipality':p['municipal_unit_source_label'],'official_SP_GP':p['settlement_group_source_label']})
 same=[q for q in neighbors if q['official_municipality']==muni]
 sameSP=[q for q in same if q['official_SP_GP']==sp]
 prev=min([q for q in neighbors if q['offset']<0],key=lambda q:abs(q['offset']),default=None)
 nxt=min([q for q in neighbors if q['offset']>0],key=lambda q:abs(q['offset']),default=None)
 # Positive literal source-neighbor context. Counts do not participate in the gate.
 bracket=bool(prev and nxt and prev['official_municipality']==nxt['official_municipality']==muni)
 SPblock=len(sameSP)>=3 and bool((prev and prev['official_SP_GP']==sp and prev['official_municipality']==muni) or (nxt and nxt['official_SP_GP']==sp and nxt['official_municipality']==muni))
 countyblock=len(same)>=3 and bool((prev and prev['official_municipality']==muni) or (nxt and nxt['official_municipality']==muni))
 accept=bracket or SPblock or countyblock
 state='accepted_positive_literal_roster_municipal_context' if accept else 'held_insufficient_or_conflicting_neighbor_context'
 method='bracketed_by_two_independent_typed_unique_official_municipal_neighbors' if bracket else 'at_least_three_same_SP_GP_literal_neighbors_and_nearest_match' if SPblock else 'at_least_three_same_municipal_literal_neighbors_and_nearest_match' if countyblock else 'no_context_gate_pass'
 r.update(followup_context_status=state,followup_context_method=method,actual_old_raw_NP_caption=target['raw_label'],actual_old_raw_municipal_caption=None,old_raw_context_method='municipal_context_inferred_from_exact_literal_source_neighbor_roster; NW omits administrative headers',positive_same_municipal_anchors=len(same),positive_same_SP_GP_anchors=len(sameSP),context_neighbor_witnesses_json=json.dumps(neighbors,ensure_ascii=False),context_gate_uses_population=False)
 if not accept:r['decision_status']='held_population_publication_binding'
 out.append(r)
 needed=[]
 for anchor in [prev,nxt]+(sameSP[:3] if SPblock else same[:3]):
  if anchor and anchor not in needed:needed.append(anchor)
 w.append({'old_source_record_id':r['old_source_record_id'],'target_raw_row':n,'raw_target_caption':target['raw_label'],'official_municipality':muni,'official_SP_GP':sp,'status':state,'method':method,'neighbors':needed,'full_neighbor_count':len(neighbors)})
q=pd.DataFrame(out);q.drop(columns=['context_neighbor_witnesses_json']).to_csv(O/'followup_context_all_512.csv.gz',index=False,compression='gzip');q[q.followup_context_status.str.startswith('accepted')].drop(columns=['context_neighbor_witnesses_json']).to_csv(O/'followup_context_accepted_delta.csv.gz',index=False,compression='gzip')
with __import__('gzip').open(O/'followup_literal_neighbor_witnesses.json.gz','wt',encoding='utf8') as f:json.dump(w,f,ensure_ascii=False)
accepted=q[q.followup_context_status.str.startswith('accepted')];held=q[~q.followup_context_status.str.startswith('accepted')]
r={'status':'followup_context_review_original_candidate_pack_frozen','positive_context_rule':'Exact target type/name/censusregion unique in all official and raw regional localities; raw target is positively NP-labelled. At least two nearest bracketing unique typed literal NP neighbors independently bind the same official municipality, OR at least3 sameSP/GP or municipality neighbors within7 raw NP rows plus nearest neighbor same context. All neighbor bindings include officialNULL named rows and use no counts. NW omits literal admin headers; recovered municipal context is a stated roster-context inference, not a fabricated caption.','target_rows':512,'accepted_rows':len(accepted),'held_rows':len(held),'accepted_delta':int(accepted.official_minus_old_delta.sum()),'accepted_old_sum':int(accepted.old_population.sum()),'accepted_new_sum':int(accepted.population.sum()),'held_delta':int(held.official_minus_old_delta.sum()),'methods':q.followup_context_method.value_counts().to_dict(),'biggest_cases':q[q.name_raw.isin(['Каменка','Никольское'])][['name_raw','old_source_row','old_population','population','official_minus_old_delta','followup_context_status','followup_context_method','positive_same_municipal_anchors','positive_same_SP_GP_anchors']].to_dict('records'),'frozen_input':{str(D):sha(D),str(P):sha(P)},'no_selected_mutation':True,'residual_allocation':False,'independent_followup_check_needed':True,'outputs':{}}
for n in ['followup_context_all_512.csv.gz','followup_context_accepted_delta.csv.gz','followup_literal_neighbor_witnesses.json.gz']:
 p=O/n;r['outputs'][n]={'bytes':p.stat().st_size,'sha256':sha(p)}
(O/'followup_context_receipt.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items() if k not in ['outputs']},ensure_ascii=False,indent=2))
