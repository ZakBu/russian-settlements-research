"""Complete measured classification; no hierarchy learning, population repair or Word gating."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import pandas as pd
import numpy as np

HERE=Path(__file__).resolve().parent
PERIODS=((2002,2010),(2010,2021),(2002,2021))
LABELS={'growth':'рост','stable':'стабильность','decline':'убыль','extinction_observed':'наблюдаемое обнуление','emergence_observed':'рост из наблюдаемого нуля','observed_zero_both':'оба наблюдения нулевые','unavailable':'динамика недоступна','not_applicable':'не применимо'}
STRUCTURES={'atomic_settlement':'отдельное поселение','rural_zone':'система с сельским окружением','local_without_rural_zone':'локальная система без сельского окружения','rural_composition_unknown':'система с неустановленным составом окружения','external_context':'неаддитивный внешний контекст','superregional_overlay':'надрегиональное перекрывающееся объединение','protected_carry':'защищённая переносимая строка'}
for _base in ('rural_zone','local_without_rural_zone','rural_composition_unknown'):
    STRUCTURES['multicenter_'+_base]='многоцентровая '+STRUCTURES[_base]

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def truth(v):
    if pd.isna(v): return None
    if isinstance(v,(bool,np.bool_)): return bool(v)
    raise ValueError(f'Expected nullable boolean, got {v!r}')
def number(v):
    if pd.isna(v): return None
    if isinstance(v,(bool,np.bool_)): raise ValueError('Boolean population')
    x=float(v)
    if not math.isfinite(x) or x<0: return None
    return x

def admitted(review):
    assert str(review.get('status','')).startswith('ACCEPTED'),'Review status is not ACCEPTED'
    for field in ('n_failures','n_failed','failed_checks'):
        if field in review: assert review[field]==0,f'Admission has failures: {field}'
    assert review.get('all_checks_passed') is True or review.get('n_failed')==0 or review.get('n_failures')==0,'No explicit successful checks'

def state(a,b,complete_a,complete_b,years,delta=.0025,applicable=True):
    if applicable is False: return 'not_applicable',None
    if applicable is None: return 'unavailable',None
    a,b=number(a),number(b)
    if truth(complete_a) is not True or truth(complete_b) is not True or a is None or b is None: return 'unavailable',None
    if a==0: return ('observed_zero_both' if b==0 else 'emergence_observed'),None
    if b==0: return 'extinction_observed',-1.
    rate=math.expm1((math.log(b)-math.log(a))/years)
    # Tiny numerical error at preregistered threshold must not switch an equality.
    if math.isclose(abs(rate),delta,rel_tol=1e-10,abs_tol=1e-14): return 'stable',rate
    return ('growth' if rate>delta else 'decline' if rate < -delta else 'stable'),rate

def structural(row,c):
    kind=str(row[c['kind_column']])
    if kind not in ('atomic_settlement','functional_union','external_context_anchor','superregional_overlay'): raise ValueError(f'Unknown unit kind {kind}')
    role=str(row[c['unit_role_column']])
    if role not in ('territorial_unit','protected_carry','context_overlay'): raise ValueError(f'Unknown unit role {role}')
    if role=='protected_carry': return 'protected_carry'
    if kind=='atomic_settlement': return kind
    if kind=='external_context_anchor': return 'external_context'
    if kind=='superregional_overlay': return kind
    if kind!='functional_union': raise ValueError(f'Unrecognised unit kind: {kind}')
    nr=number(row[c['rural_member_count_column']]); nu=number(row[c['unknown_role_member_count_column']])
    if nr is None or nu is None: return 'rural_composition_unknown'
    if nr>0: return 'rural_zone' if nu==0 else 'rural_composition_unknown'
    return 'local_without_rural_zone' if nu==0 else 'rural_composition_unknown'

def key(structure,states): return 'T:'+structure+'|'+','.join(f'{obj}={st}' for obj,st in states.items())
def name(structure,states): return STRUCTURES[structure]+': '+ '; '.join(f'{obj} — {LABELS[st]}' for obj,st in states.items())

def classify(frame,c,delta=.0025):
    idcol=c['unit_id_column']
    assert frame[idcol].notna().all() and frame[idcol].is_unique,'unit_id missing/duplicate'
    objects=c['objects']; required=[idcol,c['kind_column'],c['level_column'],c['rural_member_count_column'],c['unknown_role_member_count_column'],c['unit_role_column'],c['central_object_ids_column'],c['central_object_definition_column']]
    for spec in objects.values():
        for year in (2002,2010,2021): required.extend([spec['population'][str(year)],spec['complete'][str(year)]])
    required.extend(c['quality_columns'])
    if c.get('unit_name_column'): required.append(c['unit_name_column'])
    required.extend(x['column'] for x in c.get('context_witnesses',[]))
    absent=set(required)-set(frame)
    if absent: raise ValueError(f'Missing declared input columns: {sorted(absent)}')
    records=[]; evidence=[]
    for _,row in frame.iterrows():
        uid=str(row[idcol]); structure=structural(row,c)
        central_ids=json.loads(row[c['central_object_ids_column']])
        definition=str(row[c['central_object_definition_column']])
        if not isinstance(central_ids,list) or any(not isinstance(x,str) or not x for x in central_ids) or len(set(central_ids))!=len(central_ids): raise ValueError('Invalid central object ID set')
        if definition not in ('own_atomic','one_focal_core','all_supported_cores','not_applicable'): raise ValueError('Invalid central object definition')
        if definition in ('own_atomic','one_focal_core') and len(central_ids)!=1: raise ValueError('Singleton central object required')
        if definition=='all_supported_cores' and not central_ids: raise ValueError('Empty supported core set')
        if definition=='not_applicable' and central_ids: raise ValueError('Nonapplicable central object must have empty ID set')
        if definition=='all_supported_cores' and len(central_ids)>1 and structure in ('rural_zone','local_without_rural_zone','rural_composition_unknown'): structure='multicenter_'+structure
        atomic=str(row[c['kind_column']])=='atomic_settlement'
        active=['own'] if atomic else ['center','rural','system']
        missing=set(active)-set(objects)
        if missing: raise ValueError(f'Object contract missing {missing}')
        recent={}; applicability={}; allstates=[]; nobs=0; napplicable=0; nsupport=0; alternatives={}
        quality={k: (None if pd.isna(row[k]) else row[k].item() if hasattr(row[k],'item') else row[k]) for k in c['quality_columns']}
        for obj in active:
            spec=objects[obj]
            applicable=not(obj=='rural' and structure.endswith('local_without_rural_zone'))
            if spec.get('applicable_column'):
                applicable=False if applicable is False else truth(row[spec['applicable_column']])
            applicability[obj]=applicable
            for a,b in PERIODS:
                pa,pb=row[spec['population'][str(a)]],row[spec['population'][str(b)]]
                ca,cb=row[spec['complete'][str(a)]],row[spec['complete'][str(b)]]
                # Unknown member roles forbid treating the rural lower bound as a complete series.
                if obj=='rural' and number(row[c['unknown_role_member_count_column']])!=0:
                    ca=cb=False
                st,rate=state(pa,pb,ca,cb,b-a,delta,applicable)
                allstates.append(f'{obj}:{a}-{b}={st}')
                if st not in ('unavailable','not_applicable'): nsupport+=1
                evidence.append({'unit_id':uid,'object':obj,'period':f'{a}-{b}','start_year':a,'end_year':b,'start_population_raw':pa,'end_population_raw':pb,'start_complete':ca,'end_complete':cb,'applicable':applicable,'annual_rate':rate,'state':st,'delta':delta,'population_source_columns':json.dumps([spec['population'][str(a)],spec['population'][str(b)]])})
                if (a,b)==(2010,2021):
                    recent[obj]=st; napplicable+=int(applicable is not False)
                    nobs+=int(st not in ('unavailable','not_applicable'))
        for alt in (0.,.005):
            altstates={}
            for obj in active:
                spec=objects[obj]; applicable=applicability[obj]
                ca=row[spec['complete']['2010']]; cb=row[spec['complete']['2021']]
                if obj=='rural' and number(row[c['unknown_role_member_count_column']])!=0: ca=cb=False
                altstates[obj]=state(row[spec['population']['2010']],row[spec['population']['2021']],ca,cb,11,alt,applicable)[0]
            k=key(structure,altstates)
            if k!=key(structure,recent): alternatives[str(alt)]=k
        witnesses=[]
        for w in c.get('context_witnesses',[]):
            v=row[w['column']]
            if pd.isna(v): continue
            positive=truth(v) is True if w['kind']=='boolean' else number(v) is not None and number(v)>0
            if positive: witnesses.append(w['label'])
        witnesses=sorted(set(witnesses)); context='|'.join(witnesses) if witnesses else 'no_positive_witness_in_available_sources'
        adverse=[]
        for q in c.get('quality_uncertainty_rules',[]):
            v=row[q['column']]
            if q['rule']=='not_true': flag=truth(v) is not True
            elif q['rule']=='positive_or_missing': flag=number(v) is None or number(v)>0
            else: raise ValueError('Unknown quality rule')
            if flag: adverse.append(q['label'])
        confidence='structural_only' if nobs==0 else 'partial_demographic_support' if nobs<napplicable else 'tentative_source_quality' if adverse else 'source_supported_numeric'
        pk=key(structure,recent)
        records.append({'unit_id':uid,'unit_name':str(row[c['unit_name_column']]) if c.get('unit_name_column') and pd.notna(row[c['unit_name_column']]) else uid,'level':row[c['level_column']],'structural_class':structure,'primary_type_id':pk,'primary_type_name':name(structure,recent),'trajectory_class':json.dumps(recent,ensure_ascii=False),'trajectory_all_periods':';'.join(allstates),'functional_context':context,'complete_profile_id':pk+'|context='+context,'classification_confidence':confidence,'observed_dimension_count':nobs,'applicable_dimension_count':napplicable,'observed_object_period_count':nsupport,'source_quality':json.dumps(quality,ensure_ascii=False,default=str),'source_quality_flags':json.dumps(adverse,ensure_ascii=False),'alternative_type':json.dumps(alternatives,ensure_ascii=False),'central_object_definition':definition,'central_object_ids':json.dumps(sorted(central_ids)),'unit_role':row[c['unit_role_column']],'n_underlying_object_series':nobs,'statistical_independence_claimed':False,'historical_boundary_equivalence_claimed':False})
    result=pd.DataFrame(records); ev=pd.DataFrame(evidence)
    assert len(result)==len(frame) and set(result.unit_id)==set(frame[idcol].astype(str))
    assert result.unit_id.is_unique and result.primary_type_id.notna().all() and result.primary_type_name.str.len().gt(0).all()
    return result,ev

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--contract',required=True); ap.add_argument('--output',required=True); a=ap.parse_args()
    cp=Path(a.contract).resolve(); c=json.loads(cp.read_text()); out=Path(a.output)
    if out.exists(): raise FileExistsError('Fresh output directory required')
    p=Path(c['units_path']); assert sha(p)==c['units_sha256'],'Units SHA changed'
    rp=Path(c['protocol_admission_path']); assert sha(rp)==c['protocol_admission_sha256']
    review=json.loads(rp.read_text()); admitted(review); assert review['all_checks_passed'] is True
    assert review['accepted_protocol_sha256']==sha(HERE/'PROTOCOL.md'),'Protocol not admitted'
    assert review['accepted_classifier_sha256']==sha(__file__),'Classifier version not admitted'
    central_audit=Path(c['central_set_audit_path']); assert sha(central_audit)==c['central_set_audit_sha256']
    central_review=json.loads(central_audit.read_text()); admitted(central_review); assert central_review['all_checks_passed'] is True
    assert central_review['units_sha256']==c['units_sha256']
    assert central_review['rural_excludes_exact_central_set'] is True and central_review['whole_members_counted_once'] is True
    if not c.get('quality_uncertainty_rules'): raise ValueError('Explicit source-quality uncertainty policy required')
    hierarchy_review_path=Path(c['hierarchy_admission_path']);assert sha(hierarchy_review_path)==c['hierarchy_admission_sha256']
    hierarchy_review=json.loads(hierarchy_review_path.read_text());admitted(hierarchy_review)
    assert hierarchy_review.get('accepted_units_sha256',hierarchy_review.get('units_sha256'))==c['units_sha256'],'Hierarchy admission not bound to exact unit table'
    assert c['source_admissions'],'Source admissions may not be empty'
    for source in c['source_admissions']:
        sp=Path(source['path']); assert sha(sp)==source['sha256']
        sr=json.loads(sp.read_text());admitted(sr)
        for field,value in source['required_fields'].items(): assert sr[field]==value
    watched={str(f.resolve()):sha(f) for f in (p,cp,rp,central_audit,HERE/'PROTOCOL.md',Path(__file__),hierarchy_review_path)}
    for source in c['source_admissions']: watched[str(Path(source['path']).resolve())]=source['sha256']
    version=c['population_source_version']
    if version['mode'] not in ('accepted_base_no_new_overlay','admitted_versioned_overlay'): raise ValueError('Unspecified population source version')
    assert central_review['nodes_sha256']==version['effective_nodes_sha256'],'Central audit uses different population version'
    if version['mode']=='admitted_versioned_overlay':
        op=Path(version['overlay_path']); ar=Path(version['admission_path'])
        assert sha(op)==version['overlay_sha256'] and sha(ar)==version['admission_sha256']
        oa=json.loads(ar.read_text()); admitted(oa); assert oa['all_checks_passed'] is True
        assert oa['accepted_overlay_sha256']==sha(op)
        for field in version['unit_quality_change_columns']: assert field in c['quality_columns'],'Overlay quality changes must be retained'
        assert version['unit_quality_change_columns'],'Per-unit recovery counts/shares required'
        watched[str(op.resolve())]=sha(op);watched[str(ar.resolve())]=sha(ar)
    else:
        assert version['base_nodes_sha256']==version['effective_nodes_sha256']
    for w in c.get('context_witnesses',[]):
        assert w['kind'] in ('boolean','positive_count') and all(w.get(k) for k in ('source','year','grain','absence_is_unknown'))
    if c['primary_annual_delta']!=.0025: raise ValueError('Primary threshold must retain preregistered 0.25%')
    frame=pd.read_parquet(p); result,evidence=classify(frame,c)
    for f,s in watched.items(): assert sha(f)==s,f'Input changed during classification: {f}'
    out.mkdir(parents=True); result.to_parquet(out/'complete_typology.parquet',index=False); evidence.to_parquet(out/'trajectory_evidence.parquet',index=False)
    result.groupby(['unit_role','level','primary_type_id','primary_type_name'],dropna=False).size().rename('n_units').reset_index().to_csv(out/'type_counts.csv',index=False)
    result.sort_values('unit_id').groupby(['primary_type_id','classification_confidence'],dropna=False).head(1).to_parquet(out/'case_chart_selection.parquet',index=False)
    receipt={'status':'COMPUTED_COMPLETE_MEASURED_PARTITION_NOT_CAUSAL_TYPES','n_units':len(result),'n_types':result.primary_type_id.nunique(),'unit_role_counts':result.unit_role.value_counts().to_dict(),'n_territorial_units':int(result.unit_role.eq('territorial_unit').sum()),'all_units_classified':True,'input_units_sha256':sha(p),'contract_sha256':sha(cp),'classifier_sha256':sha(__file__),'protocol_sha256':sha(HERE/'PROTOCOL.md'),'protocol_admission_sha256':sha(rp),'delta':.0025,'source_admissions':c['source_admissions'],'population_source_version':version,'watched_input_sha256':watched,'input_unchanged':sha(p)==c['units_sha256'],'files':{f.name:sha(f) for f in out.iterdir() if f.is_file()}}
    (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)); print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__': main()
