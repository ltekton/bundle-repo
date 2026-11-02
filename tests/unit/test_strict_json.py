import pytest

import bundle_repo as br

pytestmark = pytest.mark.unit


@pytest.mark.req("BR-SI-006")
def test_duplicate_json_keys_are_rejected():
    with pytest.raises(br.FormatError, match="duplicate JSON key"):
        br.strict_json_loads('{"a":1,"a":2}')


@pytest.mark.req("BR-SI-007", "BR-REQ-VERIFY-004")
def test_resource_limits_require_positive_values():
    with pytest.raises(br.FormatError, match="positive integer"):
        br.ResourceLimits(max_entries=0)


@pytest.mark.parametrize("value", ["CON", "a<bad", "trailing.", "e\u0301"])
def test_nonportable_paths_are_rejected(value):
    with pytest.raises(br.FormatError):
        br.RepositoryPath.parse(value)
