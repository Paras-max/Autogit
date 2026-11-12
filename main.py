"""
AutoGit AI - Main Entrypoint
Provides both FastAPI REST backend and standalone CLI operations.
Phase 3: User-Controlled Repository Management, Random Scheduler & Autonomous Development Agent.
"""

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.execution_routes import execution_router
from api.phase3_routes import phase3_router
from api.phase4_routes import phase4_router
from api.routes import api_router
from background.application_service import application_service
from background.health_monitor import HealthMonitor
from background.service_manager import service_manager
from config.settings import settings
from core.authentication import AuthenticationService
from core.credential_manager import CredentialManager
from core.execution_controller import ExecutionController
from core.git_manager import GitManager
from core.permission_manager import PermissionManager
from core.repository_manager import RepositoryManager
from database.db import db
from database.execution_repository import ExecutionRepository
from database.models import RepositoryAutomationSettingsModel
from development.project_analyzer import ProjectAnalyzer
from development.task_manager import TaskManager
from integrations.github_client import GitHubClient
from integrations.github_sync import GitHubSyncEngine
from integrations.remote_status import RemoteStatusInspector
from monitoring.file_monitor import file_monitor
from notifications.notification_manager import notification_manager
from scheduler.weekly_scheduler import WeeklyScheduler
from utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("AutoGit AI application starting up...")
    logger.info(f"App Environment: {settings.APP_ENV}")
    logger.info(f"Database initialized at: {settings.DATABASE_PATH}")
    application_service.initialize_on_startup()
    application_service.start_scheduler_worker()
    yield
    # Shutdown
    logger.info("AutoGit AI shutting down...")
    application_service.shutdown()
    logger.info("AutoGit AI shutdown complete.")


app = FastAPI(
    title="AutoGit AI",
    description="IDE-independent autonomous Git automation platform (Phase 4: GitHub Sync, Dashboard & Deployment)",
    version="0.4.0",
    lifespan=lifespan,
)

# Cross-Origin Resource Sharing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes (Phase 1, 2, 3, 4)
app.include_router(api_router, prefix="/api/v1")
app.include_router(api_router)
app.include_router(execution_router, prefix="/api/v1")
app.include_router(execution_router)
app.include_router(phase3_router, prefix="/api/v1")
app.include_router(phase3_router)
app.include_router(phase4_router, prefix="/api/v1")
app.include_router(phase4_router)


@app.get("/api/health", summary="Application Health and Info")
def health():
    return {
        "name": "AutoGit AI",
        "phase": "Phase 4: GitHub Synchronization, Web Dashboard, Live Monitoring & Deployment",
        "status": "operational",
        "docs_url": "/docs",
    }


# Mount static frontend directory if built
frontend_dist = settings.BASE_DIR / "frontend" / "dist"
if frontend_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
else:
    @app.get("/", summary="Application Root")
    def root():
        return {
            "name": "AutoGit AI",
            "phase": "Phase 4: GitHub Synchronization, Web Dashboard, Live Monitoring & Deployment",
            "status": "operational",
            "docs_url": "/docs",
            "dashboard_note": "Frontend dashboard building in progress or accessible via Vite dev server",
        }



# ============================================================================
# CLI Interface
# ============================================================================

def run_cli():
    parser = argparse.ArgumentParser(
        description="AutoGit AI - Autonomous Git Automation CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # --- Phase 1 Commands ---
    run_parser = subparsers.add_parser("run", help="Start the FastAPI backend server")
    run_parser.add_argument("--host", default="127.0.0.1", help="Host address")
    run_parser.add_argument("--port", type=int, default=8000, help="Port number")
    run_parser.add_argument("--reload", action="store_true", help="Enable live reload")

    add_repo_p = subparsers.add_parser("add-repo", help="Register a local Git repository")
    add_repo_p.add_argument("path", help="Local directory path of Git repository")
    add_repo_p.add_argument("--name", help="Optional friendly name for repository")

    subparsers.add_parser("list-repos", help="List all registered repositories")

    del_repo_p = subparsers.add_parser("remove-repo", help="Unregister a repository")
    del_repo_p.add_argument("id", type=int, help="Repository ID to remove")

    status_p = subparsers.add_parser("status", help="Get Git status of a registered repository")
    status_p.add_argument("id", type=int, help="Repository ID")

    diff_p = subparsers.add_parser("diff", help="Get Git diff for a repository")
    diff_p.add_argument("id", type=int, help="Repository ID")

    subparsers.add_parser("auth-status", help="Show authentication and AI provider configuration")

    gh_p = subparsers.add_parser("validate-github", help="Validate GitHub Personal Access Token")
    gh_p.add_argument("--token", help="GitHub PAT (optional, uses GITHUB_TOKEN if omitted)")

    mon_p = subparsers.add_parser("monitor", help="Start foreground monitoring of a repository")
    mon_p.add_argument("id", type=int, help="Repository ID to monitor")

    # --- Phase 2 Commands ---
    analyze_p = subparsers.add_parser("analyze", help="Analyze repository changes and AI context")
    analyze_p.add_argument("--repo", type=int, required=True, help="Repository ID")
    analyze_p.add_argument("--hint", help="Optional user context or hint")

    validate_p = subparsers.add_parser("validate", help="Run pre-commit validation checks")
    validate_p.add_argument("--repo", type=int, required=True, help="Repository ID")

    propose_p = subparsers.add_parser("propose", help="Create Smart Commit proposal")
    propose_p.add_argument("--repo", type=int, required=True, help="Repository ID")
    propose_p.add_argument("--hint", help="Optional user context or hint")

    approve_p = subparsers.add_parser("approve", help="Approve an execution proposal")
    approve_p.add_argument("--execution", type=int, required=True, help="Execution ID")
    approve_p.add_argument("--notes", help="Optional approval notes")

    reject_p = subparsers.add_parser("reject", help="Reject an execution proposal")
    reject_p.add_argument("--execution", type=int, required=True, help="Execution ID")
    reject_p.add_argument("--reason", help="Optional rejection reason")

    execute_p = subparsers.add_parser("execute", help="Execute an approved proposal")
    execute_p.add_argument("--execution", type=int, required=True, help="Execution ID")

    history_p = subparsers.add_parser("history", help="Show execution history for repository")
    history_p.add_argument("--repo", type=int, required=True, help="Repository ID")

    mode_p = subparsers.add_parser("automation-mode", help="Check current automation mode")
    mode_p.add_argument("--repo", type=int, required=True, help="Repository ID")

    set_mode_p = subparsers.add_parser("set-mode", help="Set automation mode ('smart' or 'auto')")
    set_mode_p.add_argument("--repo", type=int, required=True, help="Repository ID")
    set_mode_p.add_argument("--mode", choices=["smart", "auto"], required=True, help="Automation mode")
    set_mode_p.add_argument("--confirm", action="store_true", help="Confirm switching to auto mode")

    # --- Phase 3 Commands ---
    perm_p = subparsers.add_parser("permissions", help="Show repository permission configuration")
    perm_p.add_argument("--repo", type=int, required=True, help="Repository ID")

    enable_dev_p = subparsers.add_parser("enable-development", help="Enable autonomous development for a repository")
    enable_dev_p.add_argument("--repo", type=int, required=True, help="Repository ID")

    disable_dev_p = subparsers.add_parser("disable-development", help="Disable autonomous development for a repository")
    disable_dev_p.add_argument("--repo", type=int, required=True, help="Repository ID")

    subparsers.add_parser("schedule", help="Show current 5-day random weekly schedule")

    gen_sched_p = subparsers.add_parser("generate-schedule", help="Generate or regenerate this week's schedule")
    gen_sched_p.add_argument("--force", action="store_true", help="Force regeneration even if schedule already exists")

    subparsers.add_parser("pause-scheduler", help="Pause the autonomous development scheduler")
    subparsers.add_parser("resume-scheduler", help="Resume the autonomous development scheduler")

    analyze_project_p = subparsers.add_parser("project-analyze", help="Analyze project structure and context")
    analyze_project_p.add_argument("--repo", type=int, required=True, help="Repository ID")

    add_task_p = subparsers.add_parser("add-task", help="Add a development task to repository backlog")
    add_task_p.add_argument("--repo", type=int, required=True, help="Repository ID")
    add_task_p.add_argument("--title", required=True, help="Task title")
    add_task_p.add_argument("--description", help="Task description")
    add_task_p.add_argument("--type", dest="task_type", default="feature",
                             choices=["feature", "test", "refactor", "documentation", "bugfix"],
                             help="Task type")
    add_task_p.add_argument("--priority", default="medium", choices=["low", "medium", "high"],
                             help="Task priority")

    list_tasks_p = subparsers.add_parser("list-tasks", help="List pending development tasks")
    list_tasks_p.add_argument("--repo", type=int, required=True, help="Repository ID")

    dev_run_p = subparsers.add_parser("development-run", help="Execute an autonomous development session")
    dev_run_p.add_argument("--repo", type=int, required=True, help="Repository ID")
    dev_run_p.add_argument("--no-worktree", action="store_true", help="Disable isolated worktree (use repo dir directly)")

    dev_hist_p = subparsers.add_parser("development-history", help="Show autonomous development session history")
    dev_hist_p.add_argument("--repo", type=int, required=True, help="Repository ID")

    # --- Phase 4 Commands ---
    subparsers.add_parser("github-account", help="Show authenticated GitHub user profile and rate limit")

    remote_p = subparsers.add_parser("remote-status", help="Inspect local vs remote synchronization status")
    remote_p.add_argument("--repo", type=int, required=True, help="Repository ID")

    fetch_p = subparsers.add_parser("fetch", help="Fetch remote updates safely without altering local files")
    fetch_p.add_argument("--repo", type=int, required=True, help="Repository ID")

    push_p = subparsers.add_parser("push", help="Push authorized commits to remote (requires remote_push permission)")
    push_p.add_argument("--repo", type=int, required=True, help="Repository ID")
    push_p.add_argument("--branch", help="Target branch (optional, defaults to current)")

    notif_p = subparsers.add_parser("notifications", help="List recent notifications")
    notif_p.add_argument("--unread", action="store_true", help="Filter unread notifications only")

    svc_p = subparsers.add_parser("service", help="Manage background application service")
    svc_p.add_argument("action", choices=["start", "stop", "restart", "status", "health"], help="Service action")

    args = parser.parse_args()

    repo_mgr = RepositoryManager()
    cred_mgr = CredentialManager()
    auth_service = AuthenticationService()
    exec_repo = ExecutionRepository()
    controller = ExecutionController()
    perm_mgr = PermissionManager()
    task_mgr = TaskManager()
    scheduler = WeeklyScheduler()
    project_analyzer = ProjectAnalyzer()

    if args.command == "run" or args.command is None:
        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8000)
        reload = getattr(args, "reload", False)
        print(f"Starting AutoGit AI server at http://{host}:{port}")
        uvicorn.run("main:app", host=host, port=port, reload=reload)

    elif args.command == "add-repo":
        try:
            repo = repo_mgr.add_repository(args.path, args.name)
            print(f"Registered repository '{repo.repository_name}' (ID: {repo.id}) at '{repo.repository_path}'")
        except Exception as e:
            print(f"Error registering repository: {e}")
            sys.exit(1)

    elif args.command == "list-repos":
        repos = repo_mgr.list_repositories()
        if not repos:
            print("No repositories registered.")
            return
        print("\nRegistered Repositories:")
        print("-" * 80)
        for r in repos:
            print(f"ID {r.id}: {r.repository_name} | Branch: {r.current_branch} | Path: {r.repository_path}")
        print("-" * 80)

    elif args.command == "remove-repo":
        success = repo_mgr.remove_repository(args.id)
        if success:
            print(f"Repository ID {args.id} removed from application (underlying files untouched).")
        else:
            print(f"Repository ID {args.id} not found.")

    elif args.command == "status":
        repo = db.get_repository(args.id)
        if not repo:
            print(f"Repository ID {args.id} not found.")
            return
        git_mgr = GitManager(repo.repository_path)
        status_info = git_mgr.get_git_status()
        print(f"\nGit Status for '{repo.repository_name}' [{status_info['current_branch']}]:")
        print(f"Working tree clean: {status_info['is_clean']}")
        print(f"Remote: {status_info['remote_url']}")
        if status_info['latest_commit']:
            print(f"Latest Commit: {status_info['latest_commit']['short_hash']} - {status_info['latest_commit']['message']}")
        print("\nStaged files:", status_info['staged_files'])
        print("Unstaged files:", status_info['unstaged_files'])
        print("Categorized changes:", status_info['changes'])

    elif args.command == "diff":
        repo = db.get_repository(args.id)
        if not repo:
            print(f"Repository ID {args.id} not found.")
            return
        git_mgr = GitManager(repo.repository_path)
        diffs = git_mgr.get_diff()
        print("\n=== Unstaged Diff ===")
        print(diffs['unstaged'] or "(No unstaged changes)")
        print("\n=== Staged Diff ===")
        print(diffs['staged'] or "(No staged changes)")

    elif args.command == "auth-status":
        status_data = auth_service.get_overall_auth_status()
        print("\n=== Authentication & Credentials Status ===")
        print(f"GitHub Status: {status_data['github']['status']} (User: {status_data['github']['username']})")
        print(f"Token Configured: {status_data['github']['token_configured']} ({status_data['github']['token_preview']})")
        print(f"Git Identity: Name='{status_data['git_identity']['name']}', Email='{status_data['git_identity']['email']}'")
        print(f"Active AI Provider: {status_data['ai_providers']['active_provider']}")
        for prov, info in status_data['ai_providers']['providers'].items():
            print(f"  - {info['name']}: configured={info['configured']} (Key: {info['masked_key']})")

    elif args.command == "validate-github":
        res = asyncio.run(auth_service.validate_github_token(args.token))
        print(f"\nGitHub Validation Result: success={res['success']}, status={res['status']}")
        if res.get("username"):
            print(f"Authenticated as: {res['username']}")
        if res.get("message"):
            print(f"Message: {res['message']}")

    elif args.command == "monitor":
        repo = db.get_repository(args.id)
        if not repo:
            print(f"Repository ID {args.id} not found.")
            return
        print(f"Starting live monitoring for repository '{repo.repository_name}' (ID: {args.id}). Press Ctrl+C to stop.")
        file_monitor.start_monitoring(args.id)
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            file_monitor.stop_monitoring(args.id)
            print("\nMonitoring stopped.")

    # --- Phase 2 CLI Handlers ---
    elif args.command == "analyze" or args.command == "propose":
        print(f"Running AI analysis pipeline for repository ID {args.repo}...")
        res = asyncio.run(controller.analyze_and_propose(repository_id=args.repo, user_hint=args.hint))
        if not res.get("success"):
            print(f"Analysis failed: {res.get('error')}")
            sys.exit(1)

        prop = res.get("proposal", {})
        print("\n" + "=" * 60)
        print(f"PROPOSAL CREATED (Execution ID: {res['execution_id']})")
        print(f"Mode: {res.get('mode')} | Status: {res.get('status')}")
        print("=" * 60)
        print(f"Summary: {prop.get('diff_summary')}")
        print(f"Task: {prop.get('logical_task')} (Risk: {prop.get('risk_level')})")
        print(f"\nProposed Files to Commit ({len(prop.get('proposed_files', []))}):")
        for f in prop.get("proposed_files", []):
            print(f"  - {f}")
        print("\nProposed Commit Message:")
        print("-" * 40)
        print(prop.get("proposed_message"))
        print("-" * 40)

        val = prop.get("validation", {})
        print(f"\nPre-commit Validation: {val.get('overall_status')}")
        sec = val.get("secret_scan", {})
        print(f"  - Secret Scanner: {'PASSED (0 secrets)' if not sec.get('has_secrets') else 'FAILED (Secrets detected!)'}")
        print(f"  - Automated Tests: {val.get('tests', {}).get('status')}")
        print(f"  - Policies: {val.get('policies', {}).get('status')}")
        if val.get("policies", {}).get("violations"):
            print("    Violations:", val["policies"]["violations"])

        if res.get("status") == "committed":
            print(f"\n[AUTO COMMIT SUCCESSFUL] Commit Hash: {res.get('commit_hash')}")
        elif res.get("status") == "awaiting_approval":
            print(f"\nAction Required: To commit these changes, run:")
            print(f"  python main.py approve --execution {res['execution_id']}")
            print(f"  python main.py execute --execution {res['execution_id']}")

    elif args.command == "validate":
        repo = db.get_repository(args.repo)
        if not repo:
            print(f"Repository ID {args.repo} not found.")
            sys.exit(1)
        git_mgr = GitManager(repo.repository_path)
        status_info = git_mgr.get_git_status()
        all_files = status_info["unstaged_files"] + status_info["staged_files"]
        settings_record = exec_repo.get_automation_settings(args.repo)

        print(f"\nRunning validations on {len(all_files)} changed file(s)...")
        report = controller.validation_agent.run_all_validations(
            repo_path=repo.repository_path,
            current_branch=status_info["current_branch"],
            target_files=all_files,
            total_diff_chars=len(git_mgr.get_unstaged_diff()) + len(git_mgr.get_staged_diff()),
            settings=settings_record,
        )
        print(f"Overall Status: {report['overall_status']}")
        print(f"Secret Scanner: {report['secret_scan']}")
        print(f"Tests: {report['tests']['status']} ({report['tests']['output']})")
        print(f"Policies: {report['policies']}")

    elif args.command == "approve":
        res = controller.approve_proposal(execution_id=args.execution, notes=args.notes)
        if res.get("success"):
            print(f"Execution ID {args.execution} APPROVED. To execute commit, run:")
            print(f"  python main.py execute --execution {args.execution}")
        else:
            print(f"Approval failed: {res.get('error')}")

    elif args.command == "reject":
        res = controller.reject_proposal(execution_id=args.execution, reason=args.reason)
        if res.get("success"):
            print(f"Execution ID {args.execution} REJECTED.")
        else:
            print(f"Rejection failed: {res.get('error')}")

    elif args.command == "execute":
        print(f"Executing approved commit for execution ID {args.execution}...")
        res = controller.execute_proposal(execution_id=args.execution)
        if res.get("success"):
            print("\n" + "=" * 60)
            print("COMMIT CREATED AND VERIFIED SUCCESSFULLY!")
            print(f"Commit Hash: {res.get('commit_hash')} [{res.get('short_hash')}]")
            print(f"Branch: {res.get('branch')}")
            print(f"Committed Files: {res.get('committed_files')}")
            print("=" * 60)
        else:
            print(f"Execution failed: {res.get('error')}")
            sys.exit(1)

    elif args.command == "history":
        records = exec_repo.list_executions(args.repo, limit=20)
        if not records:
            print(f"No execution history found for repository ID {args.repo}.")
            return
        print(f"\nExecution History for Repository ID {args.repo}:")
        print("-" * 80)
        for r in records:
            hash_str = r.commit_hash[:7] if r.commit_hash else "-------"
            msg = (r.commit_message or "").splitlines()[0] if r.commit_message else (r.error_summary or "")
            print(f"ID {r.id:3d} | {r.execution_mode:5s} | {r.status:17s} | {hash_str} | {msg[:35]}")
        print("-" * 80)

    elif args.command == "automation-mode":
        s = exec_repo.get_automation_settings(args.repo)
        print(f"\nAutomation Settings for Repository ID {args.repo}:")
        print(f"  - Execution Mode: {s.execution_mode}")
        print(f"  - Auto Commit Enabled: {s.auto_commit_enabled}")
        print(f"  - GitHub Push Enabled: {s.push_enabled}")
        print(f"  - Protected Branches: {s.protected_branches}")
        print(f"  - Mandatory Validations: {s.validation_required}")
        print(f"  - Quiet Period: {s.quiet_period_seconds}s")

    elif args.command == "set-mode":
        s = exec_repo.get_automation_settings(args.repo)
        if args.mode == "auto":
            if not args.confirm:
                print("WARNING: Auto Commit mode stages and commits approved changes automatically when policies pass.")
                print("To confirm and enable Auto Commit, run with --confirm flag:")
                print(f"  python main.py set-mode --repo {args.repo} --mode auto --confirm")
                return
            s.execution_mode = "auto"
            s.auto_commit_enabled = True
            exec_repo.save_automation_settings(s)
            print(f"Repository ID {args.repo} set to AUTO COMMIT mode (auto_commit_enabled=True).")
        else:
            s.execution_mode = "smart"
            s.auto_commit_enabled = False
            exec_repo.save_automation_settings(s)
            print(f"Repository ID {args.repo} set to SMART COMMIT mode (explicit approval required).")

    # --- Phase 3 CLI Handlers ---
    elif args.command == "permissions":
        try:
            perms = perm_mgr.get_permissions(args.repo)
            print(f"\nRepository {args.repo} Permissions:")
            print(f"  - Monitoring:                {perms.monitoring_enabled}")
            print(f"  - AI Analysis:               {perms.ai_analysis_enabled}")
            print(f"  - Autonomous Development:    {perms.autonomous_development_enabled}")
            print(f"  - Smart Commit:              {perms.smart_commit_enabled}")
            print(f"  - Auto Commit:               {perms.auto_commit_enabled}")
            print(f"  - Remote Push:               {perms.remote_push_enabled}")
            print(f"  - Last Updated: {perms.updated_at}")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.command == "enable-development":
        try:
            perms = perm_mgr.enable_autonomous_development(args.repo)
            print(f"Autonomous development ENABLED for repository ID {args.repo}.")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.command == "disable-development":
        try:
            perms = perm_mgr.disable_autonomous_development(args.repo)
            print(f"Autonomous development DISABLED for repository ID {args.repo}.")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.command == "schedule":
        schedule, sessions = scheduler.get_or_create_current_week_schedule()
        is_active = scheduler.is_active()
        print(f"\nWeekly Schedule [{schedule.week_identifier}] - Timezone: {schedule.timezone}")
        print(f"Active: {is_active}")
        print("-" * 60)
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for s in sessions:
            day_name = days[s.day_of_week] if s.day_of_week < 7 else f"Day {s.day_of_week}"
            print(f"  {s.scheduled_date} ({day_name}) | {s.time_window} | Status: {s.status}")
        print("-" * 60)

    elif args.command == "generate-schedule":
        schedule, sessions = scheduler.get_or_create_current_week_schedule(
            force_regenerate=args.force
        )
        print(f"Schedule [{schedule.week_identifier}] generated with {len(sessions)} sessions:")
        for s in sessions:
            print(f"  {s.scheduled_date} | {s.time_window}")

    elif args.command == "pause-scheduler":
        scheduler.pause()
        print("Autonomous development scheduler PAUSED.")

    elif args.command == "resume-scheduler":
        scheduler.resume()
        print("Autonomous development scheduler RESUMED.")

    elif args.command == "project-analyze":
        repo = db.get_repository(args.repo)
        if not repo:
            print(f"Repository ID {args.repo} not found.")
            sys.exit(1)
        ctx = project_analyzer.analyze_repository(args.repo, repo.repository_path)
        print(f"\nProject Analysis for '{repo.repository_name}':")
        print(f"  - Type: {ctx.project_type}")
        print(f"  - Language: {ctx.primary_language}")
        print(f"  - Framework: {ctx.framework}")
        print(f"  - Test Framework: {ctx.test_framework}")
        if ctx.summary:
            print(f"  - Description: {ctx.summary[:200]}")

    elif args.command == "add-task":
        repo = db.get_repository(args.repo)
        if not repo:
            print(f"Repository ID {args.repo} not found.")
            sys.exit(1)
        task = task_mgr.add_task(
            repository_id=args.repo,
            title=args.title,
            description=getattr(args, "description", None),
            task_type=getattr(args, "task_type", "feature"),
            priority=getattr(args, "priority", "medium"),
        )
        print(f"Task added (ID {task.id}): '{task.title}' [{task.task_type}/{task.priority}]")

    elif args.command == "list-tasks":
        tasks = task_mgr.get_pending_tasks(args.repo)
        if not tasks:
            print(f"No pending tasks for repository ID {args.repo}.")
            return
        print(f"\nPending Tasks for Repository ID {args.repo}:")
        print("-" * 70)
        for t in tasks:
            print(f"ID {t.id:3d} | {t.priority:6s} | {t.task_type:15s} | {t.title[:40]}")
        print("-" * 70)

    elif args.command == "development-run":
        from agents.development_agent import DevelopmentAgent
        from core.permission_manager import PermissionDeniedError
        repo = db.get_repository(args.repo)
        if not repo:
            print(f"Repository ID {args.repo} not found.")
            sys.exit(1)
        print(f"\nStarting autonomous development session for '{repo.repository_name}'...")
        dev_agent = DevelopmentAgent()
        try:
            result = dev_agent.run_development_session(
                repository_id=args.repo,
                isolated_worktree=not getattr(args, "no_worktree", False),
            )
            print(f"\nSession ID: {result.session_id}")
            print(f"Status: {result.status.upper()}")
            print(f"Branch: {result.branch_name}")
            if result.files_modified:
                print(f"Modified Files ({len(result.files_modified)}):")
                for f in result.files_modified:
                    print(f"  - {f}")
            if result.commit_hash:
                print(f"Commit: {result.commit_hash[:7]}")
            if result.error_message:
                print(f"Error: {result.error_message}")
            if result.tasks_summary:
                print(f"Summary: {result.tasks_summary}")
        except PermissionDeniedError as e:
            print(f"Permission denied: {e}")
            print(f"Tip: Run 'python main.py enable-development --repo {args.repo}' first.")
            sys.exit(1)

    elif args.command == "development-history":
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, session_date, branch_name, status, files_modified, commit_hash, tasks_summary
                FROM development_sessions WHERE repository_id = ? ORDER BY id DESC LIMIT 20
                """,
                (args.repo,),
            )
            rows = cursor.fetchall()
        if not rows:
            print(f"No development sessions found for repository ID {args.repo}.")
            return
        print(f"\nDevelopment History for Repository ID {args.repo}:")
        print("-" * 80)
        for r in rows:
            files = json.loads(r["files_modified"] or "[]")
            commit_str = r["commit_hash"][:7] if r["commit_hash"] else "-------"
            print(f"ID {r['id']:3d} | {r['session_date']} | {r['status']:10s} | {commit_str} | {len(files)} files")
        print("-" * 80)

    # --- Phase 4 Handlers ---
    elif args.command == "github-account":
        gh_client = GitHubClient()
        account = asyncio.run(gh_client.get_account_info())
        print("\n=== GitHub Account ===")
        print(f"Authenticated: {account['authenticated']} (Status: {account['status']})")
        if account.get("user"):
            u = account["user"]
            print(f"User: {u['login']} ({u['name'] or 'N/A'}) | Repos: {u['public_repos']} public, {u['total_private_repos']} private")
            print(f"URL: {u['html_url']}")
        if account.get("token_preview"):
            print(f"Token: {account['token_preview']}")
        if account.get("rate_limit"):
            rl = account["rate_limit"]
            print(f"Rate Limit: {rl['remaining']}/{rl['limit']}")

    elif args.command == "remote-status":
        inspector = RemoteStatusInspector()
        try:
            stat = inspector.get_remote_status(args.repo, refresh=True)
            print(f"\nRemote Status for Repo ID {args.repo}:")
            print(f"  - Local Branch:    {stat.local_branch}")
            print(f"  - Remote Branch:   {stat.remote_branch or '(None)'}")
            print(f"  - Commits Ahead:   {stat.ahead_count}")
            print(f"  - Commits Behind:  {stat.behind_count}")
            print(f"  - Sync Status:     {stat.sync_status.upper()}")
            print(f"  - Last Fetch:      {stat.last_fetch_at or 'Never'}")
            print(f"  - Last Push:       {stat.last_push_at or 'Never'}")
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.command == "fetch":
        sync_engine = GitHubSyncEngine()
        try:
            res = sync_engine.fetch_repository(args.repo)
            if res.get("success"):
                print(f"\nFetch successful for Repo ID {args.repo} on '{res.get('branch')}'.")
                print(f"Sync status: {res.get('sync_status')} (Ahead: {res.get('ahead_count')}, Behind: {res.get('behind_count')})")
            else:
                print(f"\nFetch failed: {res.get('error')}")
                sys.exit(1)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.command == "push":
        sync_engine = GitHubSyncEngine()
        try:
            res = sync_engine.push_repository(args.repo, branch=args.branch)
            if res.get("success"):
                if res.get("pushed", True):
                    print(f"\nPush SUCCESSFUL to '{res.get('remote')}/{res.get('branch')}'.")
                    print(f"Pushed Commit: {res.get('commit_hash')}")
                else:
                    print(f"\n{res.get('message')}")
            else:
                print(f"\nPush failed: {res.get('error')}")
                sys.exit(1)
        except PermissionDeniedError as e:
            print(f"\nPermission Denied: {e}")
            print(f"Tip: Run 'python main.py set-permission --repo {args.repo}' or enable Remote Push in dashboard.")
            sys.exit(1)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.command == "notifications":
        items = notification_manager.list_notifications(limit=30, unread_only=args.unread)
        if not items:
            print("\nNo notifications found.")
            return
        print(f"\nNotifications ({len(items)}):")
        print("-" * 80)
        for n in items:
            read_mark = " " if n.is_read else "*"
            print(f"[{read_mark}] ID {n.id:3d} | {n.severity.upper():7s} | {n.created_at[:19]} | {n.title}: {n.message[:45]}")
        print("-" * 80)

    elif args.command == "service":
        if args.action == "start":
            res = service_manager.start_service()
            print(res.get("message") or res.get("error"))
        elif args.action == "stop":
            res = service_manager.stop_service()
            print(res.get("message") or res.get("error"))
        elif args.action == "restart":
            res = service_manager.restart_service()
            print(res.get("message") or res.get("error"))
        elif args.action == "status":
            stat = service_manager.get_status()
            print(f"\nAutoGit AI Background Service Status:")
            print(f"  - Running:   {stat['is_running']}")
            print(f"  - PID:       {stat['pid'] or 'N/A'}")
            print(f"  - Lock File: {stat['lock_file']}")
        elif args.action == "health":
            hm = HealthMonitor()
            h = hm.check_health()
            print(f"\nService Health [{h['status'].upper()}]:")
            print(f"  - Uptime:    {h['uptime_seconds']} seconds")
            print(f"  - Database:  {'Connected' if h['database']['connected'] else h['database']['error']}")
            print(f"  - Scheduler: {'Active' if h['scheduler']['active'] else 'Paused'} ({h['scheduler']['timezone']})")
            print(f"  - Monitors:  {h['monitoring']['active_observers']} active observers")


if __name__ == "__main__":
    run_cli()
