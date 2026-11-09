"""Fixed profile entrypoint; root-owned, mounted read-only, no repository config."""
import ast
from pathlib import Path
import sys
import subprocess
import unittest

for command in (['/opt/runtime/bin/ruff','check','--isolated','--ignore-noqa','--no-cache','--select','E9,F63,F7,F82','/work'], ['/usr/bin/python3','-I','-B','/opt/bandit_entry.py']):
    result=subprocess.run(command,check=False)
    if result.returncode:raise SystemExit(5)
sys.path.insert(0,'/opt/runtime/lib/python3.12/site-packages')
sys.path.insert(0,'/opt')
from ast_checks import scan
source=Path('/work')
files=sorted(source.rglob('*.py'))
if not files:raise SystemExit(3)
for file in files:
    content=file.read_text(encoding='utf-8')
    ast.parse(content,filename=str(file))
    if scan(content):raise SystemExit(6)
sys.path.insert(0,str(source))
# Discovery is intentionally inside the sandbox: importing tests executes code.
suite=unittest.defaultTestLoader.discover(str(source),pattern='test_*.py',top_level_dir=str(source))
if suite.countTestCases()==0:raise SystemExit(4)
result=unittest.TextTestRunner(verbosity=0).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
