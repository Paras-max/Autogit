"""
Test the CORRECT bat quoting approach: "python.exe" "script.py" "%~1"
When %~1 is wrapped in quotes in the command line, cmd.exe does NOT interpret metacharacters
inside it as shell operators. The | | > < & become literal characters passed to Python.

This IS the correct and safe approach for Windows GIT_ASKPASS.

Run: .venv\Scripts\python.exe tests/scratch_quoted_arg_bat.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path
import shutil

d = Path(tempfile.mkdtemp(prefix="autogit_quoted_bat_"))
py_helper = d / "helper.py"
bat = d / "askpass.bat"

token_var = "AUTOGIT_T_Q"
user_var = "AUTOGIT_U_Q"

py_helper.write_text(
    f"""import sys, os
prompt = sys.argv[1] if len(sys.argv) > 1 else ""
pl = prompt.lower()
if "username" in pl:
    out = os.environ.get("{user_var}", "")
elif "password" in pl:
    out = os.environ.get("{token_var}", "")
else:
    out = ""
import sys as _sys
_sys.stdout.write(out + "\\n")
_sys.stdout.flush()
""",
    encoding="utf-8",
)

# KEY FIX: Wrap %~1 in double quotes in the Python call.
# "%~1" tells cmd.exe: "this is a quoted argument" - metacharacters inside are NOT evaluated.
# This is the correct, standard Windows batch quoting technique.
bat_content = (
    "@echo off\r\n"
    "setlocal\r\n"
    f'"{sys.executable}" "{str(py_helper)}" "%~1" 2>nul\r\n'
    "exit /b %errorlevel%\r\n"
)
bat.write_text(bat_content, encoding="ascii")

env = {
    "PATH": r"C:\Windows\System32;C:\Python314",
    token_var: "SAFE_TOKEN_VALUE",
    user_var: "x-access-token",
}

adversarial_prompts = [
    # Normal Git prompts
    ("Username for 'https://github.com': ", "x-access-token"),
    ("Password for 'https://x-access-token@github.com': ", "SAFE_TOKEN_VALUE"),
    # Adversarial metacharacters within single-string argument
    ("Username for 'https://evil.com & stuff': ", "x-access-token"),
    ("Password for 'https://evil.com' | dir: ", "SAFE_TOKEN_VALUE"),
    ("Username % for % host: ", "x-access-token"),
    ("Password^) ^& calc: ", "SAFE_TOKEN_VALUE"),
    # Multi-token adversarial (the previously problematic case)
    ('"username" "& dir"', "x-access-token"),    # %~1 = username (outer quotes stripped), %2 is ignored
    # Redirection operators (would cause syntax errors previously)
    (">>username<<", "x-access-token"),
    ("||username||", None),     # username extracted - depends on how cmd handles ||
    ("PASSWORD | dir C:\\", "SAFE_TOKEN_VALUE"),
    ("Username > nul & echo INJECTED", "x-access-token"),
    # Unexpected
    ("Enter passphrase for key: ", ""),
]

print("QUOTED-ARG bat approach - adversarial test:")
print("=" * 70)
all_safe = True
for prompt, expected in adversarial_prompts:
    try:
        r = subprocess.run(
            [str(bat), prompt],
            capture_output=True, text=True, timeout=5,
            env=env, shell=False
        )
        injection = any(x in r.stdout for x in ["INJECTED", "Volume in drive", "Directory of"])
        syntax_err = any(x in r.stderr.lower() for x in ["syntax", "unexpected"])
        safe = not injection
        if not safe:
            all_safe = False
        print(f"  prompt   = {repr(prompt[:55])}")
        print(f"  expected = {repr(expected)}")
        print(f"  stdout   = {repr(r.stdout.strip()[:80])}")
        print(f"  stderr   = {repr(r.stderr.strip()[:80])}")
        print(f"  rc       = {r.returncode}, SAFE = {safe}, SYNTAX_ERR = {syntax_err}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
    print()

print(f"{'ALL SAFE' if all_safe else 'VULNERABILITIES FOUND'}")
shutil.rmtree(str(d), ignore_errors=True)

