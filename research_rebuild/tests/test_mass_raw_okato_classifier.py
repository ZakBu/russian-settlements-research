from pathlib import Path
import pytest
from research_rebuild.mass_linkage.raw_okato_classifier import copy_value,read_copy


def test_copy_null_and_literal_escapes():
    assert copy_value(r'\N') is None
    assert copy_value(r'\\N') == r'\N'
    assert copy_value(r'\t\141\x62') == '\tab'


def test_code_width_and_missing_terminator(tmp_path: Path):
    path=tmp_path/'source.sql'
    header='COPY okato (code, name_raw, name, status, name_full, is_settlement) FROM stdin;\n'
    row='01201802001\tп Алейский\tАлейский\tпоселок сельского типа\tпоселок сельского типа Алейский\tt\n'
    path.write_text(header+row+'\\.\n')
    frame=read_copy(path)
    assert frame.iloc[0].historical_okato=='01201802001'
    assert frame.iloc[0].source_line_1based==2
    path.write_text(header+row)
    with pytest.raises(ValueError,match='incomplete'):
        read_copy(path)
