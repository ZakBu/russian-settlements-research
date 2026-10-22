"""Keep every previously sourced external service relation on the national axis.

This source is a selected documentary corpus, not a national flow survey and
not a blind holdout. Nothing here is used to tune the national feature joins.
"""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
R=Path(__file__).resolve().parent;B=R.parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 out=R/'documented_evidence';out.mkdir(exist_ok=True)
 source=B/'functional_dynamics_20261019/model/results/canonical_documented_external_memberships.parquet'
 axis=B/'anchor_research_20261019/data/point_axis.parquet'
 a=pd.read_parquet(axis,columns=['id']);e=pd.read_parquet(source)
 assert len(e)==138 and e.counts_as_external_service_evidence.all() and not e.actual_flow_observed.any()
 assert e.origin_uid.isin(a.id).all() and e.destination_uid.isin(a.id).all()
 f=a.copy().set_index('id');gr=e.groupby('destination_uid')
 f['documented_external_service_destination']=f.index.isin(e.destination_uid)
 f['documented_external_service_assertions']=gr.size().reindex(f.index,fill_value=0).astype('int32')
 f['documented_external_origin_UIDs']=gr.origin_uid.nunique().reindex(f.index,fill_value=0).astype('int32')
 f['documented_external_function_groups']=gr.function_group.agg(lambda x:'|'.join(sorted(set(x)))).reindex(f.index).astype('string')
 f['documented_external_function_diversity']=gr.function_group.nunique().reindex(f.index,fill_value=0).astype('int8')
 f['documented_as_external_origin']=f.index.isin(e.origin_uid)
 f['documented_selected_corpus_complete_nationally']=False
 f['documented_actual_trips_measured']=False
 f['documented_actual_trip_count']=np.nan
 f['documented_no_record_means']='no_evidence_in_selected_corpus_not_no_external_function'
 f=f.reset_index();f.to_parquet(out/'documented_settlement_features.parquet',index=False,compression='zstd');f.to_csv(out/'documented_settlement_features.csv.gz',index=False,compression='gzip')
 # Exact source rows retained; census populations refer to reference residents,
 # not counts of pupils, patients or trips.
 e.to_parquet(out/'documented_external_relations.parquet',index=False,compression='zstd')
 z=f[f.documented_external_service_destination].merge(pd.read_parquet(axis,columns=['id','name','region','population_2021']),on='id',validate='one_to_one')
 phys=pd.read_parquet(R/'places/places_settlement_features.parquet');econ=pd.read_parquet(R/'economy/economy_features.parquet')
 cols=['id']+[f'places_{m}_{g}_count'for m in ['baseline','conditional']for g in ['school','preschool','other_education','hospital','healthcare']]
 z=z.merge(phys[cols],on='id',validate='one_to_one').merge(econ[['id','econ_native_2025_education85_legal_entities','econ_native_2025_health86_legal_entities']],on='id',validate='one_to_one')
 for fn,groups in [('education',['school','preschool','other_education']),('health',['hospital','healthcare'])]:
  for mode in ['baseline','conditional']:z[f'published_POI_{mode}_{fn}_witness']=z[[f'places_{mode}_{g}_count'for g in groups]].sum(axis=1).gt(0)
  z[f'documentary_{fn}_external_witness']=z.documented_external_function_groups.str.split('|').map(lambda x:fn in x)
  z[f'no_accepted_baseline_POI_{fn}_despite_document']=z[f'documentary_{fn}_external_witness']&~z[f'published_POI_baseline_{fn}_witness']
 z.to_csv(out/'documentary_vs_mass_sources.csv',index=False)
 checks={'all_axis_rows_once':len(f)==142570 and f.id.is_unique,'source138_retained':len(e)==138,'all17_documented_provider_UIDs_preserved':int(f.documented_external_service_destination.sum())==17,'source_relation_balance':int(f.documented_external_service_assertions.sum())==138,'no_flow_count_invented':f.documented_actual_trip_count.isna().all(),'source_axis_sha_matches_frozen':sha(axis)=='a2b5544c0d3c5581144a5439113a96c4a771697dc87a38c2abf979e1ead1467b'}
 assert all(checks.values());pd.testing.assert_frame_equal(f,pd.read_parquet(out/'documented_settlement_features.parquet'))
 result={'status':'PASS','axis_rows':len(f),'documentary_assertions':len(e),'destination_UIDs':int(e.destination_uid.nunique()),'origin_UIDs':int(e.origin_uid.nunique()),'unique_origin_destination_function_combinations':len(e.drop_duplicates(['origin_uid','destination_uid','function_group'])),'relations_with_measured_trip_counts':0,'documentary_function_dates':'source rows preserve dates; not a simultaneous national observation','comparison_scope':'Selected previously inspected providers; not random, blind or population-representative accuracy evaluation; no new labels used to tune mass linkage','checks':{k:bool(v)for k,v in checks.items()},'inputs_sha256':{str(source.relative_to(B)):sha(source),str(axis.relative_to(B)):sha(axis),'places':sha(R/'places/places_settlement_features.parquet'),'economy':sha(R/'economy/economy_features.parquet')},'outputs_sha256':{p.name:sha(p)for p in out.glob('*.parquet')}}
 (out/'AUDIT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
 (out/'README.md').write_text('''# Документированные внешние связи на общей оси

Все 138 ранее извлечённых канонических отношений сохранены отдельно и соединены с общей осью 142570UID. 17 населённых пунктов имеют документированное внешнее обслуживание: это преимущественно нормативные школьные прикрепления и заявления поставщика медицинской услуги. Они не являются измеренными поездками.

`documented_settlement_features.parquet` содержит всю ось; отсутствие записи значит отсутствие свидетельства в выбранном корпусе. `documented_external_relations.parquet` сохраняет все источники, даты и типы свидетельств. Разновременные повторения не суммируются как новые поездки. `documentary_vs_mass_sources.csv` показывает, видны ли функции этих поставщиков в массовом POI/RFSD-слое. Непопадание в POI не опровергает официальный акт, а свидетельствует об ограничении источника или связки.

Это последующее сопоставление выбранных примеров, не слепая контрольная выборка и не общероссийская оценка точности. Материал не использован для подбора национального правила связки. Основной master914 не изменён; дополнение соединяется строго1:1 поid.

Запуск: `python national_integration_20261019/build_documented_evidence.py` из общего рабочего корня. Исходный корпус и его первичные ссылки сохранены в прежней поставке functional_dynamics_20261019/model/results/.
''',encoding='utf-8')
if __name__=='__main__':main()
