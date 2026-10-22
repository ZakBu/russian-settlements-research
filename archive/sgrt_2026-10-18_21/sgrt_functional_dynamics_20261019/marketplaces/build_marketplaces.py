"""Rebuild physical parcel evidence from frozen primary-source snapshots.

No opening dates or inter-settlement flows are inferred. API versions are not dates.
"""
from pathlib import Path
import argparse, collections, gzip, hashlib, json, re, unicodedata
import fitz
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

ROOT = Path(__file__).resolve().parent
WB_URL = 'https://static-basket-01.wbbasket.ru/vol0/data/all-poo-fr-v11.json'
PP_URL = 'https://pickpoint.ru/files/files/%D0%B3%D1%80%D0%B0%D1%84%D0%B8%D0%BA%20%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D1%8B%20%D0%9F%D0%92%D0%97%20PickPoint_%D1%84%D0%B5%D0%B2%D1%80%D0%B0%D0%BB%D1%8C%202021.pdf'
HSE_URL = 'https://www.hse.ru/data/2025/05/01/2005892985/%D0%A1%D0%B5%D0%BC%D0%B8%D0%BD%D0%B0%D1%80%206-%D0%9F%D0%92%D0%97.pdf'
PILOTS = {'65714000': 'Невьянский', '65715000': 'Нижнетуринский', '28630000': 'Конаковский', '80653000': 'Учалинский'}

def norm(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s-]', ' ', unicodedata.normalize('NFKC', str(s)).casefold().replace('ё','е'))).strip()

def address_head(s):
    # Street names are not evidence of the settlement name.
    return re.split(r'\b(?:улица|ул\.?|проспект|пр-кт|переулок|пер\.?|шоссе|бульвар|площадь|проезд|набережная)\b', norm(s), maxsplit=1)[0]

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def source_bytes(name):
    p=ROOT/'sources'/name
    return p.read_bytes() if p.exists() else gzip.decompress((ROOT/'sources'/(name+'.gz')).read_bytes())

def wb_extract(axis):
    raw = json.loads(source_bytes('wb_all_points_v11.json'))
    ru = next(x['items'] for x in raw if x['country']=='ru')
    rows=[]
    for x in ru:
        xy=x.get('coordinates', [None,None])
        rows.append(dict(object_id='wb:'+str(x['id']), source_object_id=x['id'], brand='Wildberries',
            function_group='marketplace_pickup', service_level='parcel_pickup', address=x.get('address'),
            latitude=xy[0], longitude=xy[1], observed_date='2026-10-19', opening_date=None,
            source_id='WB_CDN_V11', source_url=WB_URL, source_country='ru', typePoint=x.get('typePoint'),
            source_status=x.get('status'),
            fitting_rooms=x.get('fittingRooms'), work_time=x.get('workTime'),
            evidence_status=('provider_published_PVZ_focus' if x.get('typePoint') in (8,34) else 'provider_published_delivery_location_unknown_subtype'),
            focus_scope=x.get('typePoint') in (8,34),
            source_type_interpretation=('WB_or_partner_PVZ_focus' if x.get('typePoint') in (8,34) else 'postal_or_other_unclassified_delivery_location'),
            external_catchment_evidence=False))
    frame=pd.DataFrame(rows)
    assert frame.object_id.is_unique
    assert frame.latitude.between(-90,90).all() and frame.longitude.between(-180,180).all()
    frame.to_parquet(ROOT/'wb_source_only_ru_20261019.parquet',index=False)
    # The join has TWO requirements: literal name in the pre-street address and coordinate concordance.
    # A nearest point alone is never accepted. Multiple same-name candidates are preserved as ambiguous.
    axis=axis.copy();axis['name_norm']=axis.name.map(norm)
    axis_names=axis.name_norm.to_numpy()
    name_patterns={n:re.compile(r'(?<!\w)'+re.escape(n)+r'(?!\w)') for n in axis_names if len(n)>=3}
    tree=BallTree(np.deg2rad(axis[['lat','lon']].to_numpy()),metric='haversine')
    q=np.deg2rad(frame[['latitude','longitude']].to_numpy())
    ind,dist=tree.query_radius(q,r=10/6371,return_distance=True,sort_results=True)
    links=[]
    for (_,r),ix,dd in zip(frame.iterrows(),ind,dist):
        head=address_head(r.address)
        candidates=[]
        for k,d in zip(ix,dd):
            n=axis_names[k]
            if len(n)<3 or not name_patterns[n].search(head):continue
            p=axis.iloc[k]
            if re.search(r'\b(?:село|с)\s+'+re.escape(n)+r'(?!\w)',head) and norm(p.type)!='село':continue
            if re.search(r'\b(?:город|г)\s+'+re.escape(n)+r'(?!\w)',head) and norm(p.type)!='город':continue
            if re.search(r'\bдеревня\s'+re.escape(n)+r'(?!\w)',head) and norm(p.type)!='деревня':continue
            candidates.append((p,d*6371))
        # Longer names prevent 'Нижняя' from matching 'Нижняя Тура'.
        if candidates:
            ml=max(len(p.name_norm) for p,d in candidates)
            candidates=[(p,d)for p,d in candidates if len(p.name_norm)==ml]
        status='name_coordinate_concordance' if len(candidates)==1 else 'ambiguous_name_coordinates' if candidates else 'unresolved'
        z=dict(object_id=r.object_id, link_status=status, candidate_count=len(candidates), settlement_uid=None,
               settlement_name=None, region=None, municipality_oktmo8_2021=None, settlement_axis_distance_km=None)
        if len(candidates)==1:
            p,d=candidates[0];z.update(settlement_uid=p.id,settlement_name=p['name'],region=p.region,
               municipality_oktmo8_2021=str(p.municipality_oktmo8_2021),settlement_axis_distance_km=d)
        z['candidate_uids']='|'.join(p.id for p,d in candidates)
        links.append(z)
    links=pd.DataFrame(links);joined=frame.merge(links,on='object_id',validate='one_to_one')
    joined.to_parquet(ROOT/'wb_delivery_locations_ru_20261019.parquet',index=False)
    links.to_csv(ROOT/'wb_settlement_links.csv',index=False)
    focus=joined[joined.focus_scope].copy()
    focus.to_parquet(ROOT/'wb_pvz_focus_ru_20261019.parquet',index=False)
    pilot=focus[focus.municipality_oktmo8_2021.isin(PILOTS)].copy()
    pilot['pilot']=pilot.municipality_oktmo8_2021.map(PILOTS)
    pilot.to_csv(ROOT/'wb_pilot_objects.csv',index=False)
    all_pilot=joined[joined.municipality_oktmo8_2021.isin(PILOTS)].copy()
    all_pilot['pilot']=all_pilot.municipality_oktmo8_2021.map(PILOTS)
    all_pilot.to_csv(ROOT/'wb_pilot_all_delivery_locations.csv',index=False)
    # Candidate-only nearby geometry for unresolved names is useful for auditing, not node allocation.
    summary=focus.groupby(['link_status'],dropna=False).size().to_dict()
    counts=pilot.groupby(['pilot','settlement_uid','settlement_name'],dropna=False).agg(objects=('object_id','size'),fitting_rooms=('fitting_rooms','sum')).reset_index()
    counts.to_csv(ROOT/'wb_pilot_settlement_counts.csv',index=False)
    all_counts=all_pilot.groupby(['pilot','settlement_uid','settlement_name'],dropna=False).agg(
        published_delivery_locations=('object_id','size'),focus_8_34=('focus_scope','sum'),
        source_type_codes=('typePoint',lambda z:'|'.join(map(str,sorted(set(z)))))).reset_index()
    all_counts.to_csv(ROOT/'wb_pilot_all_settlement_counts.csv',index=False)
    return joined,all_pilot,dict(countries={c['country']:len(c['items'])for c in raw}, russia_records=len(ru),
      russia_unique_ids=int(frame.object_id.nunique()),focus_records=len(focus),focus_link_counts=summary,
      russian_typePoint_counts={str(k):int(v)for k,v in frame.typePoint.value_counts().items()},
      pilot_records=len(pilot),pilot_settlements=int(pilot.settlement_uid.nunique()),
      all_types_pilot_records=len(all_pilot),all_types_pilot_settlements=int(all_pilot.settlement_uid.nunique()),
      all_types_pilot_counts=all_pilot.groupby('pilot').size().to_dict(),
      duplicate_coordinates=int(frame.duplicated(['latitude','longitude'],keep=False).sum()),
      coordinate_axis='source coordinates[0]=latitude, coordinates[1]=longitude; verified against named pilot towns')

def pickpoint_extract(axis):
    doc=fitz.open(ROOT/'sources/pickpoint_february_2021.pdf')
    rows=[]
    for page_no,p in enumerate(doc,1):
        words=p.get_text('words')
        starts=sorted(w[1] for w in words if 180<w[0]<365 and w[4]=='ПВЗ:')
        for i,y in enumerate(starts):
            y2=starts[i+1]-.4 if i+1<len(starts) else p.rect.height
            chunks=[]
            for x0,x1 in [(20,180),(180,365),(365,580),(580,656),(656,735),(735,820)]:
                w=sorted([w for w in words if x0<=w[0]<x1 and y-1.3<=w[1]<y2],key=lambda w:(round(w[1],1),w[0]))
                chunks.append(' '.join(x[4]for x in w))
            reg,name,address,*times=chunks
            if not name.startswith('ПВЗ:'):continue
            sm=re.match(r'\d{6},\s*([^,]+)',address)
            settlement=sm.group(1).strip()if sm else None
            rows.append(dict(object_id='pickpoint202102:'+str(page_no)+':'+str(i+1),function_group='marketplace_pickup',
              service_level='parcel_pickup',brand='PickPoint_partner_network',operator_label=name,address=address,
              settlement_name=settlement,source_region=reg,observed_date='2021-02-20',opening_date=None,
              source_id='PICKPOINT_FEB2021',source_url=PP_URL,source_page=page_no,
              schedule_20210220=times[0],schedule_20210222=times[1],schedule_20210223=times[2],
              evidence_status='provider_published_dated_schedule',external_catchment_evidence=False))
    frame=pd.DataFrame(rows)
    # Keep the entire extracted factual address table, no invented zero for missing towns.
    frame.to_csv(ROOT/'pickpoint_extracted_202102.csv',index=False)
    wanted=['Невьянск','Нижняя Тура','Конаково','Учалы','Павлово','Ворсма','Богородск','Навашино','Кулебаки','Вача','Муром','Выкса']
    pilot=frame[frame.settlement_name.isin(wanted)].copy()
    pilot['settlement_uid']=None
    for idx,r in pilot.iterrows():
        a=axis[axis.name.eq(r.settlement_name)]
        region={'Невьянск':'свердловская','Нижняя Тура':'свердловская','Конаково':'тверская','Учалы':'башкортостан','Муром':'владимирская'}.get(r.settlement_name,'нижегородская')
        a=a[a.region.eq(region)&a.type.eq('город')]
        if len(a)==1:pilot.loc[idx,'settlement_uid']=a.iloc[0].id
    pilot.to_csv(ROOT/'pickpoint_pilot_objects_202102.csv',index=False)
    return pilot,dict(extracted_records=len(frame),pages=len(doc),pilot_records=len(pilot),pilot_by_settlement=pilot.settlement_name.value_counts().to_dict())

def hse_counts(axis):
    # Literal numeric table from slide 9. Rechecked against the PDF render.
    source=[('Павлово',19,17,5,2),('Ворсма',5,4,0,0),('Богородск',13,9,4,1),('Навашино',5,5,1,1),('Кулебаки',12,10,2,2),('Вача',1,3,1,1),('Муром',40,37,12,4),('Выкса',26,23,5,3)]
    rows=[]
    for city,*values in source:
        reg='владимирская'if city=='Муром'else'нижегородская'
        a=axis[(axis.name==city)&(axis.region==reg)]
        for brand,n in zip(['Wildberries','Ozon','Яндекс.Маркет','Мегамаркет'],values):
            rows.append(dict(settlement_name=city,region=reg,settlement_uid=a.iloc[0].id if len(a)==1 else None,
              brand=brand,count=n,observation_year=2025,presented_date='2025-04-19',exact_census_date_unknown=True,
              source_page=9,source_id='MSU_HSE_PVZ2025',source_url=HSE_URL,
              evidence_status='field_research_published_aggregate',physical_object_ids_available=False,external_catchment_evidence=False))
    f=pd.DataFrame(rows);f.to_csv(ROOT/'lower_poochye_counts_2025.csv',index=False)
    return dict(records=len(f),total_points=int(f['count'].sum()),by_brand=f.groupby('brand')['count'].sum().to_dict())

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--axis',type=Path,default=ROOT.parent.parent/'anchor_research_20261019/data/point_axis.parquet');args=ap.parse_args()
    axis=pd.read_parquet(args.axis)
    wb,pilot,wa=wb_extract(axis);pp,pa=pickpoint_extract(axis);ha=hse_counts(axis)
    # No double counting across dates. This table is an observation ledger, not a simultaneous supply census.
    out=pilot.copy();out['source_page']=None
    obj=pd.concat([out,pp],ignore_index=True)
    obj.to_csv(ROOT/'objects.csv',index=False)
    obj.to_parquet(ROOT/'objects.parquet',index=False)
    audit={'wb':wa,'pickpoint':pa,'msu_hse':ha,'axis_sha256':sha(args.axis),
      'source_sha256':{p.name:sha(p)for p in (ROOT/'sources').iterdir()if p.suffix in ['.pdf','.json']},
      'notes':['No dates of opening inferred.','No external trips or catchments inferred.','API versions are NOT historical snapshots.',
               'country=ru is the provider service section, not a territorial Russia mask; it includes Barentsburg Svalbard.',
               'A small number of provider status codes 1/3 are retained without assuming their operational meaning.',
               'Point-axis joins use literal names and 10 km coordinate concordance. They are not legal boundary containment.',
               'PickPoint schedule is neither the complete parcel market nor a historical WB/Ozon census.']}
    (ROOT/'AUDIT.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
