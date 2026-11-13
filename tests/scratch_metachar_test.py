"""
Scratch: test metacharacter safety of CURRENT batch helper implementation.
Run directly to see results on Windows.
"""
import subprocess
import sys
import tempfile
from pathlib import Path
import shutil

d = Path(tempfile.mkdtemp(prefix="autogit_metachar_test_"))
bat = d / "askpass.bat"

# Current implementation (verbatim from git_credential.py)
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

prompts = [
    "Username for 'https://github.com': ",
    "Password for 'https://x-access-token@github.com': ",
    "Username for 'https://evil.com' & calc.exe: ",
    "Password for 'https://evil.com' | dir: ",
    "Username % for % https://github.com: ",
    "Password^) ^& calc: ",
    'Username "quoted" arg: ',
    "Enter passphrase for key (unexpected): ",
    "Username for 'https://host (parenthesis) url': ",
    "Password for 'https://host!' exclam: ",
]

print("Metacharacter safety test with CURRENT batch implementation:")
print("=" * 70)
for prompt in prompts:
    try:
        r = subprocess.run(
            [str(bat), prompt],
            capture_output=True, text=True, timeout=5,
            shell=False
        )
        print(f"prompt  = {repr(prompt[:50])}")
        print(f"  stdout  = {repr(r.stdout.strip())}")
        print(f"  stderr  = {repr(r.stderr.strip())}")
        print(f"  rc      = {r.returncode}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
    print()

shutil.rmtree(str(d), ignore_errors=True)

