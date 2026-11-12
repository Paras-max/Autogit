"""
Project Analyzer for AutoGit AI (Phase 3).
Performs read-only inspection of repository structure, dependencies, test frameworks,
and README context without loading the entire codebase into LLM context.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import ProjectContextModel
from utils.logger import logger


class ProjectAnalyzer:
    """
    Analyzes project layout, language, framework, tests, and documentation.
    Persists findings to the project_context table in SQLite.
    """

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    def analyze_repository(self, repo_id: int, repo_path: Path) -> ProjectContextModel:
        """
        Analyze repository structure and persist context.
        """
        repo_path = Path(repo_path).resolve()
        if not repo_path.exists():
            raise FileNotFoundError(f"Repository path does not exist: {repo_path}")

        primary_lang = self._detect_primary_language(repo_path)
        project_type, framework = self._detect_framework_and_type(repo_path, primary_lang)
        test_framework = self._detect_test_framework(repo_path, primary_lang)
        summary = self._extract_readme_summary(repo_path)

        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO project_context (
                    repository_id, project_type, primary_language, framework, test_framework, summary, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id) DO UPDATE SET
                    project_type=excluded.project_type,
                    primary_language=excluded.primary_language,
                    framework=excluded.framework,
                    test_framework=excluded.test_framework,
                    summary=excluded.summary,
                    analyzed_at=excluded.analyzed_at
                """,
                (
                    repo_id,
                    project_type,
                    primary_lang,
                    framework,
                    test_framework,
                    summary,
                    now,
                ),
            )
            context_id = cursor.lastrowid

        context = ProjectContextModel(
            id=context_id,
            repository_id=repo_id,
            project_type=project_type,
            primary_language=primary_lang,
            framework=framework,
            test_framework=test_framework,
            summary=summary,
            analyzed_at=now,
        )
        logger.info(
            f"Analyzed repo {repo_id}: lang={primary_lang}, framework={framework}, tests={test_framework}"
        )
        return context

    def get_context(self, repo_id: int) -> Optional[ProjectContextModel]:
        """Fetch cached project context from database."""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM project_context WHERE repository_id = ?", (repo_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                return ProjectContextModel(
                    id=d["id"],
                    repository_id=d["repository_id"],
                    project_type=d["project_type"],
                    primary_language=d["primary_language"],
                    framework=d.get("framework"),
                    test_framework=d.get("test_framework"),
                    summary=d.get("summary"),
                    analyzed_at=d.get("analyzed_at", ""),
                )
        return None

    def _detect_primary_language(self, repo_path: Path) -> str:
        """Detect the dominant programming language by marker files and extensions."""
        if (repo_path / "pyproject.toml").exists() or (repo_path / "requirements.txt").exists() or (repo_path / "setup.py").exists():
            return "python"
        if (repo_path / "package.json").exists():
            if (repo_path / "tsconfig.json").exists() or list(repo_path.glob("*.ts")) or list(repo_path.glob("src/**/*.ts")):
                return "typescript"
            return "javascript"
        if (repo_path / "Cargo.toml").exists():
            return "rust"
        if (repo_path / "go.mod").exists():
            return "go"
        if (repo_path / "pom.xml").exists() or (repo_path / "build.gradle").exists():
            return "java"

        # Count file extensions
        counts: Dict[str, int] = {}
        for f in repo_path.glob("*.*"):
            if not f.name.startswith("."):
                counts[f.suffix] = counts.get(f.suffix, 0) + 1

        ext_to_lang = {
            ".py": "python",
            ".ts": "typescript",
            ".js": "javascript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
        }
        for ext, _ in sorted(counts.items(), key=lambda item: item[1], reverse=True):
            if ext in ext_to_lang:
                return ext_to_lang[ext]

        return "python"  # Default fallback

    def _detect_framework_and_type(self, repo_path: Path, lang: str) -> Tuple[str, Optional[str]]:
        """Detect framework and project type."""
        if lang == "python":
            req_file = repo_path / "requirements.txt"
            pyproject = repo_path / "pyproject.toml"
            text = ""
            if req_file.exists():
                text += req_file.read_text(encoding="utf-8", errors="ignore").lower()
            if pyproject.exists():
                text += pyproject.read_text(encoding="utf-8", errors="ignore").lower()

            if "fastapi" in text:
                return "web-api", "FastAPI"
            if "flask" in text:
                return "web-app", "Flask"
            if "django" in text:
                return "web-app", "Django"
            if "click" in text or "argparse" in text or "typer" in text:
                return "cli-tool", "CLI"
            return "library", None

        if lang in ("javascript", "typescript"):
            pkg_file = repo_path / "package.json"
            if pkg_file.exists():
                try:
                    data = json.loads(pkg_file.read_text(encoding="utf-8", errors="ignore"))
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    if "next" in deps:
                        return "fullstack", "Next.js"
                    if "react" in deps:
                        return "frontend", "React"
                    if "vue" in deps:
                        return "frontend", "Vue"
                    if "express" in deps:
                        return "web-api", "Express"
                except Exception:
                    pass
            return "node-application", None

        return "application", None

    def _detect_test_framework(self, repo_path: Path, lang: str) -> Optional[str]:
        """Detect test framework configured in repository."""
        if (repo_path / "pytest.ini").exists() or (repo_path / "tests").exists():
            return "pytest"
        if (repo_path / "setup.cfg").exists() or (repo_path / "pyproject.toml").exists():
            return "pytest"
        if (repo_path / "jest.config.js").exists() or (repo_path / "jest.config.ts").exists():
            return "jest"
        return "pytest" if lang == "python" else None

    def _extract_readme_summary(self, repo_path: Path) -> Optional[str]:
        """Extract high-level description from README if present."""
        for name in ("README.md", "readme.md", "README.rst", "README.txt"):
            p = repo_path / name
            if p.exists():
                try:
                    lines = [line.strip() for line in p.read_text(encoding="utf-8", errors="ignore").splitlines()]
                    meaningful = [l for l in lines if l and not l.startswith("#") and not l.startswith("[!")]
                    if meaningful:
                        return " ".join(meaningful[:4])[:400]
                except Exception as e:
                    logger.debug(f"Could not read README: {e}")
        return None

