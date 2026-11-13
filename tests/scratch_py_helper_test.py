"""
Test Python-delegating batch helper approach for Windows.
Verifies that the Python-based helper safely handles all adversarial prompt inputs.
Run: .venv\Scripts\python.exe tests/scratch_py_helper_test.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path
import shutil

d = Path(tempfile.mkdtemp(prefix="autogit_py_helper_test_"))
py_helper = d / "askpass_helper.py"
bat = d / "askpass.bat"

token_var = "AUTOGIT_TEST_TOKEN_VAR"
user_var = "AUTOGIT_TEST_USER_VAR"

# Python helper script: receives prompt via argv[1], checks for username/password
py_script = f"""import sys, os
prompt = sys.argv[1] if len(sys.argv) > 1 else ""
pl = prompt.lower()
if "username" in pl:
    print(os.environ.get("{user_var}", ""))
elif "password" in pl:
    print(os.environ.get("{token_var}", ""))
else:
    print("")
"""
py_helper.write_text(py_script, encoding="utf-8")

# Thin batch shim: delegates %1 (a single-quoted argument) to python
# Note: Git passes the prompt as the FIRST argument to GIT_ASKPASS - which arrives as %1 in the .bat
# Using %1 (not %*) avoids inadvertent second-argument side effects
bat_content = (
    "@echo off\r\n"
    f'"{sys.executable}" "{str(py_helper)}" %1 2>nul\r\n'
    "exit /b %errorlevel%\r\n"
)
bat.write_text(bat_content, encoding="ascii")

env = {
    "PATH": r"C:\Windows\System32",
    token_var: "TEST_SECRET_TOKEN",
    user_var: "x-access-token",
}

adversarial_prompts = [
    "Username for 'https://github.com': ",
    "Password for 'https://x-access-token@github.com': ",
    "Username for 'https://evil.com' & calc.exe: ",
    "Password for 'https://evil.com' | dir: ",
    "Username % for % https://github.com: ",
    "Password^) ^& calc: ",
    '"username" "& dir"',
    "Enter passphrase for key (unexpected): ",
    ">>username<<",
    "||username||",
    "PASSWORD | dir C:\\",
    "Username > nul & echo INJECTED",
    "USERNAME!delayed!expansion: ",
]

print("Python-delegating batch helper - adversarial test:")
print("=" * 70)
all_safe = True
for prompt in adversarial_prompts:
    try:
        r = subprocess.run(
            [str(bat), prompt],
            capture_output=True, text=True, timeout=5,
            env=env, shell=False
        )
        # Check for injection indicators
        injection_leaked = any(x in r.stdout for x in ["INJECTED", "dir", "Volume in drive"])
        token_in_stderr = "TEST_SECRET_TOKEN" in r.stderr
        safe = not injection_leaked and not token_in_stderr
        if not safe:
            all_safe = False
        print(f"prompt  = {repr(prompt[:55])}")
        print(f"  stdout  = {repr(r.stdout.strip())}")
        print(f"  stderr  = {repr(r.stderr.strip())}")
        print(f"  rc      = {r.returncode}")
        print(f"  SAFE    = {safe}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
    print()

print(f"{'ALL SAFE' if all_safe else 'VULNERABILITIES FOUND'}")
shutil.rmtree(str(d), ignore_errors=True)

