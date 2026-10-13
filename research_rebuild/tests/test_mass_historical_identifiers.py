import pyarrow.parquet as pq
from research_rebuild.mass_linkage.historical_identifiers import normalize_exact_code,_claim_row,_write_parquet

def test_no_padding_and_no_invented_validity():
    assert normalize_exact_code('01012345001')==('01012345001','digits_only_exact')
    assert normalize_exact_code('1012345001.0')==('1012345001','digits_only_exact')
    r=_claim_row(claim_id='x',identifier_system='OKTMO',raw_code='1012345001')
    assert r['normalized_exact_code']=='1012345001'
    assert r['valid_from'] is None and r['valid_to'] is None
    assert r['binding_status']=='source_claim_only_not_identity_accepted'

def test_fias_uuid_does_not_use_numeric_classifier_normalization(tmp_path):
    u='E35C31F9-44B8-45D2-A273-72B949F243CC'
    r=_claim_row(claim_id='uuid',identifier_system='FIAS',raw_code=u)
    assert r['normalized_exact_code']==u.lower()
    assert r['raw_code']==u
    p=tmp_path/'claims.parquet';_write_parquet([r],p);s=pq.read_table(p).to_pylist()[0]
    assert s['normalized_exact_code']==u.lower()
    assert s['valid_from'] is None
    bad=_claim_row(identifier_system='FIAS',raw_code='not-a-valid-id')
    assert bad['normalized_exact_code'] is None and bad['raw_code']=='not-a-valid-id'
