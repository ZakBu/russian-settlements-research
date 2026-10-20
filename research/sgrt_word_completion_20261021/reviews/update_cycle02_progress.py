#!/usr/bin/env python3
"""Record actual independently verified partial criteria; never manufacture a final snapshot."""
from pathlib import Path
import hashlib,json
H=Path(__file__).resolve().parent;R=H.parents[2];N=H.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
a=json.loads((H/'cycle02_source_audit.json').read_text()); e=json.loads((H/'current_gate_evidence.json').read_text());checks={x['check']:x['pass'] for x in a['checks']}
assert a['n_failed']==0 and a['source_bytes_unchanged_during_review']
claims={
 'axis_independent_checks':{'pass':all(checks[k] for k in checks if k.startswith('legacy_') or k.startswith('axis_') or k=='located_coordinates_valid'),'scope':'173527 source entities; all legacy populations and 12 identity/quality fields preserved. This does not prove all new historical identities or national geographic completeness.'},
 'service_source_inventories_and_controls':{'pass':a['metrics']['services2021']['source_assertions']==456966 and a['metrics']['school']['2021']['source_school_rows']==30094 and a['metrics']['medical']['history_20210101']['healthcare_source_assertions']==30064,'scope':'Real source-object inventories with dated inputs, independently recomputed links/counts and unknown-preserving controls. This criterion passes inventory construction only; national functioning-service coverage, operation, actual capacity and link recall remain unaccepted.'},
 'municipal_identity_conflicts_separate':{'pass':checks['municipal_conflicting_values_not_selected'] and checks['municipal_multiple_raw_geographies_not_selected_without_equivalence'] and checks['conflicting_reported_natural_retained_in_separate_column'],'scope':'9674 numeric conflicts excluded; all multiple-native-code groups excluded without equivalence even if equal numbers. Raw reported natural retained separately from compatible derived balance. Historical boundary equivalence still unproven; not acceptance of downstream territorial aggregation.'},
 'functional_source_snapshots_dated':{'pass':a['metrics']['school']['2021']['snapshot']==['2021-01-01'] and a['metrics']['services2021']['snapshot']==['2021-01-01T21:42:03Z'],'scope':'Actual 2021 and current physical-source snapshots are distinct from census population dates. Current road2026 remains explicit network proxy. This passes date distinction, not comparability of changes or full service completeness.'}}
receipt={'target_run_id':e['target_run_id'],'reviewer':'strict_guardian','source_audit_sha256':sha(H/'cycle02_source_audit.json'),'claims':claims,'scientific_final_allowed':False,'all_source_checks_passed':a['n_failed']==0,'source_checks_count':a['n_checks']}
(H/'cycle02_verified_partial_criteria.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
receiptpath=str((H/'cycle02_verified_partial_criteria.json').relative_to(R)); receipthash=sha(H/'cycle02_verified_partial_criteria.json')
mapping={'W03':('independent_source_axis_checks','axis_independent_checks'),'W06':('mass_physical_function_inventories_with_source_controls','service_source_inventories_and_controls'),'W11':('identity_boundaries_and_conflicts_separate','municipal_identity_conflicts_separate'),'W23':('function_snapshot_and_population_dates_separate','functional_source_snapshots_dated')}
repairs={
'W02':'Сверить все source entities/неаддитивные записи/неразмещённые18558 по региону, типу и размеру; не суммировать пересекающиеся территориальные единицы.',
'W03':'Доказать источниковую идентичность новых записей и нули/пропуски по каждому году; проверить исторические территории и координатное происхождение.',
'W04':'Валидировать знаменатели/derived balance по rawcode и source interval; 2010migration реально отсутствует, не заменять2011. Отделить муниципальный контекст от НП и периода2010–2021.',
'W05':'Независимо проверить m²/среднегодового человека по raw муниципалитету и году, покрытие и влияние муниципальных повторов.',
'W06':'Проверить сельскую идентификацию на независимых официальных объектах, оценить отдельно recall источника/связки/модели; мощности/уровни не выводить из наличия OSMтега. Udmurt473официальныхНП vs27coordinate healthcare — несогласие источников, не доказательство закрытия.',
'W08':'Использовать аграрные муниципальные показатели как контекст на исходной территории; новая source-harmonized2008земля не доказывает valid2008boundary.',
'W09':'Добыть2010/2021сельхозугодья либо обосновать корректную доступную альтернативу; почвенный балл/проверяемый proxy. GAEZ SAT и летний P/PET получены для154968НП, климатический блок больше не отсутствует.',
'W10':'Дождаться маршрутов/isochrones; проверить направленность, snap, неполные пары vs unreachable, независимые время/барьеры; current2026networkproxy отдельно от2021среза.',
'W11':'Не объявлять boundaryequivalence на основании stablecode; metadata repaired, sourceconflicts исключены; закрепить хеши свежих modeljoinedinputs и проверить временные версии.',
'W12':'Независимо проверить2021prepared outputs, число доступных massblocks для каждого узла, sensitivity единыхблоков; источниковаянаблюдаемость ≠полнаяизмеримостькомпонента.',
'W13':'OwnP2021 и контекст2021 вмассе можно описывать ретроспективно, но регрессия2010–2021траектории содержит contemporaneous outcome/endogeneity: не выдавать за causal/prediction; отдельно baseline2010/missingdesign.',
'W23':'Проверить final2021bindings и road2026proxy в готовом report; изменения OSM между датами не означают реальные открытия/закрытия.',
'W25':'Сделать literal truthmatrix всех9Wordтипов, включая положение/агроклимат/размер/специализацию/механизм. UNKNOWN обязательного признака оставляет тип недоказанным. Тип7 не назначать Кубани, тип9 не получать из resource+decline.',
'W28':'Картографировать только actual final memberships/routes/types с показом unresolved/missing/источниковой уверенности, затем сверить легенды и суммы.',
'W31':'Отдельно проверять source recall/candidate recall/assignment; провал0/98 нельзя оправдать одной причиной покрытия без разбора идентичности/даты/функции.',
'W32':'Repair loop реально изменил данные и исправил axis/context; продолжать до independently verified Word gates, не подменять завершённость synthetic/computational PASS.'}
for rid,repair in repairs.items():
 rec=e['requirements'][rid];rec.update(state='IN_PROGRESS',implementation='IN_PROGRESS',data='IN_PROGRESS',scientific='NEEDS_REPAIR',author='research_team',reviewer='strict_guardian',next_repair=repair)
 rec['attempted_repairs']=['cycle02 independent data audit: 122/122 checks passed; source-provenance, arithmetic/linkage progress, not scientific acceptance']
for rid,(criterion,claim) in mapping.items():
 rec=e['requirements'][rid]; rec['criteria'][criterion]={'status':'PASS','verified_by':'strict_guardian','review_rationale':claims[claim]['scope'],'artifact':receiptpath,'sha256':receipthash,'assertions':[{'pointer':f'claims.{claim}.pass','operator':'eq','expected':True}],'source_artifacts':[{'artifact':str((N/f).relative_to(R)),'sha256':s} for f,s in a['reviewed_sha256'].items()]}
# Source versions are not a frozen final model snapshot. Leave model_snapshot null.
(H/'current_gate_evidence.json').write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'verified_partial_criteria':len(mapping),'source_checks':a['n_checks'],'target_run_id':e['target_run_id'],'final_snapshot_frozen':False}))
