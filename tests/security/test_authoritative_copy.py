from pathlib import Path

import pytest
from conftest import git

import bundle_repo as br

pytestmark = pytest.mark.security


@pytest.mark.req("BR-REQ-RECON-001", "BR-SI-009")
def test_verified_bundle_uses_private_part_copies(repo: Path, tmp_path: Path):
    (repo / "x").write_text("original")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "c")
    result = br.BundleBuilder(
        br.GitRepository(repo), br.CreateOptions(repo, tmp_path / "bundle")
    ).build()
    verified = br.BundleVerifier().verify(result.manifest)
    source_part = result.parts[0]
    source_part.write_bytes(b"destroyed after verification")
    destination = tmp_path / "dest"
    br.BundleReconstructor().reconstruct(verified, destination)
    assert (destination / "x").read_text() == "original"
