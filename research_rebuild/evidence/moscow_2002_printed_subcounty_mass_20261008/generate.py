import sys,json,re,hashlib,shutil
from pathlib import Path
import pandas as pd,xlrd
R=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(R/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
from apply_unique_county_name_bridge_20261007 import county_key
O=Path(__file__).parent;W=Path('/workspace/settlements-work')/O.name
F=Path('/workspace/settlements-raw/data/raw/2002/010_3e630cc803_02c_Moskovskaya-oblast.xls')
C=Path('/workspace/settlements-work/sources/raw_okato_2009_verification_v1/raw_classifier.parquet')
H=Path('/workspace/settlements-work/coordinates/historical_named_candidates_v4/all_historical_named_objects.parquet')
def nk(v):return ' '.join(re.sub(r'[^а-яa-z0-9]+',' ',normalize(v)).split())
s=load(25);d=s.obs[s.obs.source_file.str.contains('010_3e630cc803_02c_Moskovskaya',na=False)].copy();d=d[d.is_additive_settlement_record.fillna(False)];d['haspoint']=d.source_record_id.isin(s.point_rows);d['full3']=d.source_record_id.map(lambda x:s.years[s.uf.find(x)]=={2002,2010,2021});d=d[~d.haspoint&~d.full3].nlargest(200,'population').copy()
sh=xlrd.open_workbook(str(F)).sheet_by_name('Sheet1');ctx={};county='';countyrow=None;community='';communityrow=None
for i in range(sh.nrows):
 raw=str(sh.cell_value(i,1));n=normalize(raw)
 if re.search(r'район - все сельское население$',n):county=raw.strip().split(' - ')[0];countyrow=i+1;community='';communityrow=None
 elif 'подчиненные администрации' in n:
  if countyrow is None:county=raw.strip();countyrow=i+1
  community='';communityrow=None
 elif n.endswith('сельский округ'):community=raw.strip();communityrow=i+1
 ctx[i+1]=(county,countyrow,community,communityrow,raw)
old_context_competitors={}
for z in s.obs[s.obs.source_file.str.contains('010_3e630cc803_02c_Moskovskaya',na=False)&s.obs.is_additive_settlement_record.fillna(False)].itertuples():
 zr=int(z.source_record_id.rsplit(':',1)[1]);zc=ctx[zr];old_context_competitors.setdefault((zc[3],nk(z.name_norm),normalize(z.type_norm)),[]).append(z.source_record_id)
c=pd.read_parquet(C);c=c[c.historical_okato.str.startswith('46')].copy();c['n']=c.name.map(nk);c['t']=c.status.map(lambda v:'поселок' if normalize(v)=='поселок сельского типа' else normalize(v))
counties={r.historical_okato[:5]:county_key(r.name) for r in c.itertuples() if len(r.historical_okato)==8 and r.historical_okato.endswith('000') and 'район' in normalize(r.name)}
parents={r.historical_okato:r for r in c.itertuples() if r.is_settlement_raw=='f' and len(r.historical_okato)==8 and not r.historical_okato.endswith('00')}
def commkey(v):return normalize(re.sub(r'\s+сельский округ$','',normalize(v)))
parentkeys={}
for code,r in parents.items():parentkeys.setdefault((counties.get(code[:5],''),normalize(r.name)),[]).append(code)
locals=c[c.is_settlement_raw.eq('t')].copy();locals['p']=locals.historical_okato.str[:8];idx={k:g for k,g in locals.groupby(['p','n','t'])}
h=pd.read_parquet(H);h=h[h.historical_okato.str.startswith('46')].copy();hidx={k:g for k,g in h.groupby('historical_okato')};pointcodes=h[~h.is_deleted.fillna(True)].groupby(['latitude_from_lat','longitude_from_long']).historical_okato.nunique().to_dict()
cur=s.obs[s.obs.census_year.eq(2021)&s.obs.is_additive_settlement_record.fillna(False)].copy();cur['n']=cur.name_norm.map(normalize);cur['t']=cur.type_norm.map(normalize);cur['code']=cur.okato.fillna('').astype(str).str.replace(r'\.0$','',regex=True)
curcodes={k:g for k,g in cur[cur.code.ne('')].groupby('code')};curnames={k:g for k,g in cur.groupby(['n','t'])};rows=[];alts=[];spatial=[]
for a in d.itertuples():
 row=int(a.source_record_id.rsplit(':',1)[1]);ct,cr,cm,mr,raw=ctx[row];pp=parentkeys.get((county_key(ct),commkey(cm)),[]);rec={'source_record_id':a.source_record_id,'population_2002':a.population,'settlement_name':a.settlement_name,'settlement_type':a.settlement_type,'source_file':str(F),'source_sha256':sha(F),'sheet':'Sheet1','source_row_1based':row,'literal_raw_label':raw,'literal_county_heading':ct,'county_heading_row_1based':cr,'literal_subcounty_heading':cm,'subcounty_heading_row_1based':mr,'classifier_parent_candidates':';'.join(pp),'historical_parent_context_quality':'exact_printed_name_and_county' if len(pp)==1 else 'unknown_unresolved','candidate_status':'hold_no_unique_classifier_parent'}
 rec['all_old_same_subcounty_name_type_competitors']=';'.join(old_context_competitors.get((mr,nk(a.name_norm),normalize(a.type_norm)),[]));rec['old_same_subcounty_name_type_competitor_count']=len(old_context_competitors.get((mr,nk(a.name_norm),normalize(a.type_norm)),[]))
 if len(pp)==1:
  p=pp[0];rec.update(classifier_parent_code=p,classifier_parent_raw_name=parents[p].name_raw,classifier_parent_source_line_1based=parents[p].source_line_1based)
  ll=idx.get((p,nk(a.name_norm),normalize(a.type_norm)),pd.DataFrame());rec['own_classifier_competitor_count']=len(ll)
  if len(ll)==1:
   l=ll.iloc[0];code=l.historical_okato;rec.update(historical_own_okato=code,classifier_own_name=l.name,classifier_own_type=l.status,classifier_own_type_comparison='rural_poselok_explicit_type_variant' if normalize(l.status)=='поселок сельского типа' else 'exact_normalized_type',classifier_own_source_line_1based=l.source_line_1based,classifier_sha256=l.source_sha256,candidate_status='resolved_native_to_unique_own_classifier')
   gg=hidx.get(code,pd.DataFrame());gg=gg[gg.historical_name_exact.fillna(False)&gg.historical_type_exact.fillna(False)&gg.historical_code_structure_compatible.fillna(False)&~gg.is_deleted.fillna(True)] if len(gg) else gg
   gg=gg[gg.latitude_from_lat.notna()&gg.longitude_from_long.notna()&gg.latitude_from_lat.between(-90,90)&gg.longitude_from_long.between(-180,180)] if len(gg) else gg
   rec['valid_own_geokladr_records']=len(gg)
   cc=curcodes.get(code,pd.DataFrame());rec['all_current_code_competitors']=len(cc)
   if len(cc):
    for b in cc.itertuples():alts.append({'old_source_record_id':a.source_record_id,'historical_own_okato':code,'current_source_record_id':b.source_record_id,'current_name':b.settlement_name,'current_type':b.settlement_type,'current_region':b.region_norm,'current_county':b.district_raw,'already_full3':s.years[s.uf.find(b.source_record_id)]=={2002,2010,2021},'has_own_accepted_point':b.source_record_id in s.point_rows})
   if len(cc)==1:
    b=cc.iloc[0];bid=b.source_record_id;rec.update(current_source_record_id=bid,current_name=b.settlement_name,current_type=b.settlement_type,current_region=b.region_norm,current_county=b.district_raw,current_population=b.population,current_years=';'.join(map(str,sorted(s.years[s.uf.find(bid)]))),current_ownpoint_admitted=bid in s.point_rows,current_already_full3=s.years[s.uf.find(bid)]=={2002,2010,2021})
    if normalize(b.name_norm)!=normalize(a.name_norm) or normalize(b.type_norm)!=normalize(a.type_norm) or b.region_norm!='московская':rec['candidate_status']='hold_current_code_name_type_region_contradiction'
    elif len(gg)!=1:rec['candidate_status']='hold_geokladr_owncode_record_nonunique_or_missing'
    elif bid not in s.point_rows:rec['candidate_status']='hold_current_ownpoint_missing'
    elif s.years[s.uf.find(a.source_record_id)] & s.years[s.uf.find(bid)]:rec['candidate_status']='hold_repeated_year_graph_competitor'
    else:
     g=gg.iloc[0];pt=s.point_rows[bid];dist=distance_km((float(g.latitude_from_lat),float(g.longitude_from_long)),(pt['latitude'],pt['longitude']));rec.update(own_geokladr_latitude=g.latitude_from_lat,own_geokladr_longitude=g.longitude_from_long,geokladr_record_1based=g.record_number_1based,geokladr_raw_sha256=g.source_sha256_2011,geokladr_kladrcode=g.kladrcode_raw_text,independent_current_point_distance_km=dist,point_origin_file=pt.get('point_origin_file',''),point_origin_sha256=pt.get('point_origin_sha256',''),point_origin_locator=pt.get('point_origin_locator',''),point_ledger_path=pt['point_ledger_path'],would_make_full3=s.years[s.uf.find(a.source_record_id)]|s.years[s.uf.find(bid)]=={2002,2010,2021})
     rec['candidate_status']='action_ready_unique_printed_subcounty_owncode_current_ownpoint' if dist<=5 and bid not in s.conflicting_point_targets else 'hold_independent_ownpoint_conflict'
   else:
    rec['candidate_status']='resolved_native_owncode_current_codeversion_differs_endpoint_review_needed'
    if len(gg)==1:
     g=gg.iloc[0];rec['historical_distinct_owncodes_sharing_raw_point']=pointcodes.get((g.latitude_from_lat,g.longitude_from_long),0);rec.update(own_geokladr_latitude=g.latitude_from_lat,own_geokladr_longitude=g.longitude_from_long,geokladr_record_1based=g.record_number_1based,geokladr_raw_sha256=g.source_sha256_2011,geokladr_kladrcode=g.kladrcode_raw_text)
     nearby=[]
     for b in curnames.get((normalize(a.name_norm),normalize(a.type_norm)),pd.DataFrame()).itertuples():
      if b.source_record_id not in s.point_rows:continue
      pt=s.point_rows[b.source_record_id];dist=distance_km((float(g.latitude_from_lat),float(g.longitude_from_long)),(pt['latitude'],pt['longitude']))
      if dist<=5:
       alt={'old_source_record_id':a.source_record_id,'old_population':a.population,'historical_own_okato':code,'current_source_record_id':b.source_record_id,'current_name':b.settlement_name,'current_type':b.settlement_type,'current_region':b.region_norm,'current_county':b.district_raw,'current_okato':b.okato,'distance_km':dist,'already_full3':s.years[s.uf.find(b.source_record_id)]=={2002,2010,2021},'year_compatible':not bool(s.years[s.uf.find(a.source_record_id)]&s.years[s.uf.find(b.source_record_id)]),'would_make_full3':s.years[s.uf.find(a.source_record_id)]|s.years[s.uf.find(b.source_record_id)]=={2002,2010,2021},'historical_distinct_owncodes_sharing_raw_point':rec['historical_distinct_owncodes_sharing_raw_point'],'old_same_subcounty_name_type_competitor_count':rec['old_same_subcounty_name_type_competitor_count'],'status':'source_header_owncode_bound_endpoint_candidate_spatial_review_required'};spatial.append(alt);nearby.append(alt)
     rec['all_name_type_current_ownpoint_5km_competitors']=len(nearby)
     if len(nearby)==1:rec.update(proposed_current_source_record_id=nearby[0]['current_source_record_id'],proposed_distance_km=nearby[0]['distance_km'],proposed_year_compatible=nearby[0]['year_compatible'],proposed_would_make_full3=nearby[0]['would_make_full3'])

  else:rec['candidate_status']='hold_own_classifier_locality_nonunique_or_missing'
 rows.append(rec)
pd.DataFrame(spatial).to_csv(O/'owncode_bound_current_endpoint_candidates.csv',index=False)
r=pd.DataFrame(rows);r.to_csv(O/'bounded200_source_header_code_resolution.csv',index=False);pd.DataFrame(alts).to_csv(O/'all_current_code_competitors.csv',index=False);ready=r[r.candidate_status.eq('action_ready_unique_printed_subcounty_owncode_current_ownpoint')];ready.to_csv(O/'action_ready_candidate_subset.csv',index=False)
receipt={'status':'candidate_only_not_applied','baseline_stage':25,'scope':'first200_highest_unpointed_nonfull3_native_Moscow2002_rows','rows':len(r),'population':float(r.population_2002.sum()),'source_hash':sha(F),'source_sheet':'Sheet1','literal_subcounty_recovered_rows':int(r.literal_subcounty_heading.ne('').sum()),'exact_unique_classifier_parent_rows':int(r.historical_parent_context_quality.eq('exact_printed_name_and_county').sum()),'unique_classifier_owncode_population':float(r[r.historical_own_okato.notna()].population_2002.sum()),'current_endpoint_candidate_rows':len(spatial),'unique_classifier_owncode_rows':int(r.historical_own_okato.notna().sum()) if 'historical_own_okato' in r else 0,'action_ready_rows':len(ready),'action_ready_old_population':float(ready.population_2002.sum()),'action_ready_new_full3_old_population':float(ready[ready.would_make_full3.fillna(False)].population_2002.sum()) if len(ready) else 0,'outcome_counts':r.candidate_status.value_counts().to_dict(),'all_current_competitors_including_full3':True,'source_values_preserved':True,'parent_population_not_used_as_locality':True,'boundary_comparability':'unknown','historical_context_inferred_from_anchors_rows':0,'outputs':{p.name:sha(p) for p in O.glob('*.csv')}}
(O/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));W.mkdir(exist_ok=True);[shutil.copy2(p,W/p.name) for p in O.iterdir() if p.is_file()];print(json.dumps(receipt,ensure_ascii=False,indent=2))
