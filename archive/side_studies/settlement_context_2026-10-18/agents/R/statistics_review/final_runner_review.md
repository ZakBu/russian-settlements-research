# Предварительное ревью final_runner до freeze

Ревью выполнено до final holdout labels. Ключевой порядок корректен: development labels → trainingmask → fit → сохранениеpredictions+SHAcommitment → holdoutlabels → losses. Присваивание zero=False приNaNtest не попадает в fit (trainmask исключаетtest), но явный NaNytest предпочтительнее читабельностью.

Требуемые поправки перед freeze переданы координатору:
1. Зафиксировать иassert SHA импортируемых model_executor.py и statistical_utils.py; runnerSHA не защищает их/PARAMS.
2. Проверить SHA original/drift variantinputs и точные CLIrefits/configids поlock.
3. Явная поправка протокола о двухfinalprimary E1/E2; E3 остановлен послеdevnegative, поэтому прежние3primary больше не формальноpre-registered3tests.
4. Явная поправка baseline: код использует nearest>=10k/>=100k и4радиуса, проектprotocol50k/100k+30km изменён.
5. Write-once guard: outputcommitments/revealmarker не должны существовать; markerдоlabelread, чтобыcrashпослеreveal не давалsilent rerun.

Не блокирует расчёт, но ограничивает вывод:
- Disk SHAcommitment передlabelread не является внешнеtimestampedGitcommit, если Gitcommit между ними не сделан.
-20reweightedtrainingblockfits HGB sampleweight не эквивалентны буквальному дублированиюobservations вbootstrap из-заhistogrambins/minleaf; этоstabilitydiagnostics.
- SpatialconditionalCI не калиброваныsimulation; p/Holmнеподтверждены. Дальняя пространственная зависимость,400km/regioncluster sensitivity отсутствует,если отдельно не выполнена.
- Placebo перестановка withinblock не является точнымconditionaltest; егоостаточныйsignalможет сохранятьсянаblockscale.

Рекомендация: условный допуск после устранения1–5, без подтверждающихp-формулировок и причинности.

## Повторное ревью

2026-10-18T17:45:16.574782+00:00 — все5запрошенныхguard/dependency/variant/config/refit/revealmarker поправки присутствуют. Runner SHA256 3ee6ab561aef0e06411952efd54894d9473547932255d5a18c508d8ee92be8b8. УсловныйPASS кfreeze при последующей сверке lock variantSHA и configids; block-reweightedfits корректно названы stabilitydiagnostics вinterpretation. Holdoutlabels ещё не просмотрены.
