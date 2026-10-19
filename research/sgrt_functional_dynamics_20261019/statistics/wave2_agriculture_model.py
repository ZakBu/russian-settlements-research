#!/usr/bin/env python3
"""Second-wave independent audit; preserves the first accepted audit freeze."""
from pathlib import Path
import collections, hashlib,json,re
import numpy as np,pandas as pd,pyarrow.parquet as pq
from html.parser import HTMLParser
class HTMLText(HTMLParser):
 def __init__(self):super().__init__();self.parts=[]
 def handle_data(self,data):self.parts.append(data)
R=Path(__file__).resolve().parents[1];B=R.parent;O=Path(__file__).resolve().parent/'wave2'
O.mkdir(exist_ok=True);checks=[];inputs={}
def readpath(p):
 inputs[str(p.relative_to(B))]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()};return p
def ck(n,v):checks.append({'name':n,'pass':bool(v)})
def norm(s):
 z=s.astype('string').str.strip();return z.where(z.str.fullmatch(r'\d{10,11}',na=False)).str.zfill(11)
def agriculture():
 ag=R/'agriculture';axis=pd.read_parquet(readpath(B/'anchor_research_20261019/data/point_axis.parquet'));axis['code']=norm(axis.oktmo_2021)
 legal=pd.read_csv(readpath(ag/'municipal_legal_membership.csv'),dtype={'municipality_code':'string','oktmo_2021':'string'})
 parser=HTMLText();parser.feed(readpath(ag/'law126z.html').read_text());text=' '.join(' '.join(parser.parts).split())
 # Several Bashkortostan districts have councils with these exact names.
 # Restrict identity to article 48, rather than taking the first name hit.
 text=text.split('48) в составе Учалинского района:',1)[1].split('49)',1)[0]
 expected={'80653410':['Малоказаккулово','Амангильдино','Галиахмерово','Калуево','Кучуково-Маяк','Сураманово'],'80653491':['Уральск','Базаргулово','Истамгулово','Ишкиново','Октябрьск']}
 for code,names in expected.items():
  ck('law_list_'+code,set(legal[legal.municipality_code.eq(code)].name)==set(names))
  title='Амангильдинский сельсовет:' if code.endswith('410') else 'Уральский сельсовет:'
  excerpt=text.split(title,1)[1].split('(приложение',1)[0]
  ck('primary_law_mentions_'+code,all(n in excerpt for n in names))
  for n in names:
   z=axis[axis.name.eq(n)&axis.code.str.startswith(code,na=False)];rr=legal[legal.name.eq(n)&legal.municipality_code.eq(code)].iloc[0]
   ck('identity_'+n,(len(z)==1 and z.iloc[0].id==rr.id) or (len(z)==0 and pd.isna(rr.id)))
 ck('missing_place_only_kuchukovo',legal[~legal.matched_axis].name.tolist()==['Кучуково-Маяк'])
 scopes=pd.read_csv(readpath(ag/'documented_scope_members.csv'),dtype={'municipality_code':'string','oktmo_2021':'string'})
 expected_scopes={'lower_school_1_9':{'Малоказаккулово','Калуево','Амангильдино'},'lower_shared_school_health':{'Малоказаккулово','Калуево'},'upper_school_10_11_documented_fragment':{'Малоказаккулово','Калуево','Амангильдино','Уральск'}}
 for name,names in expected_scopes.items():ck('scope_names_'+name,set(scopes[scopes.scope.eq(name)].name)==names)
 cross=pd.read_csv(readpath(ag/'functional_municipal_crosswalk.csv'),dtype={'municipality_code':'string'});alloc=[]
 for _,row in cross.iterrows():
  a=scopes[scopes.scope.eq(row.scope)&scopes.municipality_code.eq(row.municipality_code)];l=legal[legal.municipality_code.eq(row.municipality_code)]
  pop=axis.set_index('id').loc[a.id,'population_2021'].sum();total=scopes[scopes.scope.eq(row.scope)].population_2021.sum()
  vals={'scope_places_in_municipality':len(a),'scope_population_2021_in_municipality':pop,'scope_population_share_in_municipality':pop/total,'municipality_legal_places':len(l),'municipality_axis_places':int(l.matched_axis.sum()),'share_legal_places_captured':len(a)/len(l),'share_observed_axis_population_captured_NOT_complete_MO':pop/l.population_2021.sum()}
  for k,v in vals.items():ck('crosswalk_'+row.scope+'_'+row.municipality_code+'_'+k,np.isclose(v,row[k]))
 rawpath=readpath(B/'restored/extracted/inputs/recovery_inputs/columnar/agriculture.parquet');pf=pq.ParquetFile(rawpath);parts=[];levels=collections.Counter()
 for batch in pf.iter_batches(batch_size=100000):
  d=batch.to_pandas();levels.update(d.mun_level.value_counts().to_dict());z=d[d.oktmo.isin(expected)]
  if len(z):parts.append(z)
 raw=pd.concat(parts,ignore_index=True);raw.to_parquet(O/'independent_lower_raw.parquet',index=False)
 author=pd.read_csv(readpath(ag/'official_lower_municipal_context_2007_2009.csv'),dtype='string')
 ck('raw_31_rows',len(raw)==len(author)==31);ck('raw_level_balance',sum(levels.values())==8832750)
 ck('raw_municipal_counts',raw.groupby('oktmo').size().to_dict()=={'80653410':16,'80653491':15})
 # String-normalized unordered rows, every raw column including units/categories.
 def canon(d):return sorted(tuple('' if pd.isna(v) else str(v) for v in row) for row in d[raw.columns].itertuples(index=False,name=None))
 a=author.copy()
 for c in ['year','indicator_value']:a[c]=pd.to_numeric(a[c])
 ck('raw_all_31_full_rows_match',canon(raw)==canon(a))
 balances=[]
 for (code,year),g in raw[raw.indicator_code.eq('Y48007001')].groupby(['oktmo','year']):
  is_total=g.kultur.str.strip().eq('Всего');total=g[is_total].indicator_value.sum(min_count=1);components=g[~is_total].indicator_value.sum(min_count=1)
  if is_total.any():ck(f'crop_components_{code}_{year}',np.isclose(total,components))
  balances.append({'code':code,'year':int(year),'reported_total':None if not is_total.any() else total,'component_sum':components})
 pd.DataFrame(balances).to_csv(O/'independent_crop_balances.csv',index=False)
 # Demonstrate why unvalidated allocation is not identified. These figures are
 # counterfactual arithmetic, not estimates of fragment production or bounds.
 for _,r in cross.iterrows():
  for y in [2008,2009]:
   z=raw[raw.oktmo.eq(r.municipality_code)&raw.year.eq(y)&raw.indicator_code.eq('Y48007001')&raw.kultur.str.strip().eq('Всего')]
   if len(z):
    value=float(z.iloc[0].indicator_value);alloc.append({'scope':r.scope,'municipality_code':r.municipality_code,'agriculture_year':y,'published_whole_municipality_ha':value,'illustration_place_fraction_ha':value*r.share_legal_places_captured,'illustration_observed_population_fraction_ha':value*r.share_observed_axis_population_captured_NOT_complete_MO,'not_identified_fragment_value':True,'different_dates_and_boundary_not_verified':True})
 pd.DataFrame(alloc).to_csv(O/'allocation_nonidentification_demonstration.csv',index=False)
 # Independent raw RFSD extraction by exact code and decimal prefix tuple.
 wanted=set(scopes.id);code_to_id=axis.set_index('code').id;rows=[];lost=set();found_lost=[]
 definitions={'agriculture01':('A','01'),'agricultural_support016':('A','01.6'),'food_manufacture10':('C','10'),'agricultural_wholesale462':('G','46.2'),'food_wholesale463':('G','46.3'),'veterinary75':('M','75')}
 for year in [2016,2021]:
  path=readpath(B/f'restored/extracted/inputs/recovery_inputs/enrichment/rfsd_{year}_selected.parquet')
  for batch in pq.ParquetFile(path).iter_batches(batch_size=100000,columns=['inn','oktmo','okved','okved_section','lat','lon','geocoding_quality']):
   d=batch.to_pandas()
   if year==2021 and lost:
    zz=d[d.inn.isin(lost)]
    if len(zz):found_lost.extend(zz.inn.tolist())
   d['id']=norm(d.oktmo).map(code_to_id);d=d[d.id.isin(wanted)]
   for group,(sec,prefix) in definitions.items():
    s=d.okved.fillna('');mask=s.str.startswith(prefix) if '.' in prefix else s.str[:2].eq(prefix)
    z=d[mask&d.okved_section.eq(sec)]
    for q in z.itertuples(index=False):
     place=axis.set_index('id').loc[q.id];lat1,lat2=np.radians([q.lat,place.lat]);dl=np.radians(q.lon-place.lon)
     # Independent atan2 spherical angle rather than author asin(haversine).
     crossmag=np.sqrt((np.cos(lat2)*np.sin(dl))**2+(np.cos(lat1)*np.sin(lat2)-np.sin(lat1)*np.cos(lat2)*np.cos(dl))**2)
     angle=np.arctan2(crossmag,np.sin(lat1)*np.sin(lat2)+np.cos(lat1)*np.cos(lat2)*np.cos(dl));dist=6371.0088*angle
     rows.append({'year':year,'id':q.id,'inn':q.inn,'group':group,'strict':q.geocoding_quality=='house' and np.isfinite(dist) and dist<=5,'distance':dist})
  if year==2016:lost={r['inn'] for r in rows}
 raw_w=pd.DataFrame(rows);a=pd.read_csv(readpath(ag/'agro_legal_witnesses_2016_2021.csv'),dtype={'inn':'string'})
 ck('raw_witness_keys',set(map(tuple,raw_w[['year','id','inn','group']].to_numpy()))==set(map(tuple,a[['year','id','inn','group']].to_numpy())))
 reported=pd.read_csv(readpath(ag/'point_agro_counts_2016_2021.csv'))
 for r in reported.itertuples(index=False):
  z=raw_w[raw_w.year.eq(r.year)&raw_w.id.eq(r.id)&raw_w.group.eq(r.group)]
  if r.quality_mode=='exact_code_strict_house5km':z=z[z.strict]
  ck(f'point_agro_{r.year}_{r.id}_{r.group}_{r.quality_mode}',z.inn.nunique()==r.unique_legal_entities)
 actual_lost=set(raw_w[raw_w.year.eq(2016)].inn)-set(raw_w[raw_w.year.eq(2021)].inn)
 ck('two_source_losses',len(actual_lost)==2);ck('lost_inn_not_any2021_row',not (actual_lost&set(found_lost)))
 pd.DataFrame([{'year':y,'unique_agro':int(d.inn.nunique()),'strict_unique_agro':int(d[d.strict].inn.nunique())} for y,d in raw_w.groupby('year')]).to_csv(O/'independent_agro_summary.csv',index=False)
 return axis

def model(axis):
 p=axis.set_index('id');m=pd.read_csv(readpath(R/'model/results/canonical_documented_external_memberships.csv'));a=pd.read_csv(readpath(R/'model/results/fixed_source_catchment_demography.csv'))
 for (src,date,dst,fun,level),g in m.groupby(['canonical_source_id','canonical_evidence_date','destination_uid','function_group','canonical_service_level'],dropna=False):
  u=sorted(set(g.origin_uid));z=p.loc[u];r=a[a.source_id.eq(src)&a.source_document_date.fillna('').eq('' if pd.isna(date) else date)&a.destination_uid.eq(dst)&a.function_group.eq(fun)&a.service_level.eq(level)]
  ck('model_fixed_one_'+str((src,dst,fun,level)),len(r)==1);r=r.iloc[0]
  for y in [2002,2010,2021]:
   v=z[f'population_{y}'];ck(f'model_sum_{src}_{dst}_{level}_{y}',v.sum(min_count=1)==r[f'population_{y}']);ck(f'model_zeros_{src}_{dst}_{level}_{y}',v.eq(0).sum()==r[f'n_zero_population_{y}']);ck(f'model_missing_{src}_{dst}_{level}_{y}',v.isna().sum()==r[f'n_missing_population_{y}'])
 transitions=pd.read_csv(readpath(R/'model/results/history_positive_assignment_transitions.csv'));acc=pd.read_csv(readpath(R/'model/results/history_two_axis_accounting.csv'))
 ck('model_60_resolved_transitions',len(transitions)==60);ck('model_11_exact_decompositions',len(acc)==11)
 for r in acc.itertuples(index=False):
  t=transitions[transitions.comparison_scope.eq(r.comparison_scope)&transitions.from_document_year.eq(r.from_document_year)&transitions.to_document_year.eq(r.to_document_year)];u=t.origin_uid
  old=t.old_provider_uid.eq(r.destination_uid).to_numpy().astype(int);new=t.new_provider_uid.eq(r.destination_uid).to_numpy().astype(int);pop0=p.loc[u,'population_2010'].to_numpy();pop1=p.loc[u,'population_2021'].to_numpy()
  vals={'old_boundary_old_population':old@pop0,'new_boundary_new_population':new@pop1,'fixed_old_boundary_population_change':old@(pop1-pop0),'boundary_effect_at_new_population':(new-old)@pop1,'two_axis_total_difference':new@pop1-old@pop0}
  for k,v in vals.items():ck('model_decomp_'+str((r.comparison_scope,r.destination_uid,k)),v==getattr(r,k))
 rel=pd.read_csv(readpath(R/'model/results/integrated_relations.csv'));ck('289_relations',len(rel)==289)
 ck('no_self_external_membership',m.origin_uid.ne(m.destination_uid).all());ck('unique_source_memberships',m.canonical_membership_id.is_unique)
 ck('preserve_full_axis_zero2010',axis.population_2010.eq(0).sum()==21246)

def main():
 axis=agriculture();model(axis)
 audit={'status':'PASS' if all(x['pass'] for x in checks) else 'FAIL','n_checks':len(checks),'checks':checks,'inputs':inputs,'independent_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Independent audit of agriculture and updated model. RFSD full calendar not yet accepted.','limits':['Municipality agricultural production not allocated to functional fragment','Old agricultural years are not contemporary functional scope','Missing year INN is not physical closure','Equal-area spatial envelopes retained in first wave do not measure missing-data bias']}
 (O/'AGRICULTURE_MODEL_AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');print(audit['status'],len(checks),flush=True);assert all(x['pass'] for x in checks)
if __name__=='__main__':main()
