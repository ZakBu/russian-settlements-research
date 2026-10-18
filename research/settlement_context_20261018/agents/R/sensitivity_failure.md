# Ошибка проверки sensitivity

2026-10-18, после получения locked final_lock.json и успешной побайтной сверкиSHA с actualfiles, попытка stdlib full CSVread `geo/exclude_drift/features.csv.gz` завершилась `EOFError: Compressed file ended before the end-of-stream marker was reached`.

Команда: `python research_staging/replication/check_sensitivity_mass.py`; exit1. Проверка variantmass НЕ завершена. Координатор и агентG немедленно уведомлены: SHA совпадение само по себе не гарантирует завершённость gzip; файл вероятно читался во времяrewrite. Требуется завершённая атомарная запись, полная gzip CRCread, finalSHA и поправкаlockдоrunner. Если finalrunner уже начат, запретитьlabelsreveal до объяснения.

Эта ошибка не затрагивает сохранённые mainfeatures и первичную независимуюE1репликацию; она использует selectedaxis,а не sensitivityfiles.

Уточнение отдельной записью: агентG подтвердил усечённыйgzip с141350полнымистроками, однако сообщил,что послеexit0 выполнялтолькочтение. Причина неизвестна; предполагаемыйrewrite не установлен. Утверждать,что конкретныйагент менялфайл,нельзя. Старыйcorruptpathсохраняется, recoveryпересчёт выполняется поуникальномупути и сatomicwrite+fullEOFCRCvalidation. ТребуетсяновыйlockfeatureSHA,старыйlockнепригоден дляdriftvariant.

Recoveryпроверка: unique `geo/exclude_drift_recovery/features.csv.gz` прочитанполностьюсgzipEOF/CRC. `check_sensitivity_mass.py` независимо сравнил14фокальныхUID (10изхешстратифицированнойвыборки+4flagged),2осиoriginal/drift,4радиуса,массуичисло:224точныхсравнения,0расхождений. Receipt`sensitivity_mass_comparison.json`. Старыйнеудачныйскриптсохранёнкак`check_sensitivity_mass_failed_v1.py`. Причинаповреждениястарогофайлапо-прежнемунеустановлена.
