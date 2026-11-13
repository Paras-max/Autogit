"""
Scratch: test metacharacter edge-cases that could bypass set PROMPT_TEXT=%*
when %* itself contains characters that break the subsequent echo line.
Tests:
  - '%*' containing percent expansions (double-percent edge case)
  - Prompt containing quote+paren that closes the if block prematurely
  - Prompt containing 'username' embedded inside a larger shell-injection string
  - Prompt that has only 'password' hidden inside extra text
Run directly: .venv\Scripts\python.exe tests/scratch_metachar_edge.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path
import shutil

d = Path(tempfile.mkdtemp(prefix="autogit_metachar_edge_"))
bat = d / "askpass.bat"

bat.write_text(
    "@echo off\r\n"
    "setlocal\r\n"
    "set PROMPT_TEXT=%*\r\n"
    'echo %PROMPT_TEXT% | findstr /i "username" >nul\r\n'
    "if %errorlevel% equ 0 (\r\n"
    "  echo test_username\r\n"
    "  exit /b 0\r\n"
    ")\r\n"
    'echo %PROMPT_TEXT% | findstr /i "password" >nul\r\n'
    "if %errorlevel% equ 0 (\r\n"
    "  echo test_token\r\n"
    "  exit /b 0\r\n"
    ")\r\n"
    "echo.\r\n"
    "exit /b 0\r\n",
    encoding="ascii",
)

edge_cases = [
    # Argument that starts with ) could break the if block if it got parsed
    ") & echo INJECTED",
    # Prompt containing ) which could close a parenthesized block
    "Password for 'https://github.com) & echo INJECTED': ",
    # Double percent - could expand PROMPT_TEXT in cmd
    "Username %USERNAME% test: ",
    # Redirect operators
    "Password >nul & echo INJECTED: ",
    # Poison null-redirect to close findstr without matching
    "Username >nul 2>&1: ",
    # Injection via !var! (delayed expansion)
    "Password !PROMPT_TEXT!: ",
    # Semicolons
    "Username;password;admin: ",
    # Carriage return via %0d
    "Username\r\nPassword: ",
]

print("EDGE CASE metacharacter safety tests with CURRENT batch implementation:")
print("=" * 70)
for prompt in edge_cases:
    try:
        r = subprocess.run(
            [str(bat), prompt],
            capture_output=True, text=True, timeout=5,
            shell=False
        )
        is_safe = "INJECTED" not in r.stdout and "INJECTED" not in r.stderr
        print(f"prompt  = {repr(prompt[:60])}")
        print(f"  stdout  = {repr(r.stdout.strip())}")
        print(f"  stderr  = {repr(r.stderr.strip())}")
        print(f"  rc      = {r.returncode}")
        print(f"  SAFE    = {is_safe}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
    print()

shutil.rmtree(str(d), ignore_errors=True)

