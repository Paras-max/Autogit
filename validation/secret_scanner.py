"""
Secret Scanner for AutoGit AI.
Detects sensitive tokens, private keys, and credentials before staging or committing.
Guarantees secret values are NEVER printed in logs or API outputs.
"""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from utils.logger import logger
from utils.validators import mask_secret


SECRET_RULES = [
    ("GitHub Personal Access Token", re.compile(r"(ghp_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("OpenAI API Key", re.compile(r"(sk-[A-Za-z0-9_-]{20,}|sk-proj-[A-Za-z0-9_-]{20,})")),
    ("Google API / Gemini Key", re.compile(r"(AIza[0-9A-Za-z-_]{35})")),
    ("AWS Access Key ID", re.compile(r"(AKIA[0-9A-Z]{16})")),
    ("Private Key Header", re.compile(r"(-----BEGIN\s+([A-Z0-9_\s]+)?PRIVATE\s+KEY-----)")),
    ("Slack Token", re.compile(r"(xox[baprs]-[A-Za-z0-9-]{10,})")),
    ("Database URL with credentials", re.compile(r"(postgres|mysql|mongodb)://[^:]+:[^@]+@[^/]+")),
    ("Hardcoded Password Assignment", re.compile(r"""(?i)(?:password|passwd|api_key|secret_key)\s*[:=]\s*["']([^"'\s]{8,})["']""")),
]


class SecretScanner:
    """Scans code changes and files for potential credentials and secrets."""

    def scan_text(self, text: str, file_path: str = "diff") -> List[Dict[str, Any]]:
        findings = []
        lines = text.splitlines()

        for line_num, line in enumerate(lines, start=1):
            for rule_name, pattern in SECRET_RULES:
                match = pattern.search(line)
                if match:
                    raw_val = match.group(0)
                    # Mask the secret completely
                    masked = mask_secret(raw_val)
                    findings.append({
                        "file_path": file_path,
                        "line_number": line_num,
                        "rule_name": rule_name,
                        "masked_match": masked,
                    })
                    logger.warning(
                        f"Secret detected in {file_path} (line {line_num}): {rule_name} [{masked}]"
                    )
        return findings

    def scan_files(self, repo_path: Path | str, file_paths: List[str]) -> Dict[str, Any]:
        """
        Scan a list of repository files before staging.
        """
        repo_root = Path(repo_path).resolve()
        all_findings = []

        for rel_path in file_paths:
            # Explicitly block committing environment files
            filename = Path(rel_path).name.lower()
            if filename in (".env", ".env.local", ".env.production", "credentials.json", "id_rsa"):
                all_findings.append({
                    "file_path": rel_path,
                    "line_number": 1,
                    "rule_name": "Forbidden Environment/Key File",
                    "masked_match": filename,
                })
                continue

            full_path = repo_root / rel_path
            if full_path.exists() and full_path.is_file():
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    file_findings = self.scan_text(content, file_path=rel_path)
                    all_findings.extend(file_findings)
                except Exception as e:
                    logger.debug(f"Could not read {rel_path} for secret scan: {e}")

        has_secrets = len(all_findings) > 0
        return {
            "has_secrets": has_secrets,
            "findings_count": len(all_findings),
            "findings": all_findings,
        }

