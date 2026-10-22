"""Exact accounting over fixed settlement identities; no imputed population."""
import numpy as np

def decompose(old_members,new_members,population_old,population_new):
    s0,s1=set(old_members),set(new_members)
    if any(k not in population_old or k not in population_new or not np.isfinite(population_old[k]) or not np.isfinite(population_new[k]) for k in s0|s1):
        return {'status':'incomplete_population_not_imputed'}
    common=s0&s1;added=s1-s0;removed=s0-s1
    summ=lambda ids,p:float(sum(p[k] for k in ids))
    total=summ(s1,population_new)-summ(s0,population_old)
    common_dynamics=summ(common,population_new)-summ(common,population_old)
    added_new=summ(added,population_new);removed_old=summ(removed,population_old)
    fixed_old_dynamics=summ(s0,population_new)-summ(s0,population_old)
    boundary_new=summ(s1,population_new)-summ(s0,population_new)
    assert np.isclose(total,common_dynamics+added_new-removed_old,rtol=0,atol=1e-9)
    assert np.isclose(total,fixed_old_dynamics+boundary_new,rtol=0,atol=1e-9)
    return dict(status='exact_complete_accounting',n_common=len(common),n_added=len(added),n_removed=len(removed),old_boundary_old_population=summ(s0,population_old),old_boundary_new_population=summ(s0,population_new),new_boundary_old_population=summ(s1,population_old),new_boundary_new_population=summ(s1,population_new),two_axis_total_difference=total,common_members_population_change=common_dynamics,added_members_new_population=added_new,removed_members_old_population=removed_old,fixed_old_boundary_population_change=fixed_old_dynamics,boundary_effect_at_new_population=boundary_new,accounting_residual=total-fixed_old_dynamics-boundary_new)

def self_test():
    # Overlap, entrants/exits, zeros and incomplete measurements have different outcomes.
    a={'a':10,'b':20,'c':0};b={'a':7,'b':25,'c':4}
    r=decompose({'a','b'},{'a','c'},a,b)
    assert r['two_axis_total_difference']==-19
    assert r['fixed_old_boundary_population_change']==2
    assert r['boundary_effect_at_new_population']==-21
    assert r['common_members_population_change']==-3
    assert r['added_members_new_population']==4
    assert r['removed_members_old_population']==20
    assert decompose(set(),set(),a,b)['two_axis_total_difference']==0
    assert decompose({'x'},set(),a,b)['status']=='incomplete_population_not_imputed'
    assert decompose({'a'},{'a'},a,b)['boundary_effect_at_new_population']==0
    assert decompose({'a'},{'c'},a,a)['fixed_old_boundary_population_change']==0
    return {'checks':10,'passed':10}

if __name__=='__main__':print(self_test())
