from pathlib import Path

from conftest import git

import bundle_repo as br


def test_unborn_repo(repo: Path):
    (repo / "x").write_text("x")
    git(repo, "add", "x")
    m = br.GitRepository(repo).metadata()
    assert m.branch is not None and m.commit is None


def test_detached_head(committed_repo: Path):
    expected = git(committed_repo, "rev-parse", "HEAD").strip()
    git(committed_repo, "checkout", "--detach", "-q")
    m = br.GitRepository(committed_repo).metadata()
    assert m.branch is None and m.commit == expected
