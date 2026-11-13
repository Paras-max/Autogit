"""
Final definitive test: Use python.exe directly as GIT_ASKPASS.
The .bat shim's ONLY job is to call python.exe with a FIXED script path.
Git's prompt arrives as sys.argv[1] in PYTHON - which handles it safely (no shell parsing).
The .bat receives %1 but only uses it to set an env var - which IS safe when %~1 is used
with a simple string not containing cmd metacharacters at the shell level.

Actually, the issue is that %~1 itself is processed by cmd.exe BEFORE the set command.
The only safe approach: Don't use the prompt via %~1 at all in the bat.

DEFINITIVE APPROACH:
- .bat calls python.exe passing %* as a QUOTED argument via \"\"
- Actually: python.exe receives argv from the CreateProcess call, NOT from cmd.exe shell parsing
- When .bat does: python.exe script.py %1   <- %1 is passed to python via CreateProcess, safe
- When .bat does: python.exe script.py %*   <- all args passed to python, safe from shell injection
  because CreateProcess doesn't interpret metacharacters in args to child processes

WAIT - this is the key insight I missed:
When cmd.exe runs: python.exe script.py %*
- cmd.exe expands %* to the VALUE of the args (but metacharacters in that value ARE interpreted
  for pipes and redirects BEFORE the expansion happens at PARSE TIME)
  
So: bat receives arg '" | dir"' -> %* becomes ' | dir"' -> 'python.exe script.py | dir"'
                                                                                   ^^^^ executed!

THE ONLY SAFE SOLUTION:
Write the .bat so it NEVER passes user-controlled data as a command argument.
Instead, write the prompt to a TEMP FILE that only the owner can read, then have Python read it.

OR: Use pythonw.exe -c "..." as GIT_ASKPASS directly (no .bat), passing the
prompt env var via an already-established environment variable key that Git will pass through.

ACTUALLY THE SIMPLEST: Git on Windows supports GIT_ASKPASS pointing to a .py file
IF Python is configured as the handler for .py files. But this is unreliable.

TRUE SOLUTION: Create a minimal self-contained .exe wrapper using Python's zipapp module,
or use the Python embed distribution to create a true executable. 

FOR AUTOGIT AI: Use a secure two-file approach:
1. A Python helper script (helper.py) that reads sys.argv[1] safely
2. A .bat wrapper that uses: set AUTOGIT_PROMPT_VAR=%* (setlocal, no delayed expansion)
   This sets the env var from %* - which IS UNSAFE for the reasons we tested.

FINAL REAL SOLUTION: Use a .bat that writes %* to a named pipe or file first.

RUN: .venv\Scripts\python.exe tests/scratch_tmpfile_approach.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path
import shutil
import uuid

d = Path(tempfile.mkdtemp(prefix="autogit_tmpfile_"))
py_helper = d / "helper.py"
bat = d / "askpass.bat"

token_var = "AUTOGIT_T_X"
user_var = "AUTOGIT_U_X"
# Use a fixed temp file path to pass the prompt text
prompt_file = d / "prompt.txt"

# Python helper reads prompt from temp file (written by bat)
py_helper.write_text(
    f"""import os
from pathlib import Path
prompt_file = Path(r"{str(prompt_file)}")
try:
    prompt = prompt_file.read_text(encoding="utf-8", errors="replace")
except Exception:
    prompt = ""
pl = prompt.lower()
if "username" in pl:
    print(os.environ.get("{user_var}", ""), end="")
elif "password" in pl:
    print(os.environ.get("{token_var}", ""), end="")
# else: empty string
""",
    encoding="utf-8",
)

# Bat: redirect %* (echo) to a temp file - metacharacters in %* still problematic for echo.
# BUT: use 'echo.%*' > file which is safer because:
# - The > redirect in the bat is PARSE-TIME (safe, intended)
# - The %* VALUE is echoed (not executed) because echo is a command, not shell evaluation
# Wait: 'echo %* > file' - the > redirect IS parse-time, so it redirects echo output to file.
# The %* value inside echo IS NOT executed (echo treats everything after as text to print).
# EXCEPT: 'echo hello | dir' - the | IS parse time and DOES pipe to dir!
# 
# Solution: Use 'echo.%*' (echo dot trick) and redirect BEFORE the |:
# 'echo.%* 1>prompt.txt 2>nul' - but the | in %* still gets parsed!
#
# REAL FIX: Use cmd /Q /D /C echo %* as a child process? Same problem.
# 
# DEFINITIVE SAFE FIX: Set the prompt from env, not from cmd argument:
# Have GIT_ASKPASS_INPUT env var (we set it ourselves!) contain the prompt BEFORE calling git.
# But we don't know the prompt text before git calls our helper - git generates it!
#
# CONCLUSION: There is NO safe way to handle arbitrary prompt text via a .bat file on Windows.
# The only safe solutions are:
# 1. A compiled .exe wrapper
# 2. Direct python.exe invocation as GIT_ASKPASS (requires .py extension association)
# 3. Use git credential helper protocol instead of GIT_ASKPASS
# 4. Use a python-based .exe created via pyinstaller/zipapp
# 5. Use WSL git
# 
# PRACTICAL SAFE SOLUTION for AutoGit AI:
# Create a minimal .exe launcher that wraps the python helper.
# In practice: use pyinstaller one-liner to create a 1-file exe at startup,
# OR: use the Python py launcher 'py.exe' which IS an exe!
# py.exe helper.py "prompt text" - py.exe handles the args safely from CreateProcess,
# and the .bat calls py.exe with quoted %1.

# TEST: py.exe approach
py_path = "py.exe"  # Windows Python Launcher
bat2 = d / "askpass_py.bat"
bat2_content = (
    "@echo off\r\n"
    "setlocal\r\n"
    f'py -3 "{str(py_helper)}" %1 2>nul\r\n'  # %1 passed to py.exe -> python -> sys.argv[1] SAFE
    "exit /b %errorlevel%\r\n"
)
bat2.write_text(bat2_content, encoding="ascii")

# Fix helper to read sys.argv[1] directly (py.exe passes it safely)
py_helper.write_text(
    f"""import sys, os
prompt = sys.argv[1] if len(sys.argv) > 1 else ""
pl = prompt.lower()
if "username" in pl:
    print(os.environ.get("{user_var}", ""), end="")
elif "password" in pl:
    print(os.environ.get("{token_var}", ""), end="")
""",
    encoding="utf-8",
)

env = {
    "PATH": r"C:\Windows\System32;C:\Python314",
    token_var: "SAFE_TOKEN_VALUE",
    user_var: "x-access-token",
}

adversarial_prompts = [
    "Username for 'https://github.com': ",
    "Password for 'https://x-access-token@github.com': ",
    "Password for 'https://evil.com' | dir: ",
    "Username > nul & echo INJECTED",
    '"username" "& dir"',
    ">>username<<",
    "||username||",
    "PASSWORD | dir C:\\",
]

print("py.exe launcher approach - adversarial test:")
print("=" * 70)
for prompt in adversarial_prompts:
    try:
        r = subprocess.run(
            [str(bat2), prompt],
            capture_output=True, text=True, timeout=5,
            env=env, shell=False
        )
        injection = any(x in r.stdout for x in ["INJECTED", "Volume in drive", "Directory of"])
        syntax_err = any(x in r.stderr.lower() for x in ["syntax", "unexpected"])
        safe = not injection
        print(f"  prompt  = {repr(prompt[:55])}")
        print(f"  stdout  = {repr(r.stdout.strip()[:80])}")
        print(f"  stderr  = {repr(r.stderr.strip()[:80])}")
        print(f"  rc      = {r.returncode}, SAFE = {safe}, SYNTAX_ERR = {syntax_err}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
    print()

shutil.rmtree(str(d), ignore_errors=True)

