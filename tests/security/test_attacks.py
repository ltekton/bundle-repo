import json
import os
from pathlib import Path

import pytest

import bundle_repo as br
from tests.helpers import git

pytestmark = pytest.mark.security


def make_bundle(repo, tmp_path):
    (repo / "dir").mkdir()
    (repo / "dir" / "x").write_text("x")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "c")
    return br.BundleBuilder(
        br.GitRepository(repo), br.CreateOptions(repo, tmp_path / "out")
    ).build()


@pytest.mark.req(
    "BR-SI-001", "BR-SI-002", "BR-SI-005", "BR-SI-008", "BR-SI-012", "BR-REQ-RECON-004"
)
def test_tampered_part_rejected(repo: Path, tmp_path: Path):
    result = make_bundle(repo, tmp_path)
    doc = json.loads(result.manifest.read_text())
    part = result.manifest.parent / doc["parts"][0]["name"]
    blob = bytearray(part.read_bytes())
    blob[-2] ^= 1
    part.write_bytes(blob)
    with pytest.raises(br.IntegrityError, match="part SHA-256"):
        br.BundleVerifier().verify(result.manifest)


def test_symlink_ancestor_destination_rejected(repo: Path, tmp_path: Path):
    result = make_bundle(repo, tmp_path)
    verified = br.BundleVerifier().verify(result.manifest)
    dest = tmp_path / "dest"
    outside = tmp_path / "outside"
    dest.mkdir()
    outside.mkdir()
    try:
        os.symlink(outside, dest / "dir")
    except OSError as exc:
        pytest.skip(str(exc))
    br.BundleReconstructor().reconstruct(verified, dest, force=True)
    assert not (outside / "x").exists()
    assert not (dest / "dir").is_symlink()
    assert (dest / "dir" / "x").read_text() == "x"
