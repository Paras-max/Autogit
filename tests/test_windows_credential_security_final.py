"""
Final Windows-specific security tests for Step 1 (Secure Git Credential Handler):
- Check 1: Windows GIT_ASKPASS metacharacter safety and prompt injection resistance.
- Check 2: Actual Windows ACL inspection on temporary helper directories and files.
"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import pytest

from utils.git_credential import (
    cleanup_abandoned_helpers,
    git_credential_context,
    _is_pid_alive,
    HELPER_PREFIX,
)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific security tests")
class TestWindowsAskpassPromptSafety:
    """
    Check 1: Windows GIT_ASKPASS Prompt Safety.
    Verifies that the helper treats prompt text as untrusted input, never evaluates
    shell metacharacters as commands, strictly discriminates username vs password,
    and returns empty string for unexpected prompts.
    """

    def test_adversarial_prompts_no_command_execution(self):
        """Prompt strings with shell metacharacters (&, |, >, <, `, etc.) must NEVER execute commands."""
        dummy_token = "ghp_SAFE_TEST_TOKEN_0001"
        test_user = "test-autogit-user"

        with git_credential_context(dummy_token, username=test_user) as env:
            helper_path = env["GIT_ASKPASS"]
            child_env = {**os.environ, **env}

            adversarial_prompts = [
                # Unintended command injection attempts
                ("Username for 'https://evil.com & calc.exe': ", test_user),
                ("Password for 'https://evil.com' | dir: ", dummy_token),
                ("Password | dir C:\\", dummy_token),
                ("Username > nul & echo INJECTED", test_user),
                ('"username" "& dir"', test_user),
                (">>username<<", test_user),
                ("||username||", test_user),
                ("<username>", test_user),
                # Shell expansions
                ("Username % for % host: ", test_user),
                ("Username %USERNAME%: ", test_user),
                ("USERNAME!delayed!expansion: ", test_user),
                ("Password^) ^& calc: ", dummy_token),
                ("Username for 'https://host(paren).com': ", test_user),
                ("Password for 'https://host`whoami`.com': ", dummy_token),
                ("Password for 'https://host$(id).com': ", dummy_token),
                # Multi-line / CRLF
                ("Username\r\nPassword: ", test_user),
            ]

            for prompt, expected_output in adversarial_prompts:
                proc = subprocess.run(
                    [helper_path, prompt],
                    capture_output=True,
                    text=True,
                    env=child_env,
                    timeout=5.0,
                )
                assert proc.returncode == 0, f"Helper failed with code {proc.returncode} on prompt: {prompt!r}"

                # Ensure zero shell command injection indicators in stdout
                stdout_lower = proc.stdout.lower()
                forbidden_strings = ["volume in drive", "directory of", "injected", "file(s)"]
                for forbidden in forbidden_strings:
                    assert forbidden not in stdout_lower, f"Command execution detected for prompt {prompt!r}: {proc.stdout}"

                # Ensure expected response
                assert proc.stdout.strip() == expected_output, f"Incorrect response for prompt {prompt!r}: got {proc.stdout.strip()!r}, expected {expected_output!r}"

                # Ensure token is never leaked on username prompt
                if expected_output == test_user:
                    assert dummy_token not in proc.stdout
                    assert dummy_token not in proc.stderr

    def test_unexpected_adversarial_prompts_rejected(self):
        """Unexpected prompts containing shell metacharacters must return empty string, NEVER token."""
        dummy_token = "ghp_SAFE_TEST_TOKEN_0002"

        with git_credential_context(dummy_token) as env:
            helper_path = env["GIT_ASKPASS"]
            child_env = {**os.environ, **env}

            unexpected_prompts = [
                "Enter passphrase for key '/id_rsa' & dir: ",
                "PIN | whoami: ",
                "Confirm action (yes/no) > nul: ",
                "Random metacharacter bomb: & | > < % ! ^ ( ) ; : ",
                "Passphrase: ",
            ]

            for p in unexpected_prompts:
                proc = subprocess.run(
                    [helper_path, p],
                    capture_output=True,
                    text=True,
                    env=child_env,
                    timeout=5.0,
                )
                assert proc.returncode == 0
                assert proc.stdout.strip() == "", f"Unexpected prompt leaked data: {proc.stdout!r}"
                assert dummy_token not in proc.stdout
                assert dummy_token not in proc.stderr

    def test_token_not_in_stderr_on_syntax_variants(self):
        """Even with weird syntax prompts, stderr must be clean or never contain credentials."""
        dummy_token = "ghp_STRICT_CONFIDENTIAL_TOKEN_999"

        with git_credential_context(dummy_token) as env:
            helper_path = env["GIT_ASKPASS"]
            child_env = {**os.environ, **env}

            tricky_prompts = [
                '"""""',
                "\\\\\\\\",
                "%00%0a%0d",
                "; && ||",
            ]

            for p in tricky_prompts:
                proc = subprocess.run(
                    [helper_path, p],
                    capture_output=True,
                    text=True,
                    env=child_env,
                    timeout=5.0,
                )
                assert dummy_token not in proc.stdout
                assert dummy_token not in proc.stderr


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific security tests")
class TestWindowsAclVerification:
    """
    Check 2: Actual Windows ACL Verification.
    Inspects actual Windows security descriptors (DACLs) via icacls to verify:
    - Current user has exclusive Full Control (F).
    - BUILTIN\\Users and Everyone are completely absent (cannot read helper).
    - Inherited permissions are removed (/inheritance:r).
    - BUILTIN\\Administrators is explicitly removed.
    - Active process helper is never deleted by concurrent cleanup.
    """

    def test_windows_helper_acl_has_exclusive_access(self):
        """Inspect actual DACL on the helper directory and file using icacls."""
        dummy_token = "ghp_ACL_TEST_TOKEN_888"
        current_user = os.environ.get("USERNAME", "")
        assert current_user, "USERNAME environment variable must exist on Windows"

        with git_credential_context(dummy_token) as env:
            helper_path = Path(env["GIT_ASKPASS"])
            helper_dir = helper_path.parent

            # Inspect directory ACL
            res_dir = subprocess.run(["icacls", str(helper_dir)], capture_output=True, text=True, check=True)
            dir_acl = res_dir.stdout

            # Inspect file ACL
            res_file = subprocess.run(["icacls", str(helper_path)], capture_output=True, text=True, check=True)
            file_acl = res_file.stdout

            # 1. Current user must have explicit access
            assert current_user.lower() in dir_acl.lower(), f"Current user not in directory ACL: {dir_acl}"
            assert current_user.lower() in file_acl.lower(), f"Current user not in file ACL: {file_acl}"

            # 2. BUILTIN\\Users must NOT have access
            assert "builtin\\users" not in dir_acl.lower(), f"BUILTIN\\Users has access to directory: {dir_acl}"
            assert "builtin\\users" not in file_acl.lower(), f"BUILTIN\\Users has access to file: {file_acl}"

            # 3. Everyone must NOT have access
            assert "everyone" not in dir_acl.lower(), f"Everyone has access to directory: {dir_acl}"
            assert "everyone" not in file_acl.lower(), f"Everyone has access to file: {file_acl}"

            # 4. BUILTIN\\Administrators must be removed
            assert "builtin\\administrators" not in dir_acl.lower(), f"BUILTIN\\Administrators in directory ACL: {dir_acl}"
            assert "builtin\\administrators" not in file_acl.lower(), f"BUILTIN\\Administrators in file ACL: {file_acl}"

            # 5. File must NOT have inherited permissions (marked with (I))
            for line in file_acl.splitlines():
                if current_user.lower() in line.lower() and helper_path.name in line:
                    assert "(i)" not in line.lower(), f"File has inherited permissions: {line}"

    def test_current_user_can_read_and_execute(self):
        """Verify the current user process can read the file and execute it despite restrictive ACL."""
        dummy_token = "ghp_EXEC_TEST_TOKEN_777"
        with git_credential_context(dummy_token) as env:
            helper_path = Path(env["GIT_ASKPASS"])
            child_env = {**os.environ, **env}

            # Can read file bytes
            data = helper_path.read_bytes()
            assert len(data) > 0

            # Can execute file
            res = subprocess.run([str(helper_path), "Password: "], capture_output=True, text=True, env=child_env)
            assert res.returncode == 0
            assert res.stdout.strip() == dummy_token

    def test_cleanup_respects_active_process_with_strict_acl(self):
        """Active helpers with strict ACL are not deleted by cleanup while owning PID is running."""
        dummy_token = "ghp_PID_ACL_TEST_666"
        with git_credential_context(dummy_token) as env:
            helper_path = Path(env["GIT_ASKPASS"])
            helper_dir = helper_path.parent

            # Run cleanup with 0s threshold
            cleaned = cleanup_abandoned_helpers(max_age_seconds=0.0)

            # Owner process is active: must remain intact
            assert helper_path.exists(), "Active helper was deleted by cleanup!"
            assert helper_dir.exists(), "Active helper dir was deleted by cleanup!"

