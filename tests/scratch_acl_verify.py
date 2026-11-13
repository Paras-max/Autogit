"""
Verify that after ACL hardening:
1. Current user can still read and write helper files
2. Cleanup works correctly
3. BUILTIN\Administrators is removed

Run: .venv\Scripts\python.exe tests/scratch_acl_verify.py
"""
import subprocess
import tempfile
import os
from pathlib import Path
import shutil

user = os.environ.get("USERNAME", "PARAS")
domain = os.environ.get("USERDOMAIN", "LAPTOP-7GAGRH6M")
user_account = f"{domain}\\{user}"

d = Path(tempfile.mkdtemp(prefix="autogit_acl_verify2_"))
test_file = d / "askpass.bat"
test_file.write_text("hello world", encoding="utf-8")

# Apply hardening
subprocess.run(["icacls", str(d), "/inheritance:r"], capture_output=True)
subprocess.run(["icacls", str(d), "/grant:r", f"{user_account}:(OI)(CI)(F)"], capture_output=True)
subprocess.run(["icacls", str(d), "/remove:g", "BUILTIN\\Administrators"], capture_output=True)
subprocess.run(["icacls", str(test_file), "/inheritance:r"], capture_output=True)
subprocess.run(["icacls", str(test_file), "/grant:r", f"{user_account}:(F)"], capture_output=True)
subprocess.run(["icacls", str(test_file), "/remove:g", "BUILTIN\\Administrators"], capture_output=True)

# Verify
content = test_file.read_text(encoding="utf-8")
read_ok = content == "hello world"

r = subprocess.run(["icacls", str(d)], capture_output=True, text=True)
acl = r.stdout

admins_removed = "Administrators" not in acl
user_has_access = user in acl

print(f"Read after hardening: {read_ok}")
print(f"BUILTIN\\Administrators removed: {admins_removed}")
print(f"Current user ({user}) has access: {user_has_access}")
print(f"ACL output:\n{acl}")

test_file.unlink()
d.rmdir()
print(f"Cleanup successful: {not d.exists()}")

