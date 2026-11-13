"""
Verify exactly how Git calls GIT_ASKPASS.
Git passes the prompt as a SINGLE argv[1], not as multiple space-separated tokens.
Our earlier test with '"username" "& dir"' was adversarial input that simulates
what happens when TWO args are separately passed.

Real Git invocations use ONE argument per call:
   git: execv(askpass_path, {askpass_path, prompt, NULL})
Corresponding Python subprocess: run([bat_path, prompt_string])

This test verifies:
1. With single-argument prompts (how Git actually calls the helper), does the bat stay safe?
2. With pathological single-argument prompts containing metacharacters within a single string?

Run: .venv\Scripts\python.exe tests/scratch_git_invocation_test.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path
import shutil

d = Path(tempfile.mkdtemp(prefix="autogit_git_invoke_"))
bat = d / "askpass.bat"

bat.write_text(
    "@echo off\r\n"
    "setlocal\r\n"
    "set PROMPT_TEXT=%*\r\n"
    'echo %PROMPT_TEXT% | findstr /i "username" >nul\r\n'
    "if %errorlevel% equ 0 (\r\n"
    "  echo x-access-token\r\n"
    "  exit /b 0\r\n"
    ")\r\n"
    'echo %PROMPT_TEXT% | findstr /i "password" >nul\r\n'
    "if %errorlevel% equ 0 (\r\n"
    "  echo TEST_SECRET_TOKEN\r\n"
    "  exit /b 0\r\n"
    ")\r\n"
    "echo.\r\n"
    "exit /b 0\r\n",
    encoding="ascii",
)

# These are SINGLE-ARGUMENT prompts exactly as Git would pass them
single_arg_prompts = [
    "Username for 'https://github.com': ",
    "Password for 'https://x-access-token@github.com': ",
    # Metacharacters WITHIN a single argument string (how they appear in real prompts)
    "Username for 'https://evil.com & stuff': ",
    "Password for 'https://evil|pipe.com': ",
    "Username for 'https://host%20space.com': ",
    "Username for 'https://host(paren).com': ",
    "Password for 'https://host>redirect.com': ",
    "Username for 'https://host<input.com': ",
    # Completely unexpected prompts
    "Enter passphrase for key '/home/user/.ssh/id_rsa': ",
    "Passphrase: ",
]

# These two-token cases would only arise if cmd.exe mis-parses the argument
# THEY ARE NOT REAL GIT PROMPTS but adversarial test vectors
multi_token_adversarial = [
    # Only possible if Git passes UNQUOTED args - Git DOES quote them
    '"username" "& dir"',  # This requires TWO subprocess args
    ">>username<<",        # Only dangerous if passed unquoted at shell level
    "||username||",        # Same
]

print("Single-argument prompts (actual Git invocation pattern):")
print("=" * 70)
all_safe = True
for prompt in single_arg_prompts:
    r = subprocess.run([str(bat), prompt], capture_output=True, text=True, timeout=5, shell=False)
    injection_found = any(x in r.stdout for x in ["INJECTED", "Volume in drive", "Directory of"])
    safe = not injection_found
    if not safe:
        all_safe = False
    print(f"  prompt  = {repr(prompt[:55])}")
    print(f"  stdout  = {repr(r.stdout.strip())}")
    print(f"  rc      = {r.returncode}, SAFE = {safe}")
    print()

print()
print("Multi-token adversarial cases (NOT real Git invocations):")
print("=" * 70)
for prompt in multi_token_adversarial:
    try:
        # Pass as list[bat, prompt] - this is a single string but cmd.exe may split it
        r = subprocess.run([str(bat), prompt], capture_output=True, text=True, timeout=5, shell=False)
        injection_found = any(x in r.stdout for x in ["INJECTED", "Volume in drive", "Directory of"])
        safe = not injection_found
        print(f"  prompt  = {repr(prompt[:55])}")
        print(f"  stdout  = {repr(r.stdout.strip()[:100])}")
        print(f"  rc      = {r.returncode}, SAFE = {safe}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
    print()

print(f"Real Git invocation pattern: {'ALL SAFE' if all_safe else 'VULNERABILITIES FOUND'}")
shutil.rmtree(str(d), ignore_errors=True)

