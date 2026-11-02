import pytest
import bundle_repo as br

pytestmark=pytest.mark.unit

@pytest.mark.parametrize("value",["","../x","/x","a\\b","a/../b","a\x00b"])
def test_repository_path_rejects_unsafe(value):
    with pytest.raises(br.FormatError,match="unsafe repository path"): br.RepositoryPath.parse(value)

@pytest.mark.parametrize("value",["README","src/a.py","unicodé/文件"])
def test_repository_path_accepts_safe(value): assert str(br.RepositoryPath.parse(value))==value

def test_repository_metadata_rejects_symbolic_head():
    with pytest.raises(br.FormatError,match="Git object ID"): br.RepositoryMetadata("main","HEAD",False)

@pytest.mark.parametrize(("mode","kind"),[("100644",br.EntryType.FILE),("100755",br.EntryType.FILE),("120000",br.EntryType.SYMLINK),("160000",br.EntryType.GITLINK)])
def test_git_entry_maps_modes(mode,kind): assert br.GitEntry(br.RepositoryPath.parse("x"),mode,"a"*40).kind is kind

@pytest.mark.parametrize(("path","pattern","result"),[("pkg/a.py","*.py",True),("docs/a","docs/",True),("mydocs/a","docs/",False),("src/a.py","src/*.py",True),("pkg/src/a.py","src/*.py",False)])
def test_pattern_semantics(path,pattern,result): assert br.pattern_matches(path,pattern) is result
