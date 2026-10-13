"""Read the frozen qualified packet; never manufacture selected2002 IDs or graph edges."""
from pathlib import Path
import json,hashlib
import pandas as pd

def load_qualified():
    folder=Path(__file__).parent
    receipt=json.loads((folder/'qualified_application_receipt.json').read_text())
    for name,pin in receipt['output_hashes'].items():
        assert hashlib.sha256((folder/name).read_bytes()).hexdigest()==pin
    frame=pd.read_csv(folder/'accepted_qualified_physical_observations.csv',keep_default_na=False)
    assert len(frame)==receipt['qualified_observations']
    assert not frame[['scope','trajectory_id','year']].duplicated().any()
    for _,group in frame.groupby('trajectory_id'):
        assert set(group.year)=={2002,2010,2021}
    old=frame[frame.year.eq(2002)]
    assert old.source_record_id.eq('').all() and old.nonadditive_observation.all()
    assert frame[frame.year.ne(2002)].source_record_id.is_unique
    assert not frame.ordinary_NP3_asserted.any()
    assert not frame.population_primary_reference_verified.any()
    return frame

if __name__=='__main__':
    frame=load_qualified()
    print('PASS',frame.trajectory_id.nunique(),'series',len(frame),'observations')
