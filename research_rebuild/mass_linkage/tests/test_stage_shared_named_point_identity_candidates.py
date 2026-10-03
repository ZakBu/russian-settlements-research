import pandas as pd

from research_rebuild.mass_linkage.stage_shared_named_point_identity_candidates import select_sample


def test_sample_is_bounded_and_keeps_targeted_and_seeded_strata_distinct():
    rows=[]
    for i in range(100):
        rows.append({"edge_id":f"e{i:03}","pair_population_max":1000-i,"from_region_norm":f"r{i%55}",
                     "has_zero_population":i in {20,21,22,23,24,25},
                     "has_source_row_hold":i in {40,41,42,43,44,45},
                     "raw_name_or_region_normalization_diff":i in {30,31,32,33,34,35,36,37,38,39}})
    sample=select_sample(pd.DataFrame(rows))
    assert len(sample)<=60
    assert sample.edge_id.is_unique
    labels=[set(__import__('json').loads(x)) for x in sample.sample_strata]
    assert any("targeted_top_population" in x for x in labels)
    assert any("targeted_zero_population" in x for x in labels)
    assert any("targeted_raw_name_or_region_difference" in x for x in labels)
    assert any("seeded_random_region_strata" in x for x in labels)
    assert any("seeded_random_ordinary" in x for x in labels)
    assert select_sample(pd.DataFrame(rows)).edge_id.tolist()==sample.edge_id.tolist()


def test_inter_endpoint_difference_is_separate_from_common_type_prefix_normalization():
    df=pd.DataFrame([{"from_name":"Новоселье","to_name":"Новоселье","from_region":"псковская область","to_region":"псковская область","from_region_norm":"псковская","to_region_norm":"псковская","from_type":"село","to_type":"село"},
                     {"from_name":"Старое","to_name":"Старая","from_region":"регион","to_region":"регион","from_region_norm":"регион","to_region_norm":"регион","from_type":"село","to_type":"село"}])
    diff=df.from_name.ne(df.to_name)|df.from_region.ne(df.to_region)
    assert diff.tolist()==[False,True]
