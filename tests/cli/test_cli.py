from pathlib import Path

import pytest

import bundle_repo as br

pytestmark = pytest.mark.cli


@pytest.mark.req("BR-REQ-CLI-001")
def test_help(capsys):
    with pytest.raises(SystemExit) as exc:
        br.main(["--help"])
    assert exc.value.code == 0 and "bundle-repo" in capsys.readouterr().out


@pytest.mark.req("BR-REQ-CLI-002")
def test_verify_missing_manifest_returns_domain_exit(tmp_path: Path, capsys):
    assert br.main(["verify", str(tmp_path / "missing.json")]) == 2
    assert "error:" in capsys.readouterr().err


@pytest.mark.req("BR-REQ-CLI-003")
def test_json_error_output(tmp_path: Path, capsys):
    assert br.main(["verify", str(tmp_path / "missing.json"), "--json"]) == 2
    import json

    payload = json.loads(capsys.readouterr().err)
    assert payload["status"] == "error"
    assert payload["error"] == "FormatError"
