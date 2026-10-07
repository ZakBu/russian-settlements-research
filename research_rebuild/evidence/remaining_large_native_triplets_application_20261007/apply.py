"""Apply bounded source-native name/context triplets on stage20, without loader edits."""
import sys,json,re
from pathlib import Path
from collections import defaultdict
import pandas as pd
ROOT=Path('/workspace/russian-settlements-research');sys.path.insert(0,str(ROOT/'research_rebuild/mass_linkage'))
from working_state_20261007 import load
from current_chain_state_20261007 import normalize,sha,distance_km
O=Path(__file__).parent;R=ROOT/'research_rebuild/evidence/remaining_large_native_triplets_20261007'
# These contexts are literal native source headers or verified own-entity former names.
county_geography={'Ленина':'краснодар','Южный':'белоречен','Сторожовка':'татищев','Жаворонки':'одинцов','Дорохово':'руз','Октябрьский':'богучан','Таежный':'богучан','Халимбек-Аул':'буйнак','Зубутли-Миатли (ЦIобокь-Миякьо)':'кизилюртов','Дмитровск-Орловский':'дмитров','Беднодемьяновск':'спас','Красногвардейское':'красногвардей'}

def main():
    candidate_receipt=json.loads((R/'receipt.json').read_text());verified={}
    def pin(p,h):
        if str(p) not in verified:verified[str(p)]=sha(Path(p))
        if verified[str(p)]!=h:raise ValueError('Source/candidate pin differs: '+str(p))
    for p,h in candidate_receipt['inputs'].items():pin(p,h)
    for p,h in candidate_receipt['raw_primary_source_hashes'].items():pin(p,h)
    for name,h in candidate_receipt['outputs'].items():pin(R/name,h)
    if not candidate_receipt['actual2010_primary_checks_all_passed']:raise ValueError('Bounded2010 source checks failed')
    witnesses=pd.read_csv(R/'candidate_full_triplets.csv',dtype=str,keep_default_na=False);s=load(20);before=s.metrics();member=defaultdict(list)
    for r in s.obs.to_dict('records'):member[s.uf.find(r['source_record_id'])].append(r)
    occupied=defaultdict(set)
    for sid,p in s.point_rows.items():occupied[(int(s.by_id.loc[sid,'census_year']),p['latitude'],p['longitude'])].add(sid)
    edges=[];points=[];holds=[];preserved=[];accepted=[];competitors=[];newpointids=set();old_point_snapshot={sid:dict(p) for sid,p in s.point_rows.items()}
    for a in witnesses.to_dict('records'):
        ids=json.loads(a['source_ids_json']);sid,tid,bid=ids['2002'],ids['2010'],ids['2021'];old=s.by_id.loc[sid];cur=s.by_id.loc[bid];cp=s.point_rows.get(bid)
        if cp is None:holds.append({'source_record_id':sid,'reason':'no_admitted_current_ownpoint'});continue
        if len({s.uf.find(v) for v in ids.values()})==1:holds.append({'source_record_id':sid,'reason':'already_bound_at_stage20'});continue
        if s.uf.find(tid)!=s.uf.find(bid) or s.years[s.uf.find(sid)]!={2002} or s.years[s.uf.find(tid)]!={2010,2021}:holds.append({'source_record_id':sid,'reason':'actual_component_year_conflict'});continue
        if normalize(old.region_norm)!=normalize(cur.region_norm) or normalize(cur.region_norm)!=a['region']:raise ValueError('Source region conflict')
        if str(old.settlement_name)!=a['old_name'] or str(cur.settlement_name)!=a['current_name']:raise ValueError('Native own name pin differs')
        if 'часть' in normalize(old.settlement_name) or 'объект' in normalize(old.settlement_type):raise ValueError('Part or feature cannot be admitted as whole NP')
        pop=json.loads(a['actual_population_json']);quality=json.loads(a['source_population_quality_json'])
        for yr,rid in ids.items():
            r=s.by_id.loc[rid]
            if float(r.population)!=float(pop[yr]) or str(r.population_value_quality)!=quality[yr]:raise ValueError('Population or protected quality changed')
        if not all(bool(s.by_id.loc[rid,'is_additive_settlement_record']) for rid in ids.values()):raise ValueError('Nonadditive source grain')
        token=county_geography[a['old_name']]
        if token not in normalize(cur.district_raw):raise ValueError('Current printed geographic county differs')
        # Bednodemyanovsk/Spassk has an actual own-entity rename, not a caption-only inference.
        if a['old_name']!='Беднодемьяновск' and token not in normalize(a['primary2002_context_literal']):raise ValueError('Printed historic county/city header differs')
        former=json.loads(a['rename_own_article_witness_json'])
        if former:
            pin(former['article_file'],former['article_sha256'])
            if former['wikidata_id'] not in str(cp.get('point_origin_locator','')) or normalize(a['old_name']) not in normalize(former['former_name_literal_line']):raise ValueError('Direct own former-name entity conflict')
        # Namesakes of both printed forms, across all current selected sources, must be county-separated.
        forms={normalize(a['current_name']),normalize(a['old_name'])}
        forms.add(re.sub(r'\s*\([^)]*\)\s*',' ',normalize(a['old_name'])).strip())
        rivals=s.obs[(s.obs.census_year==2021)&s.obs.region_norm.eq(cur.region_norm)&s.obs.settlement_name.map(normalize).isin(forms)&s.obs.source_record_id.ne(bid)]
        unresolved=[r.source_record_id for r in rivals.itertuples() if not normalize(r.district_raw) or token in normalize(r.district_raw)]
        if unresolved:
            resolved_urban_biryuch=(a['old_name']=='Красногвардейское' and str(old.settlement_type)=='пгт' and str(cur.settlement_type)=='город' and former.get('wikidata_id')=='Q105150' and normalize(a['old_name']) in normalize(former.get('former_name_literal_line','')) and all(str(s.by_id.loc[rid,'settlement_type'])=='посёлок' and rid!=bid for rid in unresolved))
            if not resolved_urban_biryuch:holds.append({'source_record_id':sid,'reason':'unresolved_current_sameyear_name_context_alternative','alternative_source_ids':' | '.join(unresolved)});continue
            for rid in unresolved:
                other=s.by_id.loc[rid]
                competitors.append({'candidate_old_source_record_id':sid,'accepted_current_source_record_id':bid,'competing_current_source_record_id':rid,'competing_name':other.settlement_name,'competing_type':other.settlement_type,'competing_population':other.population,'competing_county':other.district_raw,'competing_okato_as_selected':other.okato,'competing_oktmo_as_selected':other.oktmo,'accepted_current_type':cur.settlement_type,'accepted_current_okato_as_selected':cur.okato,'accepted_current_oktmo_as_selected':cur.oktmo,'disambiguation':'Actual old urban Krasnogvardeyskoye row is documented former name on same urban Biryuch Q105150 own article/point; rural settlement Biryuch279 remains distinct and is not joined.','own_entity':'Q105150','former_name_article_file':former['article_file'],'former_name_article_sha256':former['article_sha256'],'former_name_literal_line':former['former_name_literal_line'],'competing_record_modified':False})
        oldcp=json.loads(a['current_admitted_point_json'])
        if distance_km((float(oldcp['latitude']),float(oldcp['longitude'])),(cp['latitude'],cp['longitude']))>5:holds.append({'source_record_id':sid,'reason':'current_donor_changed_over5km'});continue
        relevant=member[s.uf.find(sid)]+member[s.uf.find(tid)]
        if any(r['source_record_id'] in s.conflicting_point_targets for r in relevant):holds.append({'source_record_id':sid,'reason':'accepted_point_alternative_conflict'});continue
        if any(r['source_record_id'] in s.point_rows and distance_km((s.point_rows[r['source_record_id']]['latitude'],s.point_rows[r['source_record_id']]['longitude']),(cp['latitude'],cp['longitude']))>5 for r in relevant):holds.append({'source_record_id':sid,'reason':'existing_component_point_conflict'});continue
        missing=[r for r in relevant if r['source_record_id'] not in s.point_rows and r['source_record_id'] not in newpointids]
        if any(occupied[(int(r['census_year']),cp['latitude'],cp['longitude'])]-{r['source_record_id']} for r in missing):holds.append({'source_record_id':sid,'reason':'new_sameyear_representative_point_collision'});continue
        s.union(sid,tid);member[s.uf.find(sid)]=relevant;accepted.append(a)
        edges.append({'from_source_record_id':sid,'to_source_record_id':tid,'relation':'same_place','decision_status':'checked_rule_accepted','rule':a['identity_rule'],'source_primary_native_witness_file':str(R/'candidate_full_triplets.csv'),'source_primary_native_witness_sha256':verified[str(R/'candidate_full_triplets.csv')],'administrative_event_date':'UNKNOWN','population_boundary_comparability_asserted':False})
        ledger=Path(cp['point_ledger_path']);ledgerhash=sha(ledger)
        for r in relevant:
            rid=r['source_record_id'];yr=int(r['census_year'])
            if rid in s.point_rows:preserved.append({'target_source_record_id':rid,'latitude':s.point_rows[rid]['latitude'],'longitude':s.point_rows[rid]['longitude'],'coordinate_admission_status':s.point_rows[rid]['coordinate_admission_status'],'point_ledger_path':s.point_rows[rid]['point_ledger_path']});continue
            if rid in newpointids:continue
            p={k:v for k,v in cp.items() if k!='point_ledger_path'};p.update(target_source_record_id=rid,target_year=yr,coordinate_source_record_id=bid,coordinate_admission_status='reviewed_extension_rule_accepted',coordinate_origin_ledger=str(ledger),coordinate_origin_ledger_sha256=ledgerhash,coordinate_origin_ledger_locator='target_source_record_id='+bid,continuity_inference='retrospective_representative_current_ownpoint_after_actual_native_source_same_place_union',direct_historical_measurement=False,population_boundary_comparability_asserted=False,administrative_event_date='UNKNOWN');points.append(p);newpointids.add(rid);occupied[(yr,cp['latitude'],cp['longitude'])].add(rid)
    pd.DataFrame(edges,columns=['from_source_record_id','to_source_record_id','relation','decision_status','rule','source_primary_native_witness_file','source_primary_native_witness_sha256','administrative_event_date','population_boundary_comparability_asserted']).to_csv(O/'accepted_identity_edge_delta.csv',index=False)
    pd.DataFrame(points).to_csv(O/'accepted_point_use_delta.csv',index=False)
    pd.DataFrame(holds,columns=['source_record_id','reason','alternative_source_ids']).to_csv(O/'held_candidates.csv',index=False);pd.DataFrame(preserved).to_csv(O/'preserved_existing_point_uses.csv',index=False);pd.DataFrame(competitors).to_csv(O/'disambiguated_competitors.csv',index=False)
    s.add_deltas(point_paths=[O/'accepted_point_use_delta.csv']);after=s.metrics()
    for sid,p in old_point_snapshot.items():
        if s.point_rows[sid]!=p:raise ValueError('Existing point/status was modified')
    subgroup={}
    for a in accepted:
        quality=json.loads(a['source_population_quality_json']);key='2010_secondary_protected_quality_retained' if 'protected' in quality['2010'] else 'all_three_primary_reported_quality';g=subgroup.setdefault(key,{'histories':0,'actual_population':{str(y):0 for y in [2002,2010,2021]}});g['histories']+=1
        for y,v in json.loads(a['actual_population_json']).items():g['actual_population'][y]+=int(v)
    receipt={'status':'applied_actual_native_row_name_county_former_name_triplets','baseline_stage':20,'new_edges':len(edges),'new_point_uses':len(points),'held':len(holds),'explicitly_disambiguated_competing_rural_records':len(competitors),'baseline':before,'after':after,'population_gain':{y:after[y]['covered_population']-before[y]['covered_population'] for y in before},'full_three_row_gain':{y:after[y]['covered_rows']-before[y]['covered_rows'] for y in before},'population_quality_subgroups':subgroup,'all_source_population_and_protected_quality_retained':True,'existing_point_uses_preserved':True,'administrative_eventdate':'UNKNOWN','population_boundary_comparability_asserted':False,'actual_native_source_witness_file':str(R/'candidate_full_triplets.csv'),'bounded_checks_reused_without_repeating_source_audit':True,'inputs':{str(p):sha(Path(p)) for p in [*s.inputs,R/'receipt.json',R/'candidate_full_triplets.csv',R/'actual2010_raw_row_witnesses.csv',Path(__file__)] if Path(p).resolve().parent!=O},'verified_candidate_primary_source_hashes':verified,'outputs':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in [O/'accepted_identity_edge_delta.csv',O/'accepted_point_use_delta.csv',O/'held_candidates.csv',O/'preserved_existing_point_uses.csv',O/'disambiguated_competitors.csv']}}
    receipt['inputs'][str(Path(__file__).resolve())]=sha(Path(__file__));(O/'application_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['status','new_edges','new_point_uses','held','population_gain','full_three_row_gain']}))
if __name__=='__main__':main()
