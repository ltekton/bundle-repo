import pytest
from hypothesis import given
from hypothesis import strategies as st

import bundle_repo as br

pytestmark = pytest.mark.property


@given(st.binary(max_size=4096))
def test_content_record_json_roundtrip(data: bytes):
    record = br.ContentRecord(
        br.RepositoryPath.parse("x"), "100644", 1, 1, len(data), br.sha256_bytes(data), data
    )
    assert br.ContentRecord.from_dict(record.to_dict()) == record
