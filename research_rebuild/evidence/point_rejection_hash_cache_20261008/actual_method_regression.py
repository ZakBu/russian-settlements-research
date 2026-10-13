"""Exercise the checked-in State.reject_point_uses method without constructing State."""
from pathlib import Path
import hashlib
import sys
import tempfile
from unittest.mock import patch
import pandas as pd

ROOT = Path('/workspace/russian-settlements-research')
sys.path.insert(0, str(ROOT / 'research_rebuild' / 'mass_linkage'))
import current_chain_state_20261007 as live


def digest(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def rows_csv(path, ledger, expected, second_expected=None):
    data=[
      {"target_source_record_id":"a","rejection_status":"reviewed_superseded_representative_point_only","old_latitude":1.0,"old_longitude":2.0,"origin_ledger":str(ledger),"origin_ledger_sha256":expected},
      {"target_source_record_id":"b","rejection_status":"reviewed_superseded_representative_point_only","old_latitude":3.0,"old_longitude":4.0,"origin_ledger":str(ledger),"origin_ledger_sha256":expected if second_expected is None else second_expected},
    ]
    pd.DataFrame(data).to_csv(path,index=False)


def fixture(ledger):
    s=live.State.__new__(live.State)
    s.point_rows={"a":{"latitude":1.0,"longitude":2.0,"point_ledger_path":str(ledger)},"b":{"latitude":3.0,"longitude":4.0,"point_ledger_path":str(ledger)}}
    s.conflicting_point_targets={"a","b"};s.inputs=[]
    return s


def main():
  with tempfile.TemporaryDirectory() as td:
    td=Path(td);ledger=td/'ledger.parquet';ledger.write_bytes(b'ledger first bytes');good=digest(ledger)
    calls=[]
    def counted(p):calls.append(str(p));return digest(p)
    # Same ledger in two valid rows is read once within this method invocation.
    p=td/'valid.csv';rows_csv(p,ledger,good);s=fixture(ledger)
    with patch.object(live,'sha',side_effect=counted):s.reject_point_uses(p)
    assert calls==[str(ledger)] and not s.point_rows and not s.conflicting_point_targets and s.inputs==[p]

    # Cached digest is still compared against every row's declared digest.
    calls.clear();p=td/'bad_second.csv';rows_csv(p,ledger,good,'0'*64);s=fixture(ledger)
    with patch.object(live,'sha',side_effect=counted):
      try:s.reject_point_uses(p)
      except ValueError as e:assert str(e)=='Rejected claim input hash differs'
      else:raise AssertionError('second row bad declared hash accepted')
    assert calls==[str(ledger)] and 'a' not in s.point_rows and 'b' in s.point_rows

    # No cross-invocation cache: changed bytes on same path fail on next call.
    ledger.write_bytes(b'ledger changed bytes');calls.clear();p=td/'old_expected.csv';rows_csv(p,ledger,good);s=fixture(ledger)
    with patch.object(live,'sha',side_effect=counted):
      try:s.reject_point_uses(p)
      except ValueError as e:assert str(e)=='Rejected claim input hash differs'
      else:raise AssertionError('stale digest survived into a new call')
    assert calls==[str(ledger)] and 'a' in s.point_rows

    # Original first-row status, coordinates, active-ledger and bad-hash guards remain intact.
    ledger.write_bytes(b'ledger first bytes');good=digest(ledger)
    badcases=[
      ({'rejection_status':'candidate'},'Unsupported point rejection status'),
      ({'old_latitude':1.25},'Rejected claim does not match the active point'),
      ({'origin_ledger':str(td/'other.parquet')},'Rejected claim ledger is not active'),
      ({'origin_ledger_sha256':'f'*64},'Rejected claim input hash differs'),
    ]
    for changed,msg in badcases:
      rec={"target_source_record_id":"a","rejection_status":"reviewed_superseded_representative_point_only","old_latitude":1.0,"old_longitude":2.0,"origin_ledger":str(ledger),"origin_ledger_sha256":good};rec.update(changed)
      p=td/'bad_first.csv';pd.DataFrame([rec]).to_csv(p,index=False);s=fixture(ledger)
      with patch.object(live,'sha',side_effect=counted):
        try:s.reject_point_uses(p)
        except ValueError as e:assert str(e)==msg,(str(e),msg)
        else:raise AssertionError(f'guard bypassed: {msg}')
      assert 'a' in s.point_rows
    print({'actual_method':'current_chain_state_20261007.State.reject_point_uses','regressions':'PASS','valid_repeated_path_hash_calls':1,'bad_second_row_rejected':True,'changed_between_invocations_detected':True,'first_row_status_coordinate_active_ledger_digest_guards':'PASS'})

if __name__=='__main__':main()
