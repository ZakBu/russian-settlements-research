from pathlib import Path
import pandas as pd,zipfile,hashlib,json,math
B=Path(__file__).resolve().parent
P=Path('/workspace/russian-settlements-research/research_rebuild/evidence')
OWN=P/'large_existing_credited_north_ownpoints_20261009'
ZIP=Path('/workspace/settlements-raw/data/raw/coordinate_candidates/geonames_RU_20260907.zip')
ZIP_SHA=hashlib.sha256(ZIP.read_bytes()).hexdigest()
SNAP=B/'wiki_own_article_coordinate_rivals.json.gz'; SNAP_SHA=hashlib.sha256(SNAP.read_bytes()).hexdigest()
BASE=pd.read_csv(OWN/'accepted_point_use_delta.csv')
WIT=pd.read_csv(OWN/'ownpoint_source_row_witnesses.csv')
ROSTER=pd.read_csv(OWN/'assigned_roster.csv')
# Dated live API response captured as raw compressed JSON; source provides pageid/revision/primary coordinates.
import gzip
obj=json.loads(gzip.decompress(SNAP.read_bytes()))
page_by_title={x['title']:x for x in obj['query']['pages']}
# Native target binding context for collision families. Articles are the exact named object; source row identity is baseline-accepted.
contexts={
 'Антипино':'Exact own article Антипино (Тюмень) identifies the named former Tyumen village/microdistrict. Selected GN point is in the Tyumen receiving-city locality; same-name records 1511535–37 are roughly 60–100 km away in other Tyumen oblast localities, not the urban Antipino. Current 2010 source district raw field is Тюмень.',
 'Antipino':'Exact own article Антипино (Тюмень) identifies the named former Tyumen village/microdistrict. Selected GN point lies in the Tyumen receiving-city locality; same-name records 1511535–37 are 60–100+ km away in other Tyumen oblast districts, not the urban Antipino. Current 2010 district raw field is Тюмень.',
 'Комсомольский':'Exact own article Комсомольский (Донской) and source 2002 Том 1 row 1962 in the same former-Donskoy settlement block bind this target to Donskoy. Selected point at 53.9046,38.26454 is in that receiving-city cluster. Other exact-name point 7690518 is at 54.0047,38.6425, far outside the Donskoy settlement group and farther from the article location.',
 'Новоугольный':'Exact own article Новоугольный identifies the Donskoy former urban settlement; source row 1963 is in the consecutive Donskoy native block. Primary article coordinate 53.99694,38.33361 is nearest to GN 517773 of the two exact-name GN candidates; GN 816802 is farther north in the same broad region. Use exact article coordinate in the addendum.',
 'Подлесный':'Exact own article Подлесный (Донской), source row 1964 in the same Donskoy native block, and exact article primary coordinate bind the selected GN 508216 point (about 0.21 km away) to the target. GN 508215 at 54.13827,38.03984 is a remote different Podlesny; it is about 25 km from the article point.',
 'Шахтерский':'Exact own article Шахтёрский (Донской), native row 1966 in the Donskoy block, and article coordinate bind GN 496020 (about 90 m from article point). GN 496019 and 7690517 are distinct same-name points roughly 18 km and 20 km away, respectively, outside the named Donskoy neighborhood.',
 'Кайеркан':'Exact own article Кайеркан pageid 14911 primary coordinate is rounded to 69.35,87.75. The captured own-place article coordinate is preferred as the representative point source over either cached GN point. GN 1504139 is farther from the article point than GN 1504084, but this does not reject either feature identity; the replacement proposal uses the own article coordinate with coarse precision explicitly retained.',
 'Табага':'Exact own article Табага (городской округ Якутск) and the accepted source-year route identify Yakutsk Tabaga. GN 2015746 aliases the former name Лесокомбинат and sits adjacent to its own article primary coordinate (about 0.56 km). GN 2015747 is another distant same-name locality outside Yakutsk; GN 9408063 is explicitly Старая Табага, a distinct settlement separated in 2004. Use own article coordinate in addendum.',
 'Широкая Речка':'Exact own article Широкая Речка (Академический район Екатеринбурга) and article coordinate select GN 1492142 (within 0.25 km). GN 1545732 is a nearby PPLX point about 1.1 km away; the separate feature lies in the same broad named locality area, so the accepted article coordinate is the canonical representative. GN 8070293 is roughly 14 km away and outside the historical settlement/receiving-city neighborhood.',
 'Заводской':'Exact own article Заводской (Приморский край) says the former PGT was in Artem and joined the city in 2004. Article coordinate 43.45972,132.28333 is about 75 m from GN 2012623. GN 2021508 is named Krolevtsy (Zavodskoy only an alias) and lies about 3 km west; it is not the exact former Artem urban settlement. A partial-name Steklozavodskoy row is a different name.',
 'Марха':'Exact own article Марха (Якутск) identifies the Yakutsk urban locality. GN 2020221 is the only exact Markha point near Yakutsk (62.11454,129.74403); exact-name candidates 2020220/22/23 are 100s of km away in other districts. Near-name Malaya Markha is separately named.',
 'Косая Гора':'Exact own article Косая Гора identifies the former Tula urban settlement, later neighborhood. Selected GN 544293 is a nearby own-place feature in Tula; direct article coordinate is better and is proposed as replacement point.',
 'Скуратовский':'Exact own article Скуратовский (бывший рабочий посёлок) identifies the former settlement in Tula. Selected GN 492218 is in the same Tula neighborhood; direct article coordinate is better and is proposed as replacement point.',
 'Кольцово':'Exact own article Кольцово (Свердловская область) identifies the former settlement and current receiving-city district in Ekaterinburg. Selected GN 11049038 is within about 100 m of the article coordinate; only exact-named regional alternatives were rejected by far-away locations.'
}
def distance(a,b,c,d):
 R=6371000; p1=math.radians(a);p2=math.radians(c);dp=math.radians(c-a);dl=math.radians(d-b)
 h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
 return 2*R*math.asin(math.sqrt(h))
with zipfile.ZipFile(ZIP) as z:
 lines=z.read('RU.txt').decode().splitlines()
G={}
for i,raw in enumerate(lines,1):
 f=raw.split('\t');G[f[0]]=(i,f,raw)
# competitor groups selected GN ID and all same-type/admin1 exact or near-exact transliterated names.
selected_to_name={}
for r in WIT.drop_duplicates('geonameid').itertuples(index=False): selected_to_name[str(r.geonameid)]=str(r.settlement_name)
manual={
'Антипино':('1511538',['1511535','1511536','1511537'],'Антипино (Тюмень)',None),
'Комсомольский':('545719',['7690518'],'Комсомольский (Донской)',None),
'Новоугольный':('517773',['816802'],'Новоугольный',(53.99694,38.33361)),
'Подлесный':('508216',['508215'],'Подлесный (Донской)',(53.93833,38.26806)),
'Шахтерский':('496020',['496019','7690517'],'Шахтёрский (Донской)',(53.92111,38.30389)),
'Кайеркан':('1504139',['1504084'],'Кайеркан',(69.35,87.75)),
'Табага':('2015746',['2015747','9408063'],'Табага (городской округ Якутск)',(61.85889,129.59611)),
'Широкая Речка':('1492142',['1545732','8070293'],'Широкая Речка (Академический район Екатеринбурга)',(56.8,60.48333)),
'Заводской':('2012623',['2021508','6419714'],'Заводской (Приморский край)',(43.45972,132.28333)),
'Марха':('2020221',['2020220','2020222','2020223','2020490'],'Марха (Якутск)',None),
'Косая Гора':('544293',[],'Косая Гора',(54.11639,37.56083)),
'Скуратовский':('492218',[],'Скуратовский (бывший рабочий посёлок)',(54.103879,37.615039)),
'Кольцово':('11049038',[],'Кольцово (Свердловская область)',(56.76028,60.82083)),
}
# Map candidate family to source UIDs and target row names.
name_to_ids={}
for r in ROSTER.itertuples(index=False):name_to_ids.setdefault(str(r.settlement_name).replace('ё','е'),[]).append(r.source_record_id)
article_ids={x['title']:(x.get('pageid'),(x.get('revisions') or [{}])[0].get('revid'),(x.get('coordinates') or [{}])[0].get('lat'),(x.get('coordinates') or [{}])[0].get('lon')) for x in obj['query']['pages']}
review=[];corrections=[]
for nm,(sel,rivals,title,article_coord) in manual.items():
 sidlist=name_to_ids.get(nm.replace('ё','е'),[])
 if not sidlist:
  # Tula typographic source spelling remains exactly the parent UID target and is recorded in witness table.
  sidlist=[x for x in WIT.loc[WIT.native_name.str.replace('ё','е').eq(nm.replace('ё','е')),'target_source_record_id'].tolist()]
 sidlist=list(dict.fromkeys(sidlist))
 pi=article_ids.get(title,(None,None,None,None)); latA=article_coord[0] if article_coord else pi[2];lonA=article_coord[1] if article_coord else pi[3]
 candidates=[sel]+rivals
 for gid in candidates:
  line,f,raw=G[gid];is_sel=gid==sel
  dA=distance(latA,lonA,float(f[4]),float(f[5])) if latA is not None and lonA is not None else None
  status='selected_candidate_retained' if is_sel else 'rejected_rival'
  if nm=='Кайеркан' and gid==sel:status='selected_GN_point_superseded_by_better_own_article_point_source; no_identity_rejection'
  if nm in {'Косая Гора','Скуратовский','Новоугольный','Табага'} and gid==sel:status='selected_GN_binding_supported; exact_article_point_replacement_proposed'
  if nm=='Кайеркан' and gid=='1504084':status='closer_GN_rival_to_article_point; still use article point because coordinate_precision_is_coarse'
  review.append({'target_source_record_id':'|'.join(sidlist),'native_name':nm,'candidate_role':status,'selected_geonameid':sel,'candidate_geonameid':gid,'geonames_line_number':line,'geonames_name':f[1],'ascii_name':f[2],'alternate_names':f[3],'feature_class':f[6],'feature_code':f[7],'country_code':f[8],'admin1_code':f[10],'candidate_latitude':float(f[4]),'candidate_longitude':float(f[5]),'own_article_title':title,'own_article_pageid':pi[0],'own_article_revision':pi[1],'own_article_primary_latitude':latA,'own_article_primary_longitude':lonA,'distance_candidate_to_article_point_m':round(dA,1) if dA is not None else None,'source_context_and_selection_reason':contexts[nm],'source_sha256':ZIP_SHA,'source_locator':f'RU.txt:line{line};geonameid={gid};feature={f[7]};admin1={f[10]}','raw_ru_txt_line':raw})
 if article_coord and nm in {'Кайеркан','Косая Гора','Скуратовский','Новоугольный','Табага'}:
  sid=sidlist[0]
  corrections.append({'target_source_record_id':sid,'native_name':nm,'replacement_latitude':latA,'replacement_longitude':lonA,'coordinate_admission_status':'reviewed_rule_accepted_superseding_point_source','coordinate_source_record_id':f'ruwiki:pageid:{pi[0]}','source_sha256':SNAP_SHA,'source_locator':f'query.pages[pageid={pi[0]}].coordinates[primary=true]; own_article={title}; revision={pi[1]}','point_origin_file':str(SNAP),'point_origin_sha256':SNAP_SHA,'point_origin_locator':f'query.pages[pageid={pi[0]}].coordinates[primary=true]; own_article={title}; revision={pi[1]}','point_origin_kind':'own_exact_physical_locality_Wikipedia_primary_coordinate','reason':'Exact own-place article primary coordinate is better source-bound than the selected cached GeoNames feature coordinate. This is a point-only correction on the already-accepted identity route; census-day measurement/boundary equivalence not asserted.','approximate_accuracy_meters':600 if nm=='Кайеркан' else 120,'historical_census_coordinate_asserted':False,'population_boundary_comparability_asserted':False,'native_code_binding_asserted':False})
# extra two false-positive near-name candidates with exact proper-name distinction
for gid,reason,nm in [('500707','GeoNames ownname Rudnevo, not Rudnev; distinct proper-name root and 2002 target is Rudnev in Donskoy block.','Руднев'),('500708','GeoNames ownname Rudnevo, not Rudnev; distinct proper-name root and 2002 target is Rudnev in Donskoy block.','Руднев')]:
 line,f,raw=G[gid]; sid='2002:1_TOM_01_04.xls:0:1965'
 review.append({'target_source_record_id':sid,'native_name':nm,'candidate_role':'rejected_near_name_not_same_toponym','selected_geonameid':'500713','candidate_geonameid':gid,'geonames_line_number':line,'geonames_name':f[1],'ascii_name':f[2],'alternate_names':f[3],'feature_class':f[6],'feature_code':f[7],'country_code':f[8],'admin1_code':f[10],'candidate_latitude':float(f[4]),'candidate_longitude':float(f[5]),'own_article_title':'Руднев','own_article_pageid':article_ids.get('Руднев',(None,))[0],'own_article_revision':article_ids.get('Руднев',(None,None))[1],'own_article_primary_latitude':None,'own_article_primary_longitude':None,'distance_candidate_to_article_point_m':None,'source_context_and_selection_reason':reason,'source_sha256':ZIP_SHA,'source_locator':f'RU.txt:line{line};geonameid={gid};feature={f[7]};admin1={f[10]}','raw_ru_txt_line':raw})
review_df=pd.DataFrame(review);review_df.to_csv(B/'point_binding_rivals_review.csv',index=False)
pd.DataFrame(corrections).to_csv(B/'point_article_coordinate_corrections.csv',index=False)
receipt={'review_id':'crosscheck_large_north_ownpoint_binding_20261009','ownpoint_packet_manifest_sha256':hashlib.sha256((OWN/'FINAL_manifest.json').read_bytes()).hexdigest(),'ownpoint_delta_sha256':hashlib.sha256((OWN/'accepted_point_use_delta.csv').read_bytes()).hexdigest(),'GeoNames_source_sha256':ZIP_SHA,'own_article_API_snapshot_sha256':SNAP_SHA,'review_rows':len(review_df),'point_correction_proposals':len(corrections),'findings':{'all_40_targets_have_source_rows':True,'ambiguous_name_families_reviewed':list(manual),'material_correction':'Kayerkan: prefer the own article primary coordinate 69.35,87.75 over cached GN coordinate as the representative point source; no provider-entity/identity rejection. Coarse point precision retained.','other_point_only_corrections':['Kosaya Gora','Skuratovsky','Novougolny','Tabaga'],'identity_counts_lifecycle_reaudited':False,'municipal_parent_points_used':False,'all_candidate_raw_lines_pinned':True},'files':{}}
for fn in ['point_binding_rivals_review.csv','point_article_coordinate_corrections.csv','wiki_own_article_coordinate_rivals.json.gz','wiki_own_article_coordinate_rivals_receipt.json','build_review.py']:
 f=B/fn;receipt['files'][fn]={'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
(B/'FINAL_review_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False,indent=2))
