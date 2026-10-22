"""Describe scenario sensitivity without selecting parameters by external accuracy."""
from pathlib import Path
import argparse,json,hashlib,itertools
import pandas as pd
import numpy as np
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(paths,output):
 output.mkdir(parents=True,exist_ok=True);data={};watched={};summary=[];canonical_use={};broad_counts=[]
 for directory in paths:
  manifest=json.loads((directory/'output_manifest.json').read_text());receipt=json.loads((directory/'run_receipt.json').read_text())
  if receipt['status']!='COMPUTED_PENDING_STRICT_SCIENTIFIC_DATA_REVIEW':raise ValueError('Unfinished scenario '+str(directory))
  frames={}
  for name in ['memberships','nodes','operational_type_candidates']:
   p=directory/(name+'.parquet')
   if sha(p)!=manifest['files'][p.name]['sha256']:raise ValueError('Unfrozen derivative '+str(p))
   watched[str(p)]=sha(p);frames[name]=pd.read_parquet(p)
  broad=frames['operational_type_candidates'];canonical=directory.parent.parent/'typology'/'canonical'/directory.name;canonical_use[directory.name]=False
  if (canonical/'manifest.json').exists():
   cm=json.loads((canonical/'manifest.json').read_text());cr=json.loads((canonical/'receipt.json').read_text())
   if cr['status']!='COMPUTED_LITERAL_TYPOLOGY_ADAPTER' or cm['model_output_manifest_sha256']!=sha(directory/'output_manifest.json') or cm['receipt_sha256']!=sha(canonical/'receipt.json'):raise ValueError('Canonical typology source binding invalid')
   for name,info in cm['files'].items():
    source=canonical/name
    if sha(source)!=info['sha256']:raise ValueError('Canonical derivative changed '+str(source))
    watched[str(source)]=sha(source)
   watched[str(canonical/'manifest.json')]=sha(canonical/'manifest.json');watched[str(canonical/'receipt.json')]=sha(canonical/'receipt.json');frames['operational_type_candidates']=pd.read_parquet(canonical/'operational_type_candidates.parquet');canonical_use[directory.name]=True
  for (lev,typ),g in broad.groupby(['level','word_type'],observed=True):broad_counts.append({'scenario':directory.name,'level':int(lev),'word_type':int(typ),'n_broad_measured_patterns':len(g)})
  n=frames['nodes'];m=frames['memberships'];base=n[['id','population_2021','_population_axis_row']].merge(m[['id']+[q for q in m if q.startswith('center_id_l')]],on='id',validate='one_to_one');levels=sorted(int(c.split('_l')[1]) for c in m if c.startswith('center_id_l'))
  label=directory.name;data[label]=(base,frames['operational_type_candidates'],levels)
  for level in levels:
   assigned=base[f'center_id_l{level}'].notna();axis=base._population_axis_row
   summary.append({'scenario':label,'level':level,'n_empirical_orders':max(levels),'uses_canonical_typology':canonical_use[label],'n_assigned_population_axis':int((assigned&axis).sum()),'n_unassigned_population_axis':int((~assigned&axis).sum()),'assigned_known_population2021':float(base.loc[assigned&axis,'population_2021'].sum()),'unassigned_known_population2021':float(base.loc[~assigned&axis,'population_2021'].sum()),'n_systems':int(base.loc[axis&assigned,f'center_id_l{level}'].nunique()),'n_roots_including_external_context':int(base[f'center_id_l{level}'].nunique()),'missing_population2021_rows':int((axis&base.population_2021.isna()).sum())})
 rows=[];shifts=[];type_changes=[]
 for a,b in itertools.combinations(data,2):
  aa,at,al=data[a];bb,bt,bl=data[b]
  if set(aa.id)!=set(bb.id):raise ValueError('Scenario axes differ; require an explicit matched-universe estimand')
  for view,la,lb in [('lowest',1,1),('highest',max(al),max(bl))]:
   ca=f'center_id_l{la}';cb=f'center_id_l{lb}';merged=aa[['id','_population_axis_row',ca]].rename(columns={ca:'a'}).merge(bb[['id',cb]].rename(columns={cb:'b'}),on='id',how='outer',validate='one_to_one');merged=merged[merged._population_axis_row.fillna(False)]
   both=merged.a.notna()&merged.b.notna();same=both&merged.a.eq(merged.b);joint=merged[both].groupby(['a','b'],observed=True).size();asize=merged.groupby('a',observed=True).size();bsize=merged.groupby('b',observed=True).size()
   if len(joint):
    ix=joint.index;union=ix.get_level_values(0).map(asize).to_numpy()+ix.get_level_values(1).map(bsize).to_numpy()-joint.to_numpy();j=pd.Series(joint.to_numpy()/union,index=ix);best=j.groupby(level=0,observed=True).max();weighted=float((best*asize.reindex(best.index)).sum()/asize.sum())
   else:weighted=None
   rows.append({'scenario_a':a,'scenario_b':b,'view':view,'level_a':la,'level_b':lb,'same_level_number':la==lb,'levels_are_homologous':False if la!=lb else None,'n_axis_union':len(merged),'n_both_assigned':int(both.sum()),'n_same_center':int(same.sum()),'same_center_fraction_among_both_assigned':float(same.sum()/both.sum()) if both.any() else None,'n_assignment_status_changed':int(merged.a.notna().ne(merged.b.notna()).sum()),'directional_a_best_partition_jaccard_weighted':weighted,'interpretation':'descriptive sensitivity; same level number does not establish homologous functional orders'})
   aset={(str(r.center_id),int(r.word_type)) for r in at[at.level.eq(la)].itertuples()};bset={(str(r.center_id),int(r.word_type)) for r in bt[bt.level.eq(lb)].itertuples()}
   type_changes.append({'scenario_a':a,'scenario_b':b,'view':view,'level_a':la,'level_b':lb,'n_center_type_pairs_a':len(aset),'n_center_type_pairs_b':len(bset),'n_same_center_type_pairs':len(aset&bset),'n_a_only_center_type_pairs':len(aset-bset),'n_b_only_center_type_pairs':len(bset-aset),'interpretation':'same-center descriptive hypothesis persistence, not geographic equivalence of changing systems'})
  for label,t in [(a,at),(b,bt)]:
   for (lev,typ),g in t.groupby(['level','word_type'],observed=True):shifts.append({'pair_a':a,'pair_b':b,'scenario':label,'level':int(lev),'word_type':int(typ),'n_hypotheses':len(g),'uses_canonical_typology':canonical_use[label]})
 pd.DataFrame(broad_counts).to_csv(output/'broad_prototype_counts.csv',index=False);pd.DataFrame(summary).to_csv(output/'scenario_coverage.csv',index=False);pd.DataFrame(rows).to_csv(output/'membership_stability.csv',index=False);pd.DataFrame(shifts).to_csv(output/'operational_type_counts.csv',index=False);pd.DataFrame(type_changes).to_csv(output/'operational_type_shifts.csv',index=False)
 (output/'receipt.json').write_text(json.dumps({'status':'COMPUTED_DESCRIPTIVE_SENSITIVITY_NOT_PARAMETER_SELECTION','input_sha256':watched,'code_sha256':sha(Path(__file__)),'scenarios':list(data),'uses_canonical_typology':canonical_use,'files':{q.name:{'sha256':sha(q)} for q in output.glob('*.csv')},'unknown_population_is_not_zero':True,'overlap_direction':'A best matching B partition, weighted by A membership size'},indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--scenario',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.scenario,a.output)
