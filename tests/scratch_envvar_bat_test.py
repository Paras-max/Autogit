"""
Scratch: Final safe approach - use a .bat shim that sets an env var from %1
then delegates to a Python helper that reads the env var, NOT sys.argv.
This eliminates ALL cmd.exe argument parsing and metacharacter risks.

The .bat uses: set AUTOGIT_PROMPT_XXXXX=%~1
where %~1 strips surrounding double-quotes from the argument.
Then python reads os.environ['AUTOGIT_PROMPT_XXXXX'] - no arg parsing at all.

Crucially, python receives its OWN argv[] as hardcoded strings from the bat file.
No user-controlled data appears in python's argv[].

Run: .venv\Scripts\python.exe tests/scratch_envvar_bat_test.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path
import shutil

d = Path(tempfile.mkdtemp(prefix="autogit_envvar_bat_"))
py_helper = d / "helper.py"
bat = d / "askpass.bat"

token_var = "AUTOGIT_T_TEST"
user_var = "AUTOGIT_U_TEST"
prompt_var = "AUTOGIT_PROMPT_TEST"  # randomized per session in real code

py_helper.write_text(
    f"""import os
prompt = os.environ.get("{prompt_var}", "")
pl = prompt.lower()
if "username" in pl:
    print(os.environ.get("{user_var}", ""), end="")
elif "password" in pl:
    print(os.environ.get("{token_var}", ""), end="")
# else: empty string (no output = empty line)
""",
    encoding="utf-8",
)

# The batch shim:
# 1. %~1 strips surrounding quotes from the first argument
# 2. Sets it as an env var (setlocal scope, invisible outside this process)
# 3. Passes NO user data as python argument - just fixed script path
bat_content = (
    "@echo off\r\n"
    "setlocal\r\n"
    f"set {prompt_var}=%~1\r\n"
    f'"{sys.executable}" "{str(py_helper)}" 2>nul\r\n'
    "exit /b %errorlevel%\r\n"
)
bat.write_text(bat_content, encoding="ascii")

env = {
    "PATH": r"C:\Windows\System32",
    token_var: "TEST_SECRET_TOKEN",
    user_var: "x-access-token",
}

# All test prompts - both normal and adversarial single-argument cases
all_prompts = [
    # Normal Git prompts
    "Username for 'https://github.com': ",
    "Password for 'https://x-access-token@github.com': ",
    # Adversarial metacharacters within single-string argument
    "Username for 'https://evil.com & calc': ",
    "Password for 'https://evil.com' | dir: ",
    "Username % for % host: ",
    "Password^) ^& calc: ",
    '"username" "& dir"',          # Two-token adversarial
    ">>username<<",                # Redirect pair
    "||username||",                # Pipe pair
    "PASSWORD | dir C:\\",
    "Username > nul & echo INJECTED",
    "USERNAME!delayed!expansion: ",
    # Completely unexpected
    "Enter passphrase for key: ",
    "Passphrase: ",
]

print("Environment-variable-passing approach - all adversarial cases:")
print("=" * 70)
all_safe = True
for prompt in all_prompts:
    try:
        r = subprocess.run(
            [str(bat), prompt],
            capture_output=True, text=True, timeout=5,
            env=env, shell=False
        )
        injection = any(x in r.stdout for x in ["INJECTED", "Volume in drive", "Directory of"])
        token_leaked = "TEST_SECRET_TOKEN" in r.stderr
        safe = not injection and not token_leaked
        # Also: syntax errors should not occur
        syntax_err = "syntax" in r.stderr.lower() or "unexpected" in r.stderr.lower()
        if not safe or syntax_err:
            all_safe = False
        print(f"  prompt  = {repr(prompt[:55])}")
        print(f"  stdout  = {repr(r.stdout.strip()[:80])}")
        print(f"  stderr  = {repr(r.stderr.strip()[:80])}")
        print(f"  rc      = {r.returncode}, SAFE = {safe}, SYNTAX_ERR = {syntax_err}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
    print()

print(f"{'ALL SAFE (including adversarial multi-token)' if all_safe else 'VULNERABILITIES FOUND'}")
shutil.rmtree(str(d), ignore_errors=True)

