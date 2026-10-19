"""Actual point aggregates and non-equivalent municipal agricultural context.

Never allocates municipal totals to functional fragments. 2016/2021 exact codes
are compared on the fixed 2021 settlement axis, not historical legal boundaries.
"""
import argparse, collections, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

BASE = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
MEMBERS = {
    'lower_school_1_9': ['Малоказаккулово','Калуево','Амангильдино'],
    'lower_shared_school_health': ['Малоказаккулово','Калуево'],
    'upper_school_10_11_documented_fragment': ['Уральск','Малоказаккулово','Калуево','Амангильдино'],
}
LEGAL_MEMBERS = {
    '80653410': ('Амангильдинский сельсовет', ['Малоказаккулово','Амангильдино','Галиахмерово','Калуево','Кучуково-Маяк','Сураманово']),
    '80653491': ('Уральский сельсовет',['Уральск','Базаргулово','Истамгулово','Ишкиново','Октябрьск']),
}
GROUPS = {
    'agriculture01': (r'^01(?:\.|$)', 'A'),
    'agricultural_support016': (r'^01\.6(?:\d|\.|$)', 'A'),
    'food_manufacture10': (r'^10(?:\.|$)', 'C'),
    'agricultural_wholesale462': (r'^46\.2(?:\d|\.|$)', 'G'),
    'food_wholesale463': (r'^46\.3(?:\d|\.|$)', 'G'),
    'veterinary75': (r'^75(?:\.|$)', 'M'),
}
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(2**20),b''): h.update(b)
    return h.hexdigest()
def norm(x):
    s=x.astype('string').str.strip()
    return s.where(s.str.fullmatch(r'\d{10,11}',na=False)).str.zfill(11)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--base',type=Path,default=BASE);ap.add_argument('--out',type=Path,default=OUT);a=ap.parse_args()
    base=a.base;out=a.out;out.mkdir(parents=True,exist_ok=True)
    axis=base/'anchor_research_20261019/data/point_axis.parquet'
    p=pd.read_parquet(axis); p=p[p.municipality_oktmo8_2021.eq('80653000')].copy()
    p['code']=norm(p.oktmo_2021);assert p.code.is_unique
    legal=[]
    for code,(label,names) in LEGAL_MEMBERS.items():
        for name in names:
            z=p[p.name.eq(name) & p.code.str.startswith(code)]
            assert len(z)<=1
            v=z.iloc[0] if len(z) else None
            legal.append({'municipality_code':code,'municipality':label,'name':name,'id':v.id if v is not None else None,'oktmo_2021':v.code if v is not None else None,'population_2002':v.population_2002 if v is not None else None,'population_2010':v.population_2010 if v is not None else None,'population_2021':v.population_2021 if v is not None else None,'matched_axis':v is not None,'membership_source':'RB126z_article2_48b_48ts','source_host_status':'legislation_reproduction_not_official_host','historical_membership_2007_2009_not_proven':True})
    legal=pd.DataFrame(legal);legal.to_csv(out/'municipal_legal_membership.csv',index=False)
    scopes=[]
    for scope,names in MEMBERS.items():
        for name in names:
            z=p[p.name.eq(name)];assert len(z)==1;v=z.iloc[0]
            provider_name='Уральск' if scope.startswith('upper_') else 'Малоказаккулово'
            scopes.append({'scope':scope,'id':v.id,'name':name,'oktmo_2021':v.code,'municipality_code':v.code[:8],'population_2002':v.population_2002,'population_2010':v.population_2010,'population_2021':v.population_2021,'member_role':'provider' if name==provider_name else 'documented_external_origin','scope_basis':'2025_documented_function_not_2007_2009_boundary'})
    scopes=pd.DataFrame(scopes);scopes.to_csv(out/'documented_scope_members.csv',index=False);scopes.to_parquet(out/'documented_scope_members.parquet',index=False)
    cross=[]
    for (scope,code),g in scopes.groupby(['scope','municipality_code']):
        allscope=scopes[scopes.scope.eq(scope)];m=legal[legal.municipality_code.eq(code)]
        cross.append({'scope':scope,'municipality_code':code,'municipality':LEGAL_MEMBERS[code][0],'scope_places_in_municipality':len(g),'scope_total_places':len(allscope),'scope_population_2021_in_municipality':g.population_2021.sum(),'scope_total_population_2021':allscope.population_2021.sum(),'scope_place_share_in_municipality':len(g)/len(allscope),'scope_population_share_in_municipality':g.population_2021.sum()/allscope.population_2021.sum(),'municipality_legal_places':len(m),'municipality_axis_places':int(m.matched_axis.sum()),'share_legal_places_captured':len(g)/len(m),'municipality_axis_population_2021':m.population_2021.sum(),'share_observed_axis_population_captured_NOT_complete_MO':g.population_2021.sum()/m.population_2021.sum(),'scope_equals_municipality':set(g.name)==set(m.name),'polygon_overlap_area_known':False,'source_dates':'agriculture2007_2009;membership_page_access2026;functions2025;census2021','contemporaneous_boundary_equivalence_proven':False})
    cross=pd.DataFrame(cross);cross.to_csv(out/'functional_municipal_crosswalk.csv',index=False)
    # Read raw agricultural schema first and scan all rows in bounded batches.
    raw=base/'restored/extracted/inputs/recovery_inputs/columnar/agriculture.parquet';pf=pq.ParquetFile(raw)
    (out/'agriculture_schema.txt').write_text(str(pf.schema_arrow))
    selected=[];levels=collections.Counter();n=0
    for b in pf.iter_batches(batch_size=60000):
        d=b.to_pandas();n+=len(d);levels.update(d.mun_level.value_counts().to_dict())
        z=d[d.oktmo.isin(['80653410','80653491','80653000'])]
        if len(z):selected.append(z)
    s=pd.concat(selected,ignore_index=True);s.to_parquet(out/'official_municipal_series.parquet',index=False)
    lower=s[s.oktmo.isin(LEGAL_MEMBERS)].copy();lower['temporal_scope']='2007_2009_later_function_scope_not_known'
    lower.to_csv(out/'official_lower_municipal_context_2007_2009.csv',index=False)
    inventory=s.groupby(['oktmo','municipality','mun_level','indicator_code','indicator_name','indicator_unit'],dropna=False).agg(rows=('year','size'),nonmissing=('indicator_value','count'),year_min=('year','min'),year_max=('year','max')).reset_index();inventory.to_csv(out/'municipal_indicator_coverage.csv',index=False)
    # Verify additive crop totals. Cows are a cattle subset, never add all livestock.
    balances=[]
    for (code,year),g in lower[lower.indicator_code.eq('Y48007001')].groupby(['oktmo','year']):
        total=g.loc[g.kultur.str.strip().eq('Всего'),'indicator_value']
        subtotal=g.loc[~g.kultur.str.strip().eq('Всего'),'indicator_value'].sum(min_count=1)
        balances.append({'municipality_code':code,'year':year,'reported_total_ha':total.iloc[0] if len(total) else np.nan,'component_sum_ha':subtotal,'difference_ha':total.iloc[0]-subtotal if len(total) else np.nan,'total_reported':bool(len(total))})
    bal=pd.DataFrame(balances);bal.to_csv(out/'crop_component_balance.csv',index=False)
    # Unit-consistent cattle/household-garden context. Not allocated to SGRT.
    profile=[]
    for (code,year),g in lower.groupby(['oktmo','year']):
        def val(ind,col,label):
            z=g[g.indicator_code.eq(ind)&g[col].str.strip().eq(label)].indicator_value
            assert len(z)<=1;return z.iloc[0] if len(z) else np.nan
        profile.append({'municipality_code':code,'municipality':LEGAL_MEMBERS[code][0],'year':year,'household_sown_total_reported_ha':val('Y48007001','kultur','Всего'),'household_potato_ha':val('Y48007001','kultur','Картофель'),'household_vegetable_ha':val('Y48007001','kultur','Овощи открытого и закрытого грунта'),'household_cattle_heads':val('Y48007002','skot','Крупный рогатый скот'),'household_cows_heads_subset_of_cattle':val('Y48007002','skot','Коровы'),'catchment_value_identified':False})
    pd.DataFrame(profile).to_csv(out/'lower_municipal_profiles.csv',index=False)
    # Exact settlement-code witnesses; no nearest allocation and no turnover/jobs inference.
    paths=[];witnesses=[];scanned={};code_to_uid=dict(zip(p.code,p.id));wanted=set(scopes.id)
    for year in [2016,2021]:
        f=base/f'restored/extracted/inputs/recovery_inputs/enrichment/rfsd_{year}_selected.parquet';paths.append(f);rf=pq.ParquetFile(f);nrf=0
        for b in rf.iter_batches(batch_size=60000,columns=['inn','oktmo','okved','okved_section','lat','lon','geocoding_quality']):
            d=b.to_pandas();nrf+=len(d);d['code']=norm(d.oktmo);d['id']=d.code.map(code_to_uid);d=d[d.id.isin(wanted)&d.inn.notna()].copy()
            d['inn']=d.inn.astype('string').str.strip();d=d[d.inn.ne('')]
            for group,(pattern,section) in GROUPS.items():
                z=d[d.okved.astype('string').str.match(pattern,na=False)].copy()
                if not len(z):continue
                z['group']=group;z['year']=year;z['section_consistent']=z.okved_section.eq(section);witnesses.append(z)
        scanned[str(year)]=nrf;assert nrf==rf.metadata.num_rows
    cols=['inn','oktmo','okved','okved_section','lat','lon','geocoding_quality','code','id','group','year','section_consistent']
    w=pd.concat(witnesses,ignore_index=True) if witnesses else pd.DataFrame(columns=cols)
    w=w.merge(p[['id','name','lat','lon']],on='id',suffixes=('','_point'),validate='many_to_one')
    valid=w.lat.between(-90,90)&w.lon.between(-180,180)
    da=np.radians(w.lat-w.lat_point);db=np.radians(w.lon-w.lon_point)
    h=np.sin(da/2)**2+np.cos(np.radians(w.lat))*np.cos(np.radians(w.lat_point))*np.sin(db/2)**2
    w['coordinate_distance_km']=np.where(valid,2*6371.0088*np.arcsin(np.sqrt(np.clip(h,0,1))),np.nan)
    w['strict_house_5km']=w.geocoding_quality.eq('house')&w.coordinate_distance_km.le(5)&w.section_consistent
    w['evidence_status']='registered_legal_address_not_actual_farm_site_or_agroservice_flow'
    w.to_csv(out/'agro_legal_witnesses_2016_2021.csv',index=False);w.to_parquet(out/'agro_legal_witnesses_2016_2021.parquet',index=False)
    # Trace apparent losses anywhere in the 2021 source before interpreting them.
    before=set(w[w.year.eq(2016)].inn);after=set(w[w.year.eq(2021)].inn);lost=before-after
    follow=[];follow_rows=0
    for b in pq.ParquetFile(paths[-1]).iter_batches(batch_size=60000,columns=['inn','oktmo','okved','okved_section','eligible','filed']):
        d=b.to_pandas();follow_rows+=len(d);z=d[d.inn.isin(lost)]
        if len(z):follow.append(z)
    followed=pd.concat(follow,ignore_index=True) if follow else pd.DataFrame(columns=['inn','oktmo','okved','okved_section','eligible','filed'])
    followed.to_csv(out/'missing2016_2021_targeted_followup.csv',index=False)
    transitions=[]
    for inn in sorted(before|after):
        transitions.append({'inn':inn,'agro_witness2016':inn in before,'agro_witness2021':inn in after,'any2021_source_row_if_apparent_loss':bool(followed.inn.eq(inn).any()) if inn in lost else None,'interpretation':'registered_agro_witness_persists' if inn in before&after else 'source_witness_missing_not_observed_closure','physical_site_closure_observed':False})
    pd.DataFrame(transitions).to_csv(out/'agro_identity_transition_2016_2021.csv',index=False)
    point=[];agg=[]
    for year in [2016,2021]:
        for group in GROUPS:
            for mode in ['exact_code_section_consistent','exact_code_strict_house5km']:
                z=w[w.year.eq(year)&w.group.eq(group)&(w.section_consistent if mode=='exact_code_section_consistent' else w.strict_house_5km)]
                for uid in sorted(wanted):
                    zz=z[z.id.eq(uid)];point.append({'year':year,'id':uid,'name':p.set_index('id').loc[uid,'name'],'group':group,'quality_mode':mode,'unique_legal_entities':zz.inn.nunique(),'rows':len(zz)})
                for scope,names in MEMBERS.items():
                    u=set(scopes[scopes.scope.eq(scope)].id);zz=z[z.id.isin(u)]
                    agg.append({'scope':scope,'year':year,'group':group,'quality_mode':mode,'unique_legal_entities':zz.inn.nunique(),'raw_witness_rows':len(zz),'pop2021_fixed_scope':scopes[scopes.scope.eq(scope)].population_2021.sum(),'registered_presence_only':True,'independent_enterprise_sites_not_known':True,'individual_entrepreneurs_complete':False,'branches_complete':False})
    point=pd.DataFrame(point);agg=pd.DataFrame(agg);point.to_csv(out/'point_agro_counts_2016_2021.csv',index=False);agg.to_csv(out/'functional_agro_legal_aggregates.csv',index=False);agg.to_parquet(out/'functional_agro_legal_aggregates.parquet',index=False)
    checks=[]
    def ck(name,ok): checks.append({'name':name,'pass':bool(ok)})
    ck('raw_scan_balance',n==pf.metadata.num_rows==sum(levels.values()))
    ck('municipal_membership_complete_legal_list',len(legal)==11)
    ck('one_missing_axis_place_explicit',legal[~legal.matched_axis].name.tolist()==['Кучуково-Маяк'])
    ck('scope_members_unique',not scopes.duplicated(['scope','id']).any())
    ck('nested_lower_school_subset_upper',set(scopes[scopes.scope.eq('lower_school_1_9')].id)<set(scopes[scopes.scope.eq('upper_school_10_11_documented_fragment')].id))
    nesting=pd.read_csv(base/'functional_dynamics_20261019/model/results/documented_functional_nesting.csv').iloc[0]
    shared=pd.read_csv(base/'functional_dynamics_20261019/model/results/documented_multifunction_fragments.csv').iloc[0]
    expected_lower={nesting.lower_provider_uid,*str(nesting.common_origins).split('|')}
    expected_multi={shared.provider_uid,*str(shared.shared_origins).split('|')}
    ck('scope_matches_documented_model_nesting',set(scopes[scopes.scope.eq('lower_school_1_9')].id)==expected_lower and set(scopes[scopes.scope.eq('upper_school_10_11_documented_fragment')].id)==expected_lower|{nesting.higher_provider_uid})
    ck('shared_scope_matches_multifunction_graph',set(scopes[scopes.scope.eq('lower_shared_school_health')].id)==expected_multi)
    ck('scope_to_municipality_weights_sum1',np.allclose(cross.groupby('scope').scope_population_share_in_municipality.sum(),1))
    ck('no_scope_equals_municipality',not cross.scope_equals_municipality.any())
    ck('official_lower31rows',len(lower)==31)
    ck('historical_lower_only2007_2009',set(lower.year)=={2007,2008,2009})
    ck('all_reported_crop_totals_balance',np.allclose(bal[bal.total_reported].difference_ha,0))
    ck('raw_measures_unique',not lower.duplicated(['oktmo','year','indicator_code','kultur','skot','kategor','selmash','okpd2']).any())
    ck('no_negative_agriculture_values',lower.indicator_value.dropna().ge(0).all())
    ck('witness_inn_within_year_point_group_unique',not w.duplicated(['year','id','group','inn']).any())
    ck('all_agro_sections_consistent',w.section_consistent.all())
    ck('targeted_followup_full2021_scan',follow_rows==scanned['2021'])
    ck('point_counts_complete',len(point)==4*2*len(GROUPS)*2)
    ck('scope_counts_complete',len(agg)==3*2*len(GROUPS)*2)
    for _,r in agg.iterrows():
        u=set(scopes[scopes.scope.eq(r.scope)].id);z=point[point.id.isin(u)&point.year.eq(r.year)&point.group.eq(r.group)&point.quality_mode.eq(r.quality_mode)]
        ck('scope_sum_'+r.scope+'_'+str(r.year)+'_'+r.group+'_'+r.quality_mode,z.unique_legal_entities.sum()==r.unique_legal_entities)
    lo=agg[agg.quality_mode.eq('exact_code_strict_house5km')].set_index(['scope','year','group']).unique_legal_entities
    hi=agg[agg.quality_mode.eq('exact_code_section_consistent')].set_index(['scope','year','group']).unique_legal_entities
    ck('strict_subset',lo.le(hi).all())
    for f,frame in [('functional_agro_legal_aggregates.parquet',agg),('documented_scope_members.parquet',scopes),('agro_legal_witnesses_2016_2021.parquet',w)]:
        pd.testing.assert_frame_equal(frame,pd.read_parquet(out/f));ck('readback_'+f,True)
    inputs=[axis,raw,*paths,base/'functional_dynamics_20261019/history/UCHALY_RESULT.md',base/'functional_dynamics_20261019/model/results/documented_functional_nesting.csv',base/'functional_dynamics_20261019/model/results/documented_multifunction_fragments.csv']
    audit={'status':'computed_point_legal_aggregates_and_finer_municipal_context_no_false_total_allocation','raw_rows_scanned':n,'raw_level_counts':dict(levels),'official_lower_rows':len(lower),'official_lower_years':sorted(lower.year.unique().tolist()),'RFSD_rows_scanned':scanned,'agro_witness_rows':len(w),'unique_inn_by_year':{str(y):int(g.inn.nunique()) for y,g in w.groupby('year')},'checks_passed':sum(x['pass'] for x in checks),'checks_total':len(checks),'all_pass':all(x['pass'] for x in checks),'inputs':[{'path':str(f.relative_to(base)),'bytes':f.stat().st_size,'sha256':sha(f)} for f in inputs],'code_sha256':sha(Path(__file__)),'source_equivalence':'none:functional2025!=municipality2007_2009','actual_agricultural_flows_observed':False,'agriculture_total_allocated_to_fragment':False,'multiple_group_double_count_note':'01.6 is subset of01; never sum group totals; scopes overlap hierarchically; never sum scopes'}
    (out/'AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n');(out/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
    assert audit['all_pass'];print(json.dumps(audit,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
