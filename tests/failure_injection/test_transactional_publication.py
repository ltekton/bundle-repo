from pathlib import Path
import os
import pytest
import bundle_repo as br
from conftest import git

pytestmark = pytest.mark.failure_injection

@pytest.mark.req("BR-REQ-CREATE-004", "BR-SI-003", "BR-SI-010")
def test_create_failure_leaves_no_published_bundle(repo: Path, tmp_path: Path, monkeypatch):
    (repo / "x").write_text("x")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "c")
    output = tmp_path / "bundle"
    original = br.BundleVerifier.verify
    def fail_verify(self, manifest_path):
        raise br.IntegrityError("injected verification failure")
    monkeypatch.setattr(br.BundleVerifier, "verify", fail_verify)
    with pytest.raises(br.IntegrityError):
        br.BundleBuilder(br.GitRepository(repo), br.CreateOptions(repo, output)).build()
    assert not output.exists()
    monkeypatch.setattr(br.BundleVerifier, "verify", original)

@pytest.mark.req("BR-REQ-RECON-003", "BR-SI-010")
def test_publish_failure_rolls_back_existing_destination(tmp_path: Path, monkeypatch):
    destination = tmp_path / "dest"
    destination.mkdir()
    (destination / "old.txt").write_text("old")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "new.txt").write_text("new")
    real_replace = os.replace
    calls = 0
    def flaky_replace(src, dst):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected publication failure")
        return real_replace(src, dst)
    monkeypatch.setattr(br.os, "replace", flaky_replace)
    with pytest.raises(br.ReconstructionError, match="transactional publication failed"):
        br._publish_tree(staging, destination, True)
    assert (destination / "old.txt").read_text() == "old"
    assert not (destination / "new.txt").exists()
