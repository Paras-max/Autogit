"""
Test whether 'set VAR=%*' in batch is vulnerable to metacharacter injection
in the VALUE of %*. This tests if 'password | dir' causes dir to run.

Run: .venv\Scripts\python.exe tests/scratch_set_metachar.py
"""
import subprocess
import tempfile
from pathlib import Path
import shutil

d = Path(tempfile.mkdtemp(prefix="autogit_set_meta_"))
bat = d / "test.bat"
bat.write_text(
    "@echo off\r\n"
    "setlocal\r\n"
    "set FOO=%*\r\n"
    "echo FOO is [%FOO%]\r\n"
    "exit /b 0\r\n",
    encoding="ascii",
)

test_cases = [
    "username",
    "password | dir",           # Does this run dir?
    "username > nul",           # Does this suppress output?
    "password",
]

for prompt in test_cases:
    r = subprocess.run([str(bat), prompt], capture_output=True, text=True, timeout=5, shell=False)
    injection = any(x in r.stdout for x in ["Volume in drive", "Directory of", "File(s)"])
    print(f"prompt={repr(prompt)}")
    print(f"  stdout  = {repr(r.stdout.strip()[:80])}")
    print(f"  stderr  = {repr(r.stderr.strip()[:80])}")
    print(f"  rc      = {r.returncode}, INJECTION = {injection}")
    print()

shutil.rmtree(str(d), ignore_errors=True)

