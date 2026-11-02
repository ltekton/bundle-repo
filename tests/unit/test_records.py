import pytest

import bundle_repo as br
from tests.factories import content

pytestmark = pytest.mark.unit


def test_content_roundtrip():
    original = content(data=b"\x00hello\xff")
    assert br.ContentRecord.from_dict(original.to_dict()) == original


def test_invalid_base64():
    raw = content().to_dict()
    raw["data"] = "%%%"
    with pytest.raises(br.FormatError, match="base64"):
        br.ContentRecord.from_dict(raw)
