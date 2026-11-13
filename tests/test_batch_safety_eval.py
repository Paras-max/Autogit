import subprocess
import tempfile
import sys
from pathlib import Path
import shutil

d = Path(tempfile.mkdtemp())
b = d / "test.bat"
b.write_text('@echo off\r\nsetlocal DisableDelayedExpansion\r\nset "PROMPT_TEXT=%*"\r\necho PROMPT=[%PROMPT_TEXT%]\r\n', encoding='ascii')
r = subprocess.run([str(b), '"username" "& dir"'], capture_output=True, text=True)
print('stdout:', r.stdout)
print('stderr:', r.stderr)
print('rc:', r.returncode)
shutil.rmtree(d)
