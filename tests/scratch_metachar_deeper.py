"""
Test specifically for the scenario where echo %PROMPT_TEXT% | findstr
could be manipulated.
Key concern: batch 'set PROMPT_TEXT=%*' and then 'echo %PROMPT_TEXT%'
where PROMPT_TEXT value contains '|', '&', '>' etc.

In batch, 'echo %VAR%' where VAR contains '|' DOES NOT execute the right side.
The variable contents are literal. This is because batch interprets variables
only at parse time (outside delayed expansion).

However, we want to verify this definitively.
Run directly: .venv\Scripts\python.exe tests/scratch_metachar_deeper.py
"""
import subprocess
import tempfile
from pathlib import Path
import shutil

d = Path(tempfile.mkdtemp(prefix="autogit_metachar_deep_"))
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

# The critical question: when %PROMPT_TEXT% contains shell metacharacters,
# does 'echo %PROMPT_TEXT% | findstr ...' evaluate them?
#
# In cmd.exe batch scripting:
# - `echo %PROMPT_TEXT% | findstr` is parsed at PARSE TIME.
#   The | is a parse-time pipe. The right side is 'findstr /i "username" >nul'.
# - %PROMPT_TEXT% is expanded AFTER parsing, so | inside the VALUE does NOT create a new pipe.
# - This is a fundamental property of cmd.exe: variable expansions do NOT re-parse shell metacharacters.
# - Delayed expansion (!VAR!) DOES re-parse when enabled, but we use setlocal without /enabledelayedexpansion.
#
# The dangerous pattern would be: set PROMPT_TEXT=| dir
# Then: echo %PROMPT_TEXT% would echo "| dir" literally (the echo receives it as-is)
# The | AFTER echo %PROMPT_TEXT% is the PARSE-TIME pipe to findstr, not a runtime pipe from the value.
#
# CONCLUSION: The existing batch implementation is safe against metacharacter injection via %*
# because variable expansion occurs after parse-time metacharacter interpretation.

tricky_cases = [
    # Exactly 'username' surrounded by injection attempts
    "||username||",
    ">>username<<",
    # Token appears after injection attempt
    "&& username",
    # Quoted injection
    '"username" "& dir"',
    # Only metacharacters, no keyword
    "| & > < ! % ^ ( )",
    # Null bytes (Windows cmd strips these)
    "user\x00name",
]

print("DEEPER metacharacter test - variable expansion does not re-parse:")
print("=" * 70)
for prompt in tricky_cases:
    try:
        r = subprocess.run(
            [str(bat), prompt],
            capture_output=True, text=True, timeout=5,
            shell=False
        )
        print(f"prompt  = {repr(prompt)}")
        print(f"  stdout  = {repr(r.stdout.strip())}")
        print(f"  stderr  = {repr(r.stderr.strip())}")
        print(f"  rc      = {r.returncode}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
    print()

shutil.rmtree(str(d), ignore_errors=True)

