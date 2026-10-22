"""Versioned compatibility/quality patch. Primary inputs are never modified.
The effective executed source is exported beside results for exact reproduction.
"""
from pathlib import Path
import hashlib,json,runpy
p=Path(__file__).with_name('run_pilot.py');text=p.read_text()
patches={
 'r=np.asarray(fit.resid);r-=r.mean()':'r=np.array(fit.resid,copy=True);r=r-r.mean()',
 "s['firm_context_density']=s.n_firms_2011/s.municipality_oktmo_code8.map(den)*1000":"s['firm_context_density']=s.n_firms_2011/s.municipality_oktmo_code8.map(den)*1000\ns.to_csv(ROOT/'prestat_sgrt_results.csv');d.to_csv(ROOT/'prestat_assigned_observations.csv.gz',index=False)",
 "s.loc[s.federal_context,'type_label']='Контекстный федеральный центр'":"s.loc[~np.isfinite(s.population_annual_2002_2021),'type_label']='Нет конечного положительного значения';s.loc[s.population_2021.eq(0),'type_label']='Обнуление населения';s.loc[s.federal_context,'type_label']='Контекстный федеральный центр'",
}
for old,new in patches.items():
 assert text.count(old)==1, 'Patch target must occur exactly once: '+old
 text=text.replace(old,new)
out=Path('pilot');out.mkdir(exist_ok=True)
(out/'effective_run_pilot.py').write_text(text)
(out/'execution_patch.json').write_text(json.dumps({'base_file':str(p),'base_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'effective_sha256':hashlib.sha256(text.encode()).hexdigest(),'changes':['copy residual array before centering (pandas 3 compatibility)','checkpoint table before statistical analysis','explicit non-finite/zero population type']},indent=2))
exec(compile(text,str(out/'effective_run_pilot.py'),'exec'),{'__name__':'__main__','__file__':str(out/'effective_run_pilot.py')})
