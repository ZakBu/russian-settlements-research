"""Editorial integration only; no models or raw outcome access.
Run after final/evaluation.json and independently reviewed losses exist.
"""
import json
from pathlib import Path
import pandas as pd
S=Path(__file__).resolve().parents[1]
evalpath=S/'final/evaluation.json'
if not evalpath.exists():raise SystemExit('Final evaluation absent; manuscript not modified.')
j=json.loads(evalpath.read_text());assert j['status']=='computed_single_locked_reveal'
rows=[];paras=[]
for v in j['results']:
 met='brier' if v['task']=='zero' else 'mae';iv=v['interval'];b=v['baseline'][met];a=v['augmented'][met]
 rows.append({'configuration':v['id'],'task':v['task'],'baseline_loss':b,'augmented_loss':a,'delta':iv['delta'],'ci95_lower':iv['ci95'][0],'ci95_upper':iv['ci95'][1],'relative_gain_percent':100*v['relative_gain'],'n':iv['n_rows'],'blocks':iv['n_blocks'],'primary':v['primary']})
 if v['primary']:
  paras.append(f"**{v['id']}**: базовая ошибка {b:.9f}, расширенная {a:.9f}; Δ={iv['delta']:.9f}, относительное снижение {100*v['relative_gain']:.4f}%. Описательный условный 95%-й block-bootstrap интервал Δ: [{iv['ci95'][0]:.9f}; {iv['ci95'][1]:.9f}].")
  if 'training_refit_delta_quantiles' in v:
   q=v['training_refit_delta_quantiles'];paras.append(f"В {v['training_refit_replicates']} перевзвешенных fit-повторах квантили 2,5/50/97,5% разности равны {q[0]:.9f}/{q[1]:.9f}/{q[2]:.9f}. Это диагностика устойчивости обучения, не полный доверительный интервал эффекта.")
d=pd.DataFrame(rows);d.to_csv(S/'manuscript/final_results_table.csv',index=False)
intro=f"Единственное зафиксированное раскрытие текущего запуска завершено: {j['holdout_risk_n']} исходно положительных записей, {j['holdout_blocks']} пространственных блоков; {j['holdout_zero_n']} переходов к нулю. Предварительно сохранённый файл прогнозов имеет SHA-256 `{j['prediction_commitment_sha256']}`; SHA зафиксированного протокола `{j['lock_sha256']}`. Эти блоки ретроспективны, как раскрыто в разделе 4.3, и не называются исторически нетронутыми.\n\n"
text=intro+'\n\n'.join(paras)+'\n\nПолный ряд заранее фиксированных чувствительностей сохранён в `final_results_table.csv` и на рис.5; подмножества качества и внешних столичных зон — в `final/subgroup_sensitivity.csv`. Повторное использование одного holdout не создаёт независимых подтверждений. Ни интервалы, ни их отношение к порогу 2% не удостоверяют эффект, отсутствие эффекта или эквивалентность: диагностика зависимости между блоками демонстрирует возможность недопокрытия. После раскрытия модели и основные контрасты не переотбирались.\n\n**Статус независимой проверки:** см. receipts воспроизводителя. Получение evaluation.json само по себе не означает прохождения этой проверки.\n\n'
p=S/'manuscript/manuscript.md';t=p.read_text();start=t.index('**На момент этой версии не включена.**');end=t.index('### 5.4.',start);t=t[:start]+text+t[end:]
t=t.replace('Окончательный прогностический вывод оставлен до зафиксированной отложенной оценки и её независимой сверки.','Зафиксированная отложенная оценка приведена отдельно от разведки; её пределы и статус независимой сверки остаются обязательными условиями интерпретации.')
t=t.replace('Основные отложенные результаты будут включены после единственного фиксированного расчёта; раздел ниже намеренно отличает выполненную разведку от него.','Основные отложенные результаты включены из единственного фиксированного расчёта; раздел ниже отличает их от разведки. Независимая сверка устанавливается отдельным receipt.')
p.write_text(t)
print('Integrated editorial tables only; no models trained.')
