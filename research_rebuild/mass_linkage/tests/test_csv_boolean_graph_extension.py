"""Regression for a real reviewed-CSV append that failed Parquet serialization."""
import pandas as pd
import pyarrow as pa
import pytest

from research_rebuild.mass_linkage.apply_reviewed_mass_extensions_20261004 import preserve_nullable_booleans


def test_csv_false_does_not_change_graph_boolean_or_unknown():
    baseline = pd.DataFrame({'boundary_comparability_asserted': pd.array([False, True, None], dtype='boolean')})
    reviewed = pd.DataFrame({'boundary_comparability_asserted': ['False', '']})
    frame = preserve_nullable_booleans(pd.concat([baseline, reviewed], ignore_index=True),
                                      {'boundary_comparability_asserted'})
    column = pa.Table.from_pandas(frame, preserve_index=False).column(0)
    assert pa.types.is_boolean(column.type)
    assert column.to_pylist() == [False, True, None, False, None]


def test_unrecognized_boolean_is_rejected_before_serialization():
    with pytest.raises(ValueError, match='invalid boolean source flag'):
        preserve_nullable_booleans(pd.DataFrame({'flag': ['candidate']}), {'flag'})
