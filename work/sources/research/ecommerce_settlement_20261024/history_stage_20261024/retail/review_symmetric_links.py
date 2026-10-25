"""Independent bounded audit; outputs only to retail/. Does not import linker."""
from pathlib import Path
from collections import defaultdict,Counter
import re,unicodedata,hashlib,json
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent
P=OUT.parent
KEY='source_record_id_2021'
x=pd.read_parquet(P/'wb_history_symmetric_links.parquet')
d=pd.read_parquet(P.parent/'national/national_target_source2021.parquet')
c=pd.read_parquet(P/'centres/settlement_admin_context_main2021.parquet')
d=d.merge(c[[KEY,'admin_centre_positive_20200110','context_status_20200110',
              'admin_centre_positive_20211103','context_status_20211103']],on=KEY,validate='one_to_one')
lookup=d.set_index(KEY)
assert not x.duplicated(['archive_date','source_object_id']).any()

def norm(s):
    return ' '.join(re.sub(r'[^\w\s-]',' ',unicodedata.normalize('NFKC',str(s)).lower().replace('ё','е')).split())
# Independent procedural token stripping implements the documented matching rule.
patterns=['поселок городского типа','рабочий поселок','город','село','деревня','хутор',
          'станица','поселок','аул','слобода','станция',r'ст-ца',r'пгт\.?',r'р\.?\s*п\.?',
          r'пос\.?',r'сл\.?',r'ст\.?',r'г\.?',r'с\.?',r'д\.?',r'х\.?',r'п\.?']

def components(address,limit=None):
    out=[]
    for raw in str(address or '').lower().replace('ё','е').split(',')[:limit]:
        part=re.sub(r'\([^)]*\)',' ',raw).strip()
        for token in patterns:
            mt=re.match('^'+token+r'\s+',part)
            if mt:
                part=part[mt.end():];break
        v=norm(part)
        if v:out.append(v)
    return out

def km(lat,lon,la,lo):
    # Haversine, independent of linker Cartesian vectors/KDTree.
    p1=np.radians(lat);p2=np.radians(la)
    dl=np.radians(np.asarray(lo)-lon)
    dp=p2-p1
    a=np.sin(dp/2)**2+np.cos(p1)*np.cos(p2)*np.sin(dl/2)**2
    return 6371.0088*2*np.arcsin(np.sqrt(np.minimum(1,a)))

points=d.loc[d.accepted_point_present_2021].reset_index(drop=True)
index=defaultdict(list)
for i,n in enumerate(points.name_2021):index[norm(n)].append(i)

def matching(row,limit=4):
    ids=set(i for n in components(row.address,limit) for i in index.get(n,[]))
    if not ids:return []
    pp=points.iloc[sorted(ids)]
    dist=km(row.latitude,row.longitude,pp.accepted_latitude_2021.to_numpy(),pp.accepted_longitude_2021.to_numpy())
    return [(r[KEY],float(di),r.name_2021,r.type_2021,r.region_2021) for (_,r),di in zip(pp.iterrows(),dist) if di<=10+1e-8]

# Deterministic sample with all dates and all accepted/ambiguous/unresolved states.
sample=[]
dates=sorted(x.archive_date.unique())
for j,(date,g) in enumerate(x.groupby('archive_date')):
    for status,n in [('accepted_unique_exact_address_component_and_coordinate',8+(j<4)),
                     ('ambiguous_multiple_named_candidates',2),('unresolved_no_named_candidate',2)]:
        h=g.loc[g.link_status_5km.eq(status)].copy()
        h['hash']=h.source_object_id.map(lambda k:hashlib.sha256((date+'|'+str(k)).encode()).hexdigest())
        sample.extend(h.sort_values('hash').head(n).drop(columns='hash').to_dict('records'))
assert len(sample)==100
checks=[]
for row in pd.DataFrame(sample).itertuples(index=False):
    match=matching(row)
    r={'archive_date':row.archive_date,'source_object_id':row.source_object_id,'address':row.address,
       'normalized_components_first4':' | '.join(components(row.address,4))}
    for radius in [1,5,10]:
        a=[m for m in match if m[1]<=radius]
        expected='accepted_unique_exact_address_component_and_coordinate' if len(a)==1 else 'ambiguous_multiple_named_candidates' if len(a)>1 else 'unresolved_no_named_candidate'
        r[f'candidate_n_{radius}km']=len(a)
        r[f'status_{radius}km']=expected
        r[f'status_match_{radius}km']=expected==getattr(row,f'link_status_{radius}km')
        expected_id=a[0][0] if len(a)==1 else None
        actual_id=getattr(row,KEY+f'_{radius}km')
        r[f'id_match_{radius}km']=expected_id==actual_id or (expected_id is None and pd.isna(actual_id))
        if len(a)==1:
            err=abs(a[0][1]-getattr(row,f'distance_km_{radius}km'))
            r[f'distance_error_km_{radius}km']=err
            r[f'candidate_name_{radius}km']=a[0][2]
            r[f'candidate_type_{radius}km']=a[0][3]
            r[f'candidate_region_{radius}km']=a[0][4]
            assert err<1e-6
        else:r[f'distance_error_km_{radius}km']=None
        assert r[f'status_match_{radius}km'] and r[f'id_match_{radius}km']
    checks.append(r)
pd.DataFrame(checks).to_csv(OUT/'symmetric_link_sample100.csv',index=False)

# Independent aggregate recalculation from link rows + accepted base.
inv=pd.read_csv(P/'wb_history_linkage_inventory.csv')
for r in inv.itertuples(index=False):
    g=x.loc[x.archive_date.eq(r.archive_date)]
    assert len(g)==r.ru_catalogue_objects
    assert int(g[f'{KEY}_{r.radius_km}km'].notna().sum())==r.linked_objects
    assert len(g)-r.linked_objects==r.unresolved_or_ambiguous
    assert json.loads(r.status_counts)==g[f'link_status_{r.radius_km}km'].value_counts().to_dict()
f=pd.read_csv(P/'wb_history_admin_footprints.csv',dtype={'context_vintage':str})
for r in f.itertuples(index=False):
    g=x.loc[x.archive_date.eq(r.archive_date)&x[f'{KEY}_{r.radius_km}km'].notna()]
    if r.profile=='fitting_positive_observed':g=g.loc[g.fitting_rooms.ge(1)]
    if r.profile=='fitting_positive_or_unknown':g=g.loc[g.fitting_rooms.ge(1)|g.fitting_rooms.isna()]
    ids=set(g[f'{KEY}_{r.radius_km}km'])
    n=d.loc[d[KEY].isin(ids)]
    centre=n[f'admin_centre_positive_{r.context_vintage}']
    known=n[f'context_status_{r.context_vintage}'].eq('accepted_administrative_parent_and_centre')
    expected=[len(n),n.population_2021.sum(),int(n.population_2021.gt(0).sum()),
              int(centre.sum()),int((known&~centre).sum()),int((~known&~centre).sum())]
    actual=[r.positive_nodes,r.population2021,r.inhabited_positive_nodes,r.centre_positive_nodes,
            r.other_known_positive_nodes,r.unknown_context_positive_nodes]
    assert expected==actual,(expected,actual)
changes=pd.read_csv(P/'wb_catalogue_footprint_changes.csv')
for r in changes.itertuples(index=False):
    k=f'{KEY}_{r.radius_km}km'
    a=x.loc[x.archive_date.eq(r.older_date)]
    b=x.loc[x.archive_date.eq(r.current_date)]
    old=set(a[k].dropna());new=set(b[k].dropna())
    newfit=set(b.loc[b.fitting_rooms.ge(1),k].dropna())
    conservative=newfit-old
    cc=d.loc[d[KEY].isin(conservative)]
    expected=[len(old),len(new),len(old&new),len(new-old),len(old-new),len(conservative),
              int(cc.admin_centre_positive_20211103.sum()),
              int((cc.context_status_20211103.eq('accepted_administrative_parent_and_centre')&~cc.admin_centre_positive_20211103).sum())]
    actual=[r.older_catalogue_nodes,r.current_catalogue_nodes,r.retained_nodes,r.current_only_catalogue_nodes,
            r.older_only_catalogue_nodes,r.current_fitting_positive_nodes_without_old_catalogue_record,
            r.latter_documented_centres2021,r.latter_other_known_members2021]
    assert expected==actual

# Material diagnostic: first-four-components restriction can be asymmetric across dates.
late=[]
for row in x.loc[x.link_status_5km.eq('unresolved_no_named_candidate') & x.address.str.count(',').ge(4)].itertuples(index=False):
    m=[z for z in matching(row,limit=None) if z[1]<=5]
    if len(m)==1:
        late.append({'archive_date':row.archive_date,'source_object_id':row.source_object_id,
                     'address':row.address,'full_components':' | '.join(components(row.address)),
                     'candidate_id':m[0][0],'candidate_name':m[0][2],'candidate_type':m[0][3],
                     'distance_km':m[0][1]})
pd.DataFrame(late).to_csv(OUT/'symmetric_link_beyond_first4_candidates.csv',index=False)

# Type-conflict candidates require historical administrative-status review, not automatic errors.
conflicts=[]
for row in x.loc[x[f'{KEY}_5km'].notna()].itertuples(index=False):
    target=lookup.loc[getattr(row,KEY+'_5km')]
    for component in str(row.address).lower().replace('ё','е').split(',')[:4]:
        if re.match(r'^\s*(?:г\.|город)\s+',component) and norm(target.name_2021) in components(component,4) and target.type_2021 not in ['город','пгт']:
            conflicts.append({'archive_date':row.archive_date,'source_object_id':row.source_object_id,
                'address':row.address,'name_2021':target.name_2021,'type_2021':target.type_2021,
                'region_2021':target.region_2021,'distance_km':getattr(row,'distance_km_5km')})
pd.DataFrame(conflicts).to_csv(OUT/'symmetric_link_explicit_city_type_conflicts.csv',index=False)

# Explicit city/village homonyms illustrate avoidable ambiguity, not a validated fix.
ambiguous_city=[]
for row in x.loc[x.link_status_5km.eq('ambiguous_multiple_named_candidates') &
                 x.address.str.contains(r'(?:^|,)\s*(?:г\.|город)\s+',case=False,regex=True)].itertuples(index=False):
    m=[z for z in matching(row) if z[1]<=5]
    cn=[]
    for part in str(row.address).lower().replace('ё','е').split(',')[:4]:
        if re.match(r'^\s*(?:г\.|город)\s+',part):cn+=components(part,4)
    for name in cn:
        same=[z for z in m if norm(z[2])==name]
        if sum(z[3]=='город' for z in same)==1 and any(z[3] not in ['город','пгт'] for z in same):
            ambiguous_city.append({'archive_date':row.archive_date,'source_object_id':row.source_object_id,
                'address':row.address,'candidate_types':' | '.join(z[3] for z in same),
                'candidate_names':' | '.join(z[2] for z in same)})
            break
pd.DataFrame(ambiguous_city).to_csv(OUT/'symmetric_link_ambiguous_city_village_homonyms.csv',index=False)

nonmonotonic=[]
profiles=[]
for date,g in x.groupby('archive_date'):
    nonmonotonic.append({'archive_date':date,
      'accepted1_becomes_ambiguous5':int((g[f'{KEY}_1km'].notna()&g.link_status_5km.eq('ambiguous_multiple_named_candidates')).sum()),
      'accepted5_becomes_ambiguous10':int((g[f'{KEY}_5km'].notna()&g.link_status_10km.eq('ambiguous_multiple_named_candidates')).sum())})
    for typ,h in g.groupby('typePoint',dropna=False):
        profiles.append({'archive_date':date,'typePoint':None if pd.isna(typ) else int(typ),'n':len(h),
          'fitting_positive':int(h.fitting_rooms.ge(1).sum()),'fitting_missing':int(h.fitting_rooms.isna().sum()),
          'linked5km':int(h[f'{KEY}_5km'].notna().sum())})
pd.DataFrame(profiles).to_csv(OUT/'symmetric_link_type_fitting_profiles.csv',index=False)
result={
 'review_scope':'catalogue linkage validity and independent arithmetic, not ground-truth completeness or operational history',
 'input_rows':len(x),'snapshots':dates,'sample100_rows':len(checks),'sample_design':'SHA256(date|id), stratified 8dates and 3main5km statuses; 68accepted+16ambiguous+16unresolved',
 'independent_recalculation':'different haversine formula plus inverted-name index, no imported linker functions',
 'sample_status_id_distance_checks':'PASS: 300 radius-specific status/id/distance comparisons; distance tolerances1e-6km',
 'inventory_rows_verified':len(inv),'footprint_rows_verified':len(f),'change_rows_verified':len(changes),
 'beyond_first4_unique5km_candidates':len(late),
 'beyond_first4_by_date':dict(Counter(r['archive_date'] for r in late)),
 'explicit_city_matched_nonurban_type_cases':len(conflicts),
 'ambiguous_explicit_city_village_homonyms':len(ambiguous_city),
 'ambiguous_explicit_city_village_by_date':dict(Counter(r['archive_date'] for r in ambiguous_city)),
 'nonmonotonic_radius_diagnostics':nonmonotonic,
 'can_describe_catalogue_footprint_change':True,
 'strict_profile_note':'current_fitting_positive_without_old_catalogue_record is a stricter observed-evidence contrast, NOT a lower bound on true openings/growth',
 'claim_scope':'change in positively observed catalogue evidence under a fixed name/coordinate linkage rule, explicit source and field-coverage caveats; not complete network or true customer-PVZ changes',
 'material_risks':[
  'First-four-component parsing may miss nested localities; address formatting changes across dates.',
  'One centroid point and no settlement polygons preferentially miss urban peripheries at1/5km; distances are linkage rules, not service distance.',
  'Region text is discarded and prefix/type ignored; exact homonyms or changed administrative status need extra review.',
  'Uniqueness is evaluated inside each radius; accepted1/5km can become ambiguous at5/10km, so linked sets are not nested.',
  'Alltype current catalogue includes objects outside narrow pickup8/34; typePoint is not comparable across snapshots.',
  'Fitting metadata missingness differs strongly by date; fitting-positive is evidence of a field, not validated operational classification.',
  'Catalogue object IDs cannot automatically be used as persistent physical-unit identities.',
  'Fixed2021 names/points and administrative contexts omit historical renamings, relocations and boundary/status changes.',
  'An unobserved old catalogue record is not a verified absence, opening date or proof of retail function gain.'
 ],
 'not_established':'no independently ground-truthed sample or operational validation; arithmetic agreement does not imply no false matches',
 'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'linker_sha256':hashlib.sha256((P/'link_history_symmetrically.py').read_bytes()).hexdigest(),
}
(OUT/'symmetric_link_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
