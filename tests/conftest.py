from __future__ import annotations
import subprocess
from pathlib import Path
import pytest

def git(repo:Path,*args:str)->str:
    return subprocess.run(["git","-C",str(repo),*args],check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout

@pytest.fixture
def repo(tmp_path:Path)->Path:
    p=tmp_path/"repo"; p.mkdir(); git(p,"init","-q"); git(p,"config","user.email","test@example.invalid"); git(p,"config","user.name","Test User"); return p

@pytest.fixture
def committed_repo(repo:Path)->Path:
    (repo/"hello.txt").write_text("hello\n"); git(repo,"add","-A"); git(repo,"commit","-qm","initial"); return repo
