"""Independent descriptive KOUZh channel/geography audit. No causal effect."""
from pathlib import Path
import hashlib,json,re
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
RAW=ROOT/'work/ecommerce_flows_20261026'
MANIFEST=ROOT/'research/ecommerce_cloud/flows_20261026/kouzh_source_members.json'
GOODS={2:'clothing_footwear',3:'appliances_electronics_communications'}
PLACE={1:'own_locality_or_residential_district',2:'nearby_localities_or_districts',3:'other_russian_region',4:'abroad',-7:'unknown_place'}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def weighted_pct(d,m):return 100*float(d.loc[m,'KVZV'].sum())/float(d.KVZV.sum())
def channel(v):return np.select([v.isin([1,2]),v.isin([3,4])],['positive','negative'],default='unknown')
def aggregate(g,base,year,good,definition,label):
    v=g[f'I04_03_0{good}'];w=g.KVZV;total=float(w.sum())
    r=dict(year=year,goods=GOODS[good],group_definition=definition,group=label,n=len(g),weight=total,group_share_rural_pct=100*total/float(base.KVZV.sum()),channel_wording='internet' if year==2024 else 'post_or_internet')
    for code,name in PLACE.items():
        r[name+'_n']=int(v.eq(code).sum());r[name+'_weight']=float(w[v.eq(code)].sum());r[name+'_pct']=100*r[name+'_weight']/total
    r['external_n']=int(v.isin([2,3,4]).sum());r['external_pct']=100*float(w[v.isin([2,3,4])].sum())/total
    r['joint_external_share_all_rural_pct']=100*float(w[v.isin([2,3,4])].sum())/float(base.KVZV.sum())
    assert np.isclose(sum(r[n+'_pct']for n in PLACE.values()),100)
    return r

def main():
    member=json.loads(MANIFEST.read_text())['members'];proof=[];denom=[];rows=[];compositions=[];proxy=[];standard=[];audit=[];sensitivity=[];short_denom=[]
    for year in [2018,2022,2024]:
        for kind in ['individual.csv','questionnaire.pdf','codebook.xlsx']:
            p=RAW/f'{year}_{kind}';pin=next(r for r in member if r['filename']==p.name)
            assert p.stat().st_size==pin['bytes'] and sha(p)==pin['sha256']
            proof.append({'year':year,'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':pin['sha256']})
        headers=pd.read_csv(RAW/f'{year}_individual.csv',sep=';',nrows=0).columns
        cols=['H01_01','H01_02','H01_12','H00_04','R_1','R_1_1','KVZV','I08_04','I08_05_04']+[f'I04_0{i}_0{j}' for i in [3,4] for j in [1,2,3]]+(['I08_01']if 'I08_01' in headers else [])
        d=pd.read_csv(RAW/f'{year}_individual.csv',sep=';',usecols=cols)
        roster=d[d.H01_02.ge(15)&d.H00_04.eq(2)].copy()
        r=roster[roster.H01_12.ne(99)].copy()
        assert r.R_1.eq(2).all() and r.KVZV.gt(0).all()
        assert r.R_1_1.isin([7,8,9,10]).all()
        for k in [1,2,3]:
            assert r[f'I04_03_0{k}'].isin(PLACE).all()
            assert r[f'I04_04_0{k}'].isin([1,2,3,4,-7]).all()
        denom.append({'year':year,'rural15_roster_n':len(roster),'rural15_roster_weight':float(roster.KVZV.sum()),'information_available_n':len(r),'information_available_weight':float(r.KVZV.sum()),'information_unavailable_n':int(roster.H01_12.eq(99).sum()),'information_unavailable_weight':float(roster.loc[roster.H01_12.eq(99),'KVZV'].sum()),'information_unavailable_pct':weighted_pct(roster,roster.H01_12.eq(99))})
        rem=r[[f'I04_04_0{k}'for k in [1,2,3]]]
        r['any_goods_channel']=np.select([rem.isin([1,2]).any(axis=1),rem.isin([3,4]).all(axis=1)],['positive','negative'],default='unknown')
        use=r.I08_04.isin([1,2,3]);no=r.I08_04.eq(4)
        if year==2018:no|=r.I08_01.eq(2)
        r['general_internet']=np.select([use,no],['user','nonuser'],default='unknown')
        r['purpose_composite']=r.I08_05_04.eq(1 if year==2024 else 4)
        r['age_band']=pd.cut(r.H01_02,[14,29,44,59,np.inf],labels=['15_29','30_44','45_59','60plus'])
        r['stratum']=r.R_1_1.astype(int).astype(str)+'|'+r.age_band.astype(str)+'|'+r.H01_01.astype(int).astype(str)
        target=r.groupby('stratum').KVZV.sum()/r.KVZV.sum();assert len(target)==32
        for good in GOODS:
            rr=r[f'I04_04_0{good}'];binary=pd.Series(channel(rr),index=r.index)
            frequency=rr.map({1:'regular',2:'occasional',3:'no_aware',4:'no_unaware',-7:'unknown'})
            groups=[('all','all',r)]
            for definition,states in [('same_goods_binary',binary),('same_goods_frequency',frequency),('any_goods_binary',r.any_goods_channel)]:
                for lab in states.unique():groups.append((definition,str(lab),r[states.eq(lab)]))
            for definition,label,g in groups:
                if g.empty:continue
                rows.append(aggregate(g,r,year,good,definition,label))
                c={'year':year,'goods':GOODS[good],'group_definition':definition,'group':label,'n':len(g),'weight':float(g.KVZV.sum()),'mean_age':float(np.average(g.H01_02,weights=g.KVZV)),'women_pct':weighted_pct(g,g.H01_01.eq(2))}
                for a in ['15_29','30_44','45_59','60plus']:c['age_'+a+'_pct']=weighted_pct(g,g.age_band.eq(a))
                for size in [7,8,9,10]:c['rural_size_'+str(size)+'_pct']=weighted_pct(g,g.R_1_1.eq(size))
                compositions.append(c)
                if definition in ['same_goods_binary','same_goods_frequency'] and label in ['positive','negative','regular','occasional']:
                    by={k:h for k,h in g.groupby('stratum')};missing=set(target.index)-set(by)
                    row={'year':year,'goods':GOODS[good],'group_definition':definition,'group':label,'target':'same_wave_all_informed_rural15plus_32_age_sex_size_strata','strata_present':len(by),'min_cell_n':min(len(h)for h in by.values()),'uncovered_target_weight_pct':100*float(target.reindex(list(missing)).sum()),'own_locality_pct':None,'external_pct':None,'unknown_place_pct':None}
                    if not missing:
                        row['own_locality_pct']=sum(float(target[k])*weighted_pct(h,h[f'I04_03_0{good}'].eq(1)) for k,h in by.items())
                        row['external_pct']=sum(float(target[k])*weighted_pct(h,h[f'I04_03_0{good}'].isin([2,3,4])) for k,h in by.items())
                        row['unknown_place_pct']=sum(float(target[k])*weighted_pct(h,h[f'I04_03_0{good}'].eq(-7)) for k,h in by.items())
                    standard.append(row)
        # Age-aligned sensitivity only. This does not harmonise IKT questions,
        # calendar reference period or survey design with KOUZh.
        short=r[r.H01_02.le(74)].copy();short_roster=roster[roster.H01_02.le(74)]
        short_denom.append({'year':year,'age_scope':'15_74','roster_n':len(short_roster),'information_available_n':len(short),'information_available_weight':float(short.KVZV.sum()),'information_unavailable_n':int(short_roster.H01_12.eq(99).sum()),'information_unavailable_weight':float(short_roster.loc[short_roster.H01_12.eq(99),'KVZV'].sum())})
        for good in GOODS:
            sr=short[f'I04_04_0{good}'];binary=pd.Series(channel(sr),index=short.index)
            freq=sr.map({1:'regular',2:'occasional',3:'no_aware',4:'no_unaware',-7:'unknown'})
            groups=[('all','all',short)]
            for definition,states in [('same_goods_binary',binary),('same_goods_frequency',freq),('any_goods_binary',short.any_goods_channel)]:
                for label in states.unique():groups.append((definition,str(label),short[states.eq(label)]))
            for definition,label,g in groups:
                if g.empty:continue
                row=aggregate(g,short,year,good,definition,label);row['age_scope']='15_74';sensitivity.append(row)
        # Explicit joint distribution: broad internet use / broad purpose != goods purchase.
        for (general,any_goods,purpose),g in r.groupby(['general_internet','any_goods_channel','purpose_composite']):
            proxy.append({'year':year,'general_internet':general,'any_goods_channel':any_goods,'purpose_search_order_sale_flag':bool(purpose),'n':len(g),'weight':float(g.KVZV.sum()),'share_informed_rural_pct':100*float(g.KVZV.sum())/float(r.KVZV.sum()),'purpose_interpretation':'composite search_goods_services_order_goods_services_sale_personal_items;not_unique_purchase'})
        # All pages searched; relevant sections read in full. Substrings such as
        # предоставляют are not mistaken for delivery questions.
        txt=(RAW/f'{year}_questionnaire.txt').read_text();pages=txt.split('\f')
        for i,page in enumerate(pages,1):
            norm=re.sub(r'\s+',' ',page)
            if 'Где Вы в основном' in norm:
                audit.append({'year':year,'field':'I04_03_01..03','pdf_page':i,'meaning':'main acquisition geography;own/nearby/otherRF/abroad/unknown;may be bought by another person','direct_purchase_channel':False})
                audit.append({'year':year,'field':'I04_04_01..03','pdf_page':i,'meaning':'used internet buying these goods this calendar year'if year==2024 else'used post OR internet buying these goods this calendar year','direct_purchase_channel':True})
            if 'Для каких целей Вы' in norm:
                audit.extend([{'year':year,'field':'I08_04','pdf_page':i,'meaning':'general frequency of internet use;not purchase frequency','direct_purchase_channel':False},{'year':year,'field':'I08_05_04','pdf_page':i,'meaning':'combined search+orders goods/services+selling possessions;not exclusive online purchase','direct_purchase_channel':False}])
    proxydf=pd.DataFrame(proxy);proxy_summary=[]
    for year,g in proxydf.groupby('year'):
        def total(mask):return float(g.loc[mask,'share_informed_rural_pct'].sum())
        proxy_summary.append({'year':year,'channel_wording':'internet_at_purchase'if year==2024 else'post_or_internet_at_purchase','general_internet_user_share_pct':total(g.general_internet.eq('user')),'any_goods_positive_share_pct':total(g.any_goods_channel.eq('positive')),'general_users_all_three_goods_explicit_negative_share_pct':total(g.general_internet.eq('user')&g.any_goods_channel.eq('negative')),'goods_positive_general_nonuser_share_pct':total(g.general_internet.eq('nonuser')&g.any_goods_channel.eq('positive')),'composite_purpose_tick_all_goods_explicit_negative_share_pct':total(g.purpose_search_order_sale_flag.eq(True)&g.any_goods_channel.eq('negative')),'goods_positive_composite_purpose_not_ticked_share_pct':total(g.purpose_search_order_sale_flag.eq(False)&g.any_goods_channel.eq('positive'))})
    for name,data in [('denominators.csv',denom),('purchase_geography_by_channel.csv',rows),('group_composition.csv',compositions),('internet_proxy_crosswalk.csv',proxy),('proxy_summary.csv',proxy_summary),('same_wave_standardised.csv',standard),('questionnaire_field_audit.csv',audit),('purchase_geography_age15_74.csv',sensitivity),('denominators_age15_74.csv',short_denom)]:pd.DataFrame(data).to_csv(HERE/name,index=False)
    # This is a fresh implementation; comparison labels earlier findings as repeated.
    old=pd.read_csv(ROOT/'research/ecommerce_cloud/flows_20261026/purchase_geography_by_remote_use.csv')
    new=pd.DataFrame(rows);checks=[]
    for year in [2018,2022,2024]:
        for good,oldgood in [(2,'clothing_and_footwear'),(3,'appliances_electronics_communications')]:
            for label,oldlabel in [('positive','remote_any'),('negative','no_remote'),('unknown','dont_know')]:
                a=new[(new.year==year)&(new.goods==GOODS[good])&(new.group_definition=='same_goods_binary')&(new.group==label)]
                b=old[(old.year==year)&(old.goods==oldgood)&(old.scope=='remote_group_rural')&(old.group==oldlabel)]
                if a.empty or b.empty:continue
                for x,y in [('n','sample_n'),('weight','base_weight'),('own_locality_or_residential_district_pct','own_locality_or_urban_district_pct')]:
                    delta=float(a.iloc[0][x])-float(b.iloc[0][y]);assert abs(delta)<1e-6
                    checks.append({'year':year,'goods':GOODS[good],'group':label,'new_field':x,'old_field':y,'difference':delta,'novel_result':False})
    pd.DataFrame(checks).to_csv(HERE/'comparison_with_previous.csv',index=False)
    instruction=ROOT/'work/ecommerce_national_test_20261106/purchase_microdata/rosstat_order149_garant.html'
    metadata={'source_id':'ECOM_KOUZH_PUBLIC_MICRODATA_2018_2022_2024','source_page':'https://tochno.st/datasets/surveys','members_manifest':str(MANIFEST.relative_to(ROOT)),'inputs':proof,'unit':'rural persons15plus with available individual information,proxy answers retained;KVZV supplied household weight repeated on individual records','no_information':'H01_12=99 excluded;this is not internetuse','new_fields_found':False,'known_direct_field':'I04_04_01..03','official_2024_interpretation':{'order':'Росстат11.04.2024№149,указанияп146','url':'https://www.garant.ru/products/ipo/prime/doc/408788959/','excerpt':'приобретения товаров посредством заказа через интернет-магазины','interpretation':'Self-reported Internet-shop ordering,not merely browsing;not independently verified completed delivery','raw_path':str(instruction.relative_to(ROOT)),'sha256':sha(instruction)},'new_calculation':'regular/occasional/no-aware/no-unaware geography;any-goods vs same-goods grouping;general-internet/composite-purpose crosswalk;composition;independent earlier binary replication','standardisation':'32same-wave age/sex/rural-size strata to all informed rural15plus;not old pooled-binary target;missing support returnedNA','limits':['2024questionnaireinternetonlywhilecodebookretainsoldpostwording','2018/22postalORinternetcannotseparate','currentcalendarperioddiffersacrosswaves','frequencyqualitativeconstant/occasional,notnumberoforders','noWB/Ozonbrand,noexpenditure,noorderreceiptdestination,nodeliverymode,nopurchase-linkedtripcount','geographyquestionmainoverallacquisition,notgeographyofInternetorders','nosettlementnames,noactualmedium-centreOD,nocausalestimate,nodesign-basedSE']}
    metadata['age_sensitivity']={'age_range':'15..74 inclusive','tables':['purchase_geography_age15_74.csv','denominators_age15_74.csv'],'purpose':'align age range only with IKT;not harmonised goods list,reference period,design or completed delivery'}
    (HERE/'sources_and_methods.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
    print(pd.DataFrame(denom).to_string(index=False))
    print(new[(new.year==2024)&new.group_definition.isin(['same_goods_binary','same_goods_frequency'])][['goods','group_definition','group','n','group_share_rural_pct','own_locality_or_residential_district_pct','external_pct','unknown_place_pct']].round(3).to_string(index=False))
    print('comparison_cells',len(checks))

if __name__=='__main__':main()
