import pytest

import bundle_repo as br
from tests.factories import content, manifest


def test_complete_content_passes():
    m = manifest()
    state = br.VerificationState(m)
    state.consume(content())
    state.finish()


def test_out_of_order_chunk_rejected():
    m = manifest()
    state = br.VerificationState(m)
    r = content(chunk=2)
    with pytest.raises(br.IntegrityError, match="out-of-order"):
        state.consume(r)


def test_missing_chunk_rejected():
    state = br.VerificationState(manifest())
    with pytest.raises(br.IntegrityError, match="chunk-count"):
        state.finish()
