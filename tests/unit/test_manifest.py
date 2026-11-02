import pytest
import bundle_repo as br
from factories import manifest
pytestmark=pytest.mark.unit

@pytest.mark.req('BR-SI-011')
def test_manifest_roundtrip():
    original=manifest(); assert br.Manifest.from_dict(original.to_dict())==original

def test_manifest_self_hash_detects_change():
    raw=manifest().to_dict(); raw["summary"]["payload_bytes"]+=1
    with pytest.raises(br.IntegrityError,match="SHA-256"): br.Manifest.from_dict(raw)

def test_unknown_version_fails_closed():
    raw=manifest().to_dict(); raw["version"]=2; unsigned=dict(raw); unsigned.pop("manifest_sha256"); raw["manifest_sha256"]=br.sha256_bytes(br.canonical_json(unsigned))
    with pytest.raises(br.FormatError,match="unsupported"): br.Manifest.from_dict(raw)

@pytest.mark.req("BR-REQ-VERIFY-002")
def test_manifest_rejects_unknown_fields():
    raw = manifest().to_dict()
    raw["future"] = True
    unsigned = dict(raw)
    unsigned.pop("manifest_sha256")
    raw["manifest_sha256"] = br.sha256_bytes(br.canonical_json(unsigned))
    with pytest.raises(br.FormatError, match="unknown fields"):
        br.Manifest.from_dict(raw)
