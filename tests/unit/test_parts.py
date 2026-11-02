from pathlib import Path

import pytest

import bundle_repo as br
from tests.factories import content

pytestmark = pytest.mark.unit


@pytest.mark.req("BR-REQ-CREATE-005")
def test_writer_reader_roundtrip(tmp_path: Path):
    writer = br.PartWriter(tmp_path, "x", 2048, "bundle")
    records = [content("a", b"a"), content("b", b"b")]
    for r in records:
        writer.write(r)
    parts = writer.close()
    read = list(br.PartReader([tmp_path / p.name for p in parts], "bundle").records())
    assert read == records


def test_oversized_record_does_not_create_file(tmp_path: Path):
    writer = br.PartWriter(tmp_path, "x", 2048, "bundle")
    with pytest.raises(br.FormatError, match="encoded record exceeds"):
        writer.write(content("/".join(["p" * 200] * 12), b"x"))
    assert list(tmp_path.iterdir()) == []
