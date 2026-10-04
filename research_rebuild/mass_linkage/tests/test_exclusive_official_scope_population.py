"""Regress actual protected-source and partition overlap found in the ninth run."""
from research_rebuild.mass_linkage.measure_scoped_joint_coverage_eighth_20261004 import exclusive_official_source_projection

def observation(sid,year,pop,counterpart='',aliases='[]'):
    return dict(source_record_id=sid,census_year=year,population=pop,preferred_same_census_alternate_selected_source_record_id=counterpart,same_census_source_alias_record_ids=aliases)

def test_trudovoe_already_linked_2021_is_not_new_population():
    sid='2021:data_allsettlements_anon_156_v20251217.parquet:parquet:100072'
    before={sid:19543,'another_place':100}
    after,_,_,_=exclusive_official_source_projection(before,2021,[observation(sid,2021,19543,sid)],[])
    assert sum(after.values())==sum(before.values())
    assert before=={sid:19543,'another_place':100}

def test_official_trudovoe_replaces_protected_assertion_only_in_view():
    old='2010:009_81f8a0e73c_17._20ДВ_ФО_2010.xls:ДВ:565';new='ROSSTAT2010:T5:p199:l277'
    before={old:18495,'another_place':100}
    after,removed,excluded,_=exclusive_official_source_projection(before,2010,[observation(new,2010,18522,old)],[])
    assert sum(after.values())-sum(before.values())==27
    assert old not in after and old in excluded and removed[old]==18495
    assert before[old]==18495

def test_kushchevskaya_whole_is_exclusive_of_both_parts():
    a='2002:036_81b258bc42_02c_Krasnodarski-krai.xls:11:1276';b='2002:036_81b258bc42_02c_Krasnodarski-krai.xls:11:1332'
    before={a:22680,b:6853,'another_place':100}
    after,removed,excluded,_=exclusive_official_source_projection(before,2002,[observation('ROSSTAT2002:T4:01-04:r4338',2002,29533)],[a,b])
    assert sum(after.values())==sum(before.values())
    assert set(removed)==excluded=={a,b}
    assert a not in after and b not in after
