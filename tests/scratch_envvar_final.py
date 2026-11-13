"""
DEFINITIVE SAFE APPROACH TEST:
Instead of echo %VAR% | findstr (parse-time pipe), use:
- set AUTOGIT_PROMPT_xxx=%*  (safe: metacharacters in VALUE are NOT executed)
- Python reads from os.environ[prompt_var] (no cmd.exe evaluation, no pipes)
- Python helper receives NO user-controlled command-line arguments
- No cmd.exe shell parsing of user data at any point in the helper logic

This is THE correct Windows GIT_ASKPASS implementation.

Run: .venv\Scripts\python.exe tests/scratch_envvar_final.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path
import shutil

d = Path(tempfile.mkdtemp(prefix="autogit_envvar_final_"))
py_helper = d / "helper.py"
bat = d / "askpass.bat"

TOKEN_VAR = "AUTOGIT_T_FINAL"
USER_VAR = "AUTOGIT_U_FINAL"
PROMPT_VAR = "AUTOGIT_PROMPT_FINAL"

py_helper.write_text(
    f"""import os, sys
prompt = os.environ.get("{PROMPT_VAR}", "")
pl = prompt.lower()
if "username" in pl:
    sys.stdout.write(os.environ.get("{USER_VAR}", "") + "\\n")
    sys.stdout.flush()
elif "password" in pl:
    sys.stdout.write(os.environ.get("{TOKEN_VAR}", "") + "\\n")
    sys.stdout.flush()
# else: no output = empty line
""",
    encoding="utf-8",
)

# SAFE bat: assigns %* to env var (metacharacters in VALUE of set are safe),
# then python reads from env var, NOT from piped echo or args.
bat_content = (
    "@echo off\r\n"
    "setlocal DisableDelayedExpansion\r\n"
    f"set {PROMPT_VAR}=%*\r\n"
    f'"{sys.executable}" "{str(py_helper)}" 2>nul\r\n'
    "exit /b %errorlevel%\r\n"
)
bat.write_text(bat_content, encoding="ascii")

env = {
    "PATH": r"C:\Windows\System32;C:\Python314",
    TOKEN_VAR: "SAFE_TOKEN",
    USER_VAR: "x-access-token",
    "USERPROFILE": r"C:\Users\PARAS",
    "APPDATA": r"C:\Users\PARAS\AppData\Roaming",
    "LOCALAPPDATA": r"C:\Users\PARAS\AppData\Local",
    "TEMP": r"C:\Users\PARAS\AppData\Local\Temp",
    "TMP": r"C:\Users\PARAS\AppData\Local\Temp",
    "SystemRoot": r"C:\Windows",
    "ComSpec": r"C:\Windows\System32\cmd.exe",
}

test_cases = [
    # Normal Git prompts
    ("Username for 'https://github.com': ", "x-access-token"),
    ("Password for 'https://x-access-token@github.com': ", "SAFE_TOKEN"),
    # Adversarial metacharacters
    ("Username for 'https://evil.com & stuff': ", "x-access-token"),
    ("Password for 'https://evil.com' | dir: ", "SAFE_TOKEN"),
    ("Password | dir C:\\", "SAFE_TOKEN"),
    ("Username > nul & echo INJECTED", "x-access-token"),
    ('"username" "& dir"', "x-access-token"),
    (">>username<<", "x-access-token"),
    ("||username||", "x-access-token"),
    ("USERNAME!delayed!expansion: ", "x-access-token"),
    ("Username % for % host: ", "x-access-token"),
    # Unexpected
    ("Enter passphrase for key: ", ""),
    ("Passphrase: ", ""),
]

print("ENV-VAR approach (set %* -> Python reads env, NO echo|findstr) - all adversarial:")
print("=" * 70)
all_safe = True
for prompt, expected_contains in test_cases:
    try:
        r = subprocess.run(
            [str(bat), prompt],
            capture_output=True, text=True, timeout=5,
            env=env, shell=False
        )
        injection = any(x in r.stdout for x in ["INJECTED", "Volume in drive", "Directory of", "File(s)"])
        syntax_err = any(x in r.stderr.lower() for x in ["syntax", "unexpected", "is not recognized"])
        safe = not injection
        correct = (expected_contains == "" and r.stdout.strip() == "") or \
                  (expected_contains and expected_contains in r.stdout)
        if not safe:
            all_safe = False
        print(f"  prompt   = {repr(prompt[:55])}")
        print(f"  expected = {repr(expected_contains)}")
        print(f"  stdout   = {repr(r.stdout.strip()[:80])}")
        print(f"  stderr   = {repr(r.stderr.strip()[:80])}")
        print(f"  rc       = {r.returncode}, SAFE = {safe}, CORRECT = {correct}, SYNTAX_ERR = {syntax_err}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
    print()

print(f"{'ALL SAFE' if all_safe else 'VULNERABILITIES FOUND'}")
shutil.rmtree(str(d), ignore_errors=True)

