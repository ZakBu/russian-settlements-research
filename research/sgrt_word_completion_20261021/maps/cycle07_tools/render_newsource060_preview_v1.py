"""Actual accepted060 inspection pages only; does not substitute incomplete50-ledger with invented diagnostics."""
from pathlib import Path
import importlib.util,json,argparse,hashlib
P=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--config',required=True);ap.add_argument('--output',required=True);a=ap.parse_args();cp=Path(a.config);c=json.loads(cp.read_text());out=Path(a.output);assert not out.exists();assert c['status']=='ACTUAL_NEWSOURCE060_PREVIEW_ONLY_NOT_FULL_ATLAS';sp=importlib.util.spec_from_file_location('frozen_atlas_v6',P/'render_atlas_v6.py');r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r);code_sha=r.sha(P/'render_atlas_v6.py');ownsha=r.sha(__file__);cfgsha=r.sha(cp);n,u,z,watched=r.load(c,require_admission=True);out.mkdir(parents=True);atlas=r.Atlas(out,n,u,z,c,watched)
original_finish=atlas.finish
def finish_checkpoint(fig,title,caption,kind,metadata=None):
 coverage=(f'Всего в этом варианте: {len(z)} членств; {int(z._coordinate_valid.sum())} с координатами, {int((~z._coordinate_valid).sum())} без координат сохранены в журнале. ' if kind.startswith('national') else '')
 return original_finish(fig,title,'НОВЫЙ ИСТОЧНИКОВЫЙ ПРОХОД. Операционный дорожный охват 60 минут; не эмпирическая ступень. '+coverage+caption,kind,metadata)
atlas.finish=finish_checkpoint
try:
 atlas.textpage('СГРТ: новый источниковый проход, дорожный охват 60 минут',[
 'ФАКТИЧЕСКИЙ НОВЫЙ РАСЧЁТ. Принятые 477 координат, перепривязки учреждений и расширенные маршруты включены. Ведущий центр выбирается по максимальной фиксированной собственной массе среди всех центров объединения и сам должен удовлетворять прямому дорожному охвату. Это операционный сценарий; эмпирические ступени показываются отдельно после допуска реестра.',
 '353 новых первичных свидетельства населения2010 уже включены в исходную рамку. Повторное численное вмешательство исключено проверкой полного равенства исходных значений и качества. Полнота исторических границ этим не доказана.',
 f'Все {len(u)} единиц получили измеренный полный тип: {int(u.unit_role.eq("territorial_unit").sum())} территориальных объединений и {int(u.unit_role.ne("territorial_unit").sum())} отдельных исходных объектов. Полные {u.primary_type_id.nunique()} кодов сохранены; структурные цвета и бивариатная динамика являются явно обозначенными картографическими сводками.',
 f'Все {len(z)} членств сохранены: {int(z._coordinate_valid.sum())} нанесены по исходным координатам, {int((~z._coordinate_valid).sum())} без координат остаются в журнале. Географический состав:173856 обычныхНП и2 контекстных объекта; полный популяционный источник:173864 строки, иной знаменатель. Точки точно передают состав, но территориальные границы между ними неизвестны; линии схематические.',
 'Собственное население контекстных Москвы и Петербурга неизвестно в этой рамке. При любом таком участнике полнота всей системы запрещена, независимо от выбора ядра. Известные обычные и сельские итоги сохраняются; население субъекта не подменяет собственное население города.'
 ],'preview_scope')
 for level in c['retained_resolutions']:atlas.national(level);atlas.national_trajectories(level)
 atlas.zooms()
finally:atlas.close()
(out/'atlas_cycle07.pdf').rename(out/'actual060_preview.pdf');u.to_csv(out/'all_actual060_types.csv.gz',index=False,compression='gzip');z[['unit_id','id','level','is_overlay_membership','_coordinate_valid']].to_csv(out/'all_actual060_memberships.csv.gz',index=False,compression='gzip');assert all(r.sha(p)==s for p,s in watched.items()) and r.sha(cp)==cfgsha and r.sha(P/'render_atlas_v6.py')==code_sha and r.sha(__file__)==ownsha
receipt={'status':'COMPUTED_ACTUAL060_PREVIEW_PENDING_INDEPENDENT_VISUAL_REVIEW','actual_final_all5_all50_atlas':False,'scientific_word_completion_claimed':False,'renderer_sha256':code_sha,'preview_code_sha256':ownsha,'config_sha256':cfgsha,'sources':watched,'counts':{'source_nodes':len(n),'units':len(u),'membership_rows':len(z),'full_types':int(u.primary_type_id.nunique())},'source_integration_status':c['component_integration_status'],'resolution_kind':'operational_forest','registry_level':None,'candidate_cap':60,'partition_role':'supported_end_forest','page_count':len(atlas.pages),'pages':atlas.pages,'files':{p.name:r.sha(p) for p in out.iterdir() if p.is_file()}};(out/'preview_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'output':str(out),'pages':len(atlas.pages)}))
