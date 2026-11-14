"""
Secure Git Credential Handler for AutoGit AI (Phase 4).

Provides platform-specific, ephemeral GIT_ASKPASS credential helpers:
- Windows (.bat) and POSIX (.sh).
- Discriminates between Username and Password prompts.
- Zero token embedded in the script itself (reads from process-scoped environment variables).
- Zero token in process command-line arguments, git config, remote URLs, logs, or API responses.
- Ephemeral process-scoped environment with GIT_TERMINAL_PROMPT=0.
- Automatic cleanup in try/finally blocks across success, error, timeout, and interruption.
- Concurrency-safe helper directory management with owner PID verification.
- Safe startup cleanup of abandoned helper files with restrictive pattern matching and PID checking.
- Restrictive file and directory permissions (Windows ACL inheritance restricted / POSIX 0700).
- Does not modify or overwrite persistent user Git credentials.
"""

from contextlib import contextmanager
import glob
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
from typing import Dict, Generator, Optional, Tuple

from utils.logger import logger


# Prefix used strictly for AutoGit AI credential helpers to avoid touching unrelated files
HELPER_PREFIX = "autogit_askpass_"


def _is_pid_alive(pid: int) -> bool:
    """Check whether a process with the given PID is currently active on the host OS."""
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            # On Windows, os.kill(pid, 0) can raise PermissionError if process exists,
            # or OSError/ProcessLookupError if process does not exist.
            # Using OpenProcess via ctypes or kernel check is safest:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid
            )
            if handle:
                # Check exit code
                exit_code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(handle)
                # STILL_ACTIVE = 259
                return exit_code.value == 259
            return False
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError, PermissionError):
        # On POSIX, PermissionError means the process exists but is owned by someone else
        return sys.platform != "win32" and isinstance(sys.exc_info()[1], PermissionError)
    except Exception:
        return False


def cleanup_abandoned_helpers(max_age_seconds: float = 300.0) -> int:
    """
    Safely scan the system temporary directory for abandoned AutoGit askpass helper files
    and directories. Considers both age AND creator process PID state.
    Never removes helpers belonging to an actively running process.
    Never removes unrelated temporary files.
    Returns the count of cleaned up files/dirs.
    """
    temp_dir = Path(tempfile.gettempdir())
    cleaned_count = 0
    now = time.time()

    pattern = str(temp_dir / f"{HELPER_PREFIX}*")
    for path_str in glob.glob(pattern):
        p = Path(path_str)
        try:
            mtime = p.stat().st_mtime
            # Try to read pid from pidfile inside directory if directory
            pid_alive = False
            if p.is_dir():
                pid_file = p / "owner.pid"
                if pid_file.is_file():
                    try:
                        pid_val = int(pid_file.read_text(encoding="utf-8").strip())
                        if _is_pid_alive(pid_val):
                            pid_alive = True
                    except Exception:
                        pass

            # If creator process is confirmed alive, DO NOT DELETE regardless of age
            if pid_alive:
                continue

            # Only remove if age exceeds max_age_seconds AND process is not active
            if now - mtime >= max_age_seconds:
                if p.is_file():
                    p.unlink(missing_ok=True)
                    cleaned_count += 1
                elif p.is_dir():
                    for child in p.iterdir():
                        child.unlink(missing_ok=True)
                    p.rmdir()
                    cleaned_count += 1
        except Exception as e:
            logger.debug(f"Could not clean abandoned helper {path_str}: {e}")

    if cleaned_count > 0:
        logger.info(f"Cleaned up {cleaned_count} abandoned credential helper artifact(s).")
    return cleaned_count


def _apply_restrictive_permissions(dir_path: Path, file_path: Path) -> None:
    """
    Apply restrictive permissions so only the current user/process can access
    the temporary helper directory and file.
    On POSIX: sets mode 0700.
    On Windows: uses icacls to disable inheritance, grant exclusive Full Control
    to the current user and NT AUTHORITY\\SYSTEM, and remove BUILTIN\\Administrators
    and all unrelated user access.
    """
    if sys.platform != "win32":
        try:
            dir_path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)  # 0700
            file_path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)  # 0700
        except Exception as e:
            logger.debug(f"Failed to set POSIX permissions: {e}")
    else:
        try:
            user = os.environ.get("USERNAME")
            domain = os.environ.get("USERDOMAIN")
            user_account = f"{domain}\\{user}" if domain and user else (user or "")

            if user_account:
                # 1. Directory ACL: disable inheritance, grant current user and SYSTEM Full Control
                subprocess.run(
                    ["icacls", str(dir_path), "/inheritance:r"],
                    capture_output=True, check=False
                )
                subprocess.run(
                    ["icacls", str(dir_path), "/grant:r", f"{user_account}:(OI)(CI)(F)"],
                    capture_output=True, check=False
                )
                subprocess.run(
                    ["icacls", str(dir_path), "/grant:r", "NT AUTHORITY\\SYSTEM:(OI)(CI)(F)"],
                    capture_output=True, check=False
                )
                subprocess.run(
                    ["icacls", str(dir_path), "/remove:g", "BUILTIN\\Administrators"],
                    capture_output=True, check=False
                )

                # 2. File ACL: disable inheritance, grant current user and SYSTEM Full Control
                subprocess.run(
                    ["icacls", str(file_path), "/inheritance:r"],
                    capture_output=True, check=False
                )
                subprocess.run(
                    ["icacls", str(file_path), "/grant:r", f"{user_account}:(F)"],
                    capture_output=True, check=False
                )
                subprocess.run(
                    ["icacls", str(file_path), "/grant:r", "NT AUTHORITY\\SYSTEM:(F)"],
                    capture_output=True, check=False
                )
                subprocess.run(
                    ["icacls", str(file_path), "/remove:g", "BUILTIN\\Administrators"],
                    capture_output=True, check=False
                )
        except Exception as e:
            logger.debug(f"Failed to set Windows ACL: {e}")


def _create_posix_helper(helper_path: Path, token_env_var: str, user_env_var: str) -> None:
    """
    Create a POSIX shell script helper that outputs username or password depending
    on the prompt received from Git in $1.
    Never contains raw credentials.
    """
    content = (
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  *[Uu]sername*)\n'
        '    exec printf "%s\\n" "${' + user_env_var + '}"\n'
        "    ;;\n"
        '  *[Pp]assword*)\n'
        '    exec printf "%s\\n" "${' + token_env_var + '}"\n'
        "    ;;\n"
        "  *)\n"
        '    exec printf "%s\\n" ""\n'
        "    ;;\n"
        "esac\n"
    )
    helper_path.write_text(content, encoding="utf-8")


def _get_or_compile_windows_helper(helper_path: Path) -> bool:
    """
    Provide a native Windows executable helper (.exe) that evaluates Git prompts
    directly inside the process without cmd.exe or shell metacharacter evaluation.
    Tries precompiled utils/askpass.exe first, then csc.exe compilation.
    Returns True if askpass.exe was created successfully.
    """
    import shutil
    built_in_exe = Path(__file__).parent / "askpass.exe"
    if built_in_exe.is_file():
        try:
            shutil.copyfile(built_in_exe, helper_path)
            return True
        except Exception as e:
            logger.debug(f"Could not copy precompiled askpass.exe: {e}")

    # Fallback to compiling askpass.cs with csc.exe if present
    cs_file = Path(__file__).parent / "askpass.cs"
    if cs_file.is_file():
        csc_candidates = [
            r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe",
            r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe",
            shutil.which("csc.exe"),
        ]
        for csc in csc_candidates:
            if csc and Path(csc).is_file():
                try:
                    res = subprocess.run(
                        [
                            csc,
                            "/nologo",
                            "/optimize",
                            "/target:exe",
                            f"/out:{str(helper_path)}",
                            str(cs_file),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if res.returncode == 0 and helper_path.is_file():
                        # Also cache at built_in_exe for subsequent calls
                        try:
                            shutil.copyfile(helper_path, built_in_exe)
                        except Exception:
                            pass
                        return True
                except Exception as e:
                    logger.debug(f"csc compilation failed: {e}")

    return False


def _create_windows_bat_fallback(helper_path: Path, token_env_var: str, user_env_var: str) -> None:
    """
    Fallback Windows batch helper when .exe is unavailable.
    """
    content = (
        "@echo off\r\n"
        "setlocal\r\n"
        "set PROMPT_TEXT=%*\r\n"
        "echo %PROMPT_TEXT% | findstr /i \"username\" >nul\r\n"
        "if %errorlevel% equ 0 (\r\n"
        f"  echo %{user_env_var}%\r\n"
        "  exit /b 0\r\n"
        ")\r\n"
        "echo %PROMPT_TEXT% | findstr /i \"password\" >nul\r\n"
        "if %errorlevel% equ 0 (\r\n"
        f"  echo %{token_env_var}%\r\n"
        "  exit /b 0\r\n"
        ")\r\n"
        "echo.\r\n"
        "exit /b 0\r\n"
    )
    helper_path.write_text(content, encoding="ascii")


@contextmanager
def git_credential_context(
    token: Optional[str],
    username: str = "x-access-token",
) -> Generator[Dict[str, str], None, None]:
    """
    Context manager that generates an ephemeral GIT_ASKPASS credential helper and yields
    an environment dictionary configured with GIT_ASKPASS, GIT_TERMINAL_PROMPT=0, and
    process-scoped secret environment variables.

    Guarantees:
    1. Returns username for Username prompts and token for Password prompts.
    2. Zero token in helper file or command-line arguments.
    3. Ephemeral process-scoped environment variables only.
    4. Concurrency safety: helper dir includes PID and timestamp.
    5. Automatic and guaranteed cleanup upon exit (success, error, timeout, interruption).
    6. If token is None or empty, yields empty dict without modifying credentials.
    """
    if not token or not token.strip():
        yield {}
        return

    stripped_token = token.strip()
    clean_username = username.strip() if username and username.strip() else "x-access-token"
    is_windows = sys.platform == "win32" or os.name == "nt"

    # Ephemeral random directory containing PID for owner verification
    my_pid = os.getpid()
    unique_suffix = f"{my_pid}_{int(time.time() * 1000)}"
    temp_dir = Path(tempfile.mkdtemp(prefix=f"{HELPER_PREFIX}{unique_suffix}_"))

    # Write owner PID file for concurrency-safe cleanup verification
    try:
        (temp_dir / "owner.pid").write_text(str(my_pid), encoding="utf-8")
    except Exception:
        pass

    # Process-scoped randomized variable names
    token_var_name = f"AUTOGIT_ASKPASS_TOKEN_{unique_suffix}"
    user_var_name = f"AUTOGIT_ASKPASS_USER_{unique_suffix}"
    helper_path: Optional[Path] = None

    try:
        if is_windows:
            exe_helper = temp_dir / "askpass.exe"
            if _get_or_compile_windows_helper(exe_helper):
                helper_path = exe_helper
            else:
                helper_path = temp_dir / "askpass.bat"
                _create_windows_bat_fallback(helper_path, token_var_name, user_var_name)
        else:
            helper_path = temp_dir / "askpass.sh"
            _create_posix_helper(helper_path, token_var_name, user_var_name)

        _apply_restrictive_permissions(temp_dir, helper_path)

        env_updates = {
            "GIT_ASKPASS": str(helper_path.resolve()),
            "GIT_TERMINAL_PROMPT": "0",
            token_var_name: stripped_token,
            user_var_name: clean_username,
        }

        yield env_updates

    finally:
        # Guaranteed cleanup: delete helper binary/script, pid file, and directory
        try:
            if helper_path and helper_path.exists():
                helper_path.unlink(missing_ok=True)
            pid_file = temp_dir / "owner.pid"
            if pid_file.exists():
                pid_file.unlink(missing_ok=True)
            if temp_dir.exists():
                temp_dir.rmdir()
        except Exception as e:
            logger.warning(f"Failed to clean up temporary credential helper at {temp_dir}: {e}")
