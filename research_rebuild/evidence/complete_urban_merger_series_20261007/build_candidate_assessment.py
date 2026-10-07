from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path
import duckdb
import pandas as pd

ROOT=Path('/workspace/russian-settlements-research')
OUT=ROOT/'research_rebuild/evidence/complete_urban_merger_series_20261007'
SEL=Path('/workspace/settlements-delivery/continuation-consolidated-20261003/selected_observations.parquet')
RAW=Path('/workspace/settlements-raw')
EVENT=ROOT/'research_rebuild/evidence/moscow_oblast_absorbed_city_events_20261005'
ACCEPTED=[Path('/workspace/settlements-work/continuation_20261004/root/accepted_large_inclusion6_zheleznodorozhny_scope/accepted_scoped_inclusion_references.json'),Path('/workspace/settlements-work/continuation_20261004/root/accepted_moscow_inclusion4_scope/accepted_scoped_inclusion_references.json')]
MIRROR=Path('/workspace/settlements-work/continuation_20261004/federal_and_history/zheleznodorozhny_scope_candidate/law209_sud.html')
PROPOSAL=Path('/workspace/settlements-work/continuation_20261004/regions/moscow_large_inclusions_v2/klimovsk_yubileyny_scope_proposal')
LEGAL=OUT/'legal_sources'
PDFS={
 '209_2014':LEGAL/'mosoblduma_2014_activity_overview_from_209_url.pdf',
 '103_2015':LEGAL/'mosoblduma_2015_activity_overview_from_103_url.pdf',
 '53_54_2014':LEGAL/'mosoblduma_12page_material_from_53_54_url.pdf',
}
OFFICIAL_URLS={
 '209_2014':'https://www.mosoblduma.ru/upload/site1/document_file/MpERPO3IaX.pdf',
 '103_2015':'https://www.mosoblduma.ru/upload/site1/document_file/ZT9mzaJrbw.pdf',
 '53_54_2014':'https://www.mosoblduma.ru/upload/site1/document_file/ZHY0wiu5hJ.pdf',
}

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()

def norm(x): return str(x or '').casefold().replace('ё','е').replace('ѐ','е').strip()

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 names=['балашиха','железнодорожный','никольско-архангельский','салтыковка','подольск','климовск','львовский','королёв','юбилейный','королѐв']
 q=f"""SELECT source_record_id,census_year,settlement_name,settlement_type,region_raw,district_raw,municipality_raw,population,population_scope,population_value_quality,source_file,source_sheet,source_row,source_name_raw,source_locator,oktmo,okato
FROM read_parquet(?) WHERE census_year IN (2002,2010,2021) AND lower(region_raw) IN ('московская','московская область') AND lower(replace(replace(settlement_name,'ё','е'),'ѐ','е')) IN ({','.join(repr(norm(n)) for n in names)}) ORDER BY census_year,settlement_name,source_record_id"""
 d=duckdb.connect().execute(q,[str(SEL)]).fetchdf()
 def group_for(r):
  n=norm(r.settlement_name); t=norm(r.settlement_type); y=int(r.census_year)
  if n in ('балашиха','железнодорожный','никольско-архангельский','салтыковка'):
   if n=='железнодорожный' and t!='город': return 'Balashikha_Zheleznodorozhny','homonym_control_not_member'
   return 'Balashikha_Zheleznodorozhny',('possible_early_urban_constituent_membership_unverified' if n in ('никольско-архангельский','салтыковка') else 'candidate_city_member_membership_unverified')
  if n in ('подольск','климовск','львовский'):
   return 'Podolsk_Klimovsk_Lvovskiy',('candidate_city_member_membership_unverified' if n!='подольск' else 'candidate_city_member_membership_unverified')
  if n in ('королев','юбилейный'):
   return 'Korolev_Yubileiny','candidate_city_member_membership_unverified'
  return '', 'out_of_scope'
 d[['candidate_group','membership_status']]=d.apply(lambda r:pd.Series(group_for(r)),axis=1)
 d['source_file_sha256']=d.source_file.map(lambda x:sha(RAW/str(x)) if (RAW/str(x)).is_file() else '')
 d['source_row_locator']=d.apply(lambda r: f"{r.source_file}#{r.source_sheet}!row={r.source_row}",axis=1)
 d['population_is_component_observation_only']=True
 d['group_total_computed']=False
 d.to_csv(OUT/'candidate_census_observations.csv',index=False)

 laws=[]
 title_hint={'209_2014':'2014 Duma activity overview (contains a summary mention of Law 209; not the statute text)',
             '103_2015':'2015 Duma activity overview (contains a summary mention of Law 103; not the statute text)',
             '53_54_2014':'12-page Duma material PDF with meeting/municipal content and references to Laws 53/54; not a complete statute or boundary annex'}
 for key,p in PDFS.items():
  laws.append({'law_reference':key,'law_as_claimed_in_accepted_event_manifest':key.replace('_','/'),'official_url_from_accepted_manifest':OFFICIAL_URLS[key],
               'downloaded_bytes_path':str(p),'downloaded_sha256':sha(p),'downloaded_bytes':p.stat().st_size,
               'downloaded_content_assessment':title_hint[key],'actual_legal_act_text_verified':False,
               'settlement_level_constituent_roster_in_asset':False,'physical_city_boundary_schedule_in_asset':False})
 law_inventory={
  'status':'official_resource_urls_return_duma_overview_assets_not_complete_law_texts',
  'law_assets':laws,
  'cached_209_text':{'path':str(MIRROR),'sha256':sha(MIRROR),'source':'third-party mirror, not authenticated official publication',
                     'article_scope':'Article 1 merges Balashikha and Zheleznodorozhny as administrative-territorial units; does not list settlements or prove census population scope.'},
  'other_cached_law_texts':{'53_2014':'not found; existing Klimovsk/Yubileiny proposal cites secondary web pages only','54_2014':'not found; cited Rossiyskaya Gazeta legal-publication URL returned HTTP 403','103_2015':'not found; Duma PDF URL returned the 2015 activity overview'},
  'prior_direct_access_results':{'209_2014_mosreg_and_doc':'HTTP 403 per existing Zheleznodorozhny scope review receipt','209_2014_mosoblduma_pdf_api':'HTTP 502 per existing Zheleznodorozhny scope review receipt','54_2014_rg_cited_in_wikitext':'HTTP 403 from bounded direct header request'},
  'official_duma_pdf_fetch_urls':OFFICIAL_URLS,
  'legal_scope_conclusion':'The existing accepted event references establish historical city-to-successor context but do not provide a verified full list of historical physical urban constituents or a final 2021 city-boundary crosswalk.'}
 (OUT/'legal_source_inventory.json').write_text(json.dumps(law_inventory,ensure_ascii=False,indent=2)+'\n')

 group_data=[
  {'group':'Balashikha_Zheleznodorozhny','candidate_members_2002':['Балашиха (город)','Железнодорожный (город)','Никольско-Архангельский (пгт)','Салтыковка (пгт)'],'candidate_members_2010':['Балашиха (город)','Железнодорожный (город)'],'successor_city_2021':'Балашиха (город)','status':'HOLD_INCOMPLETE_PHYSICAL_SCOPE_PROOF','specific_gap':'2002 has two extra urban-type rows (Nikolsko-Arkhangelsky, Saltykovka) that are absent as separate rows in 2010; no verified act establishes when/how their counts map into Balashikha. Law 209 text available only in third-party mirror here concerns administrative-territorial units, not settlement-level scope. The 2021 city row is not a dated act or crosswalk for the complete historical urban group.'},
  {'group':'Podolsk_Klimovsk_Lvovskiy','candidate_members_2002':['Подольск (город)','Климовск (город)','Львовский (пгт)'],'candidate_members_2010':['Подольск (город)','Климовск (город)','Львовский (пгт)'],'successor_city_2021':'Подольск (город)','status':'HOLD_INCOMPLETE_PHYSICAL_SCOPE_PROOF','specific_gap':'Lvovskiy remains a separate 2010 pgt observation. The 103/2015 actual text/boundary schedule is not staged; official Duma URL returned an annual review summary. No evidence binds Lvovskiy or every urban constituent of the abolished Podolsk district to the 2021 physical city row.'},
  {'group':'Korolev_Yubileiny','candidate_members_2002':['Королёв (город)','Юбилейный (город)'],'candidate_members_2010':['Королёв (город)','Юбилейный (город)'],'successor_city_2021':'Королёв (город)','status':'HOLD_ACTUAL_ACT_AND_SCOPE_LINK_UNVERIFIED','specific_gap':'Census candidate roster is two named city rows, but accepted references mark legal acts independently unverified. Cached official Duma assets are activity-review materials, not full laws/maps; no verified law 53/54 boundary attachment or direct crosswalk proves that the 2021 physical city row is the complete corresponding union.'},
 ]
 decisions=pd.DataFrame(group_data)
 decisions['complete_urban_group_sum_published']=False
 decisions['population_imputed']=False
 decisions['partial_sum_emitted']=False
 decisions['boundary_comparability_asserted']=False
 decisions['2021_parent_or_municipality_total_used']=False
 decisions['candidate_point_coordinates_published']=False
 decisions.to_csv(OUT/'group_completeness_decisions.csv',index=False)
 inputs=[SEL,EVENT/'accepted_series.csv',EVENT/'source_manifest.json',EVENT/'event_aware_coverage.json',*ACCEPTED,MIRROR,PROPOSAL/'proposal.json',PROPOSAL/'receipt.json']
 manifest={'status':'candidate_only_three_groups_all_held_for_complete_constituent_scope','scope':3,
           'inputs_sha256':{str(p):sha(p) for p in inputs},
           'primary_census_source_sha256':{
            '/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls':sha(Path('/workspace/settlements-raw/data/raw/2002_official_tom1/1_TOM_01_04.xls')),
            '/workspace/settlements-raw/data/raw/2010_official_tom11/pub-11-1-4.pdf':sha(Path('/workspace/settlements-raw/data/raw/2010_official_tom11/pub-11-1-4.pdf')),
            '/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls':sha(Path('/workspace/settlements-raw/data/raw/2010/010_711691e352_2._20Kostrom_Kur_Lip_Moscow_MoscObl_Orlov_2010.xls')),
            '/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet':sha(Path('/workspace/settlements-raw/data/interim/2021_tochno/data_allsettlements_anon_156_v20251217.parquet'))},
           'law_asset_sha256':{k:sha(v) for k,v in PDFS.items()},
           'outputs_sha256':{n:sha(OUT/n) for n in ['candidate_census_observations.csv','group_completeness_decisions.csv','legal_source_inventory.json','README.md']},
           'no_group_population_sums_or_points_emitted':True,'canonical_graph_unchanged':True}
 (OUT/'source_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'rows':len(d),'groups':decisions[['group','status']].to_dict('records'),'law_assets':[(x['law_reference'],x['downloaded_bytes'],x['downloaded_sha256']) for x in laws]},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
