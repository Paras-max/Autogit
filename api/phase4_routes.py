"""
FastAPI route handlers for AutoGit AI Phase 4:
- GitHub Account & Synchronization
- Real-time Dashboard Analytics, Activity, and Commit History
- In-App Notifications
- Background Service & Health Monitoring
- Live Server-Sent Events (SSE) Stream
"""

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from api.routes import get_db
from database.execution_repository import ExecutionRepository
from api.schemas import (
    CommitDetailResponse,
    DashboardActivityItem,
    DashboardOverviewResponse,
    GenericMessageResponse,
    GitHubPushRequest,
    GitHubSyncHistoryResponse,
    NotificationResponse,
    RemoteStatusResponse,
    ServiceStatusResponse,
    SyncOperationResponse,
)
from background.health_monitor import HealthMonitor
from background.service_manager import service_manager
from core.git_manager import GitManager
from core.permission_manager import PermissionDeniedError, PermissionManager
from database.db import DatabaseManager
from database.execution_repository import ExecutionRepository
from database.notification_repository import NotificationRepository
from database.preference_repository import PreferenceRepository
from database.sync_repository import SyncRepository
from integrations.github_client import GitHubClient
from integrations.github_sync import GitHubSyncEngine
from integrations.remote_status import RemoteStatusInspector
from monitoring.file_monitor import file_monitor
from notifications.event_dispatcher import event_dispatcher
from notifications.notification_manager import notification_manager
from scheduler.weekly_scheduler import WeeklyScheduler
from utils.logger import logger
from utils.security import safe_subprocess_run


phase4_router = APIRouter()


# Dependency injection helpers
def get_sync_repo(db_mgr: DatabaseManager = Depends(get_db)) -> SyncRepository:
    return SyncRepository(db_mgr)


def get_notif_repo(db_mgr: DatabaseManager = Depends(get_db)) -> NotificationRepository:
    return NotificationRepository(db_mgr)


def get_pref_repo(db_mgr: DatabaseManager = Depends(get_db)) -> PreferenceRepository:
    return PreferenceRepository(db_mgr)


def get_github_client(db_mgr: DatabaseManager = Depends(get_db)) -> GitHubClient:
    return GitHubClient(db_mgr)


def get_remote_inspector(db_mgr: DatabaseManager = Depends(get_db)) -> RemoteStatusInspector:
    return RemoteStatusInspector(db_mgr)


def get_sync_engine(db_mgr: DatabaseManager = Depends(get_db)) -> GitHubSyncEngine:
    return GitHubSyncEngine(db_mgr)


def get_health_monitor(db_mgr: DatabaseManager = Depends(get_db)) -> HealthMonitor:
    return HealthMonitor(db_mgr)


# ============================================================================
# 1. GitHub Account & Synchronization Endpoints
# ============================================================================

@phase4_router.post(
    "/github/push",
    response_model=SyncOperationResponse,
    summary="Push an authorized commit or branch to remote with verification",
)
def push_commit_endpoint(
    req: GitHubPushRequest,
    sync_engine: GitHubSyncEngine = Depends(get_sync_engine),
):
    """
    Step 3: Secure push endpoint.
    Derives and validates the actual local commit and source branch.
    Never assumes main branch for autonomous development commits.
    Enforces repository-level remote_push permission.
    Verifies remote commit reachable before returning success.
    """
    exec_id = req.execution_id or req.commit_id
    try:
        res = sync_engine.push_repository(
            repository_id=req.repository_id,
            execution_id=exec_id,
            commit_hash=req.commit_hash,
            branch=req.branch,
            remote_name=req.remote_name or "origin",
            target_branch=req.target_branch,
        )
        if not res.get("success") and not res.get("pushed"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.get("error", "Push failed"))
        return SyncOperationResponse(**res)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@phase4_router.get(
    "/github/sync-status/{repo_id}",
    summary="Get detailed commit synchronization and verification status",
)
def get_commit_sync_status(
    repo_id: int,
    sync_engine: GitHubSyncEngine = Depends(get_sync_engine),
):
    try:
        return sync_engine.get_sync_status(repo_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@phase4_router.get(
    "/github/pending/{repo_id}",
    summary="List local commits pending synchronization to remote",
)
def get_pending_sync_commits(
    repo_id: int,
    limit: int = 50,
    sync_engine: GitHubSyncEngine = Depends(get_sync_engine),
):
    try:
        return sync_engine.get_pending_commits(repo_id, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@phase4_router.get(
    "/github/push-history/{repo_id}",
    summary="Get push attempt audit history",
)
def get_push_audit_history(
    repo_id: int,
    limit: int = 20,
    sync_engine: GitHubSyncEngine = Depends(get_sync_engine),
):
    try:
        return sync_engine.get_push_history(repo_id, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@phase4_router.post(
    "/github/retry/{execution_id}",
    response_model=SyncOperationResponse,
    summary="Retry a failed or pending push for an execution record",
)
def retry_failed_push(
    execution_id: int,
    remote_name: str = "origin",
    sync_engine: GitHubSyncEngine = Depends(get_sync_engine),
):
    try:
        res = sync_engine.retry_push(execution_id, remote_name=remote_name)
        if not res.get("success"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.get("error", "Retry push failed"))
        return SyncOperationResponse(**res)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@phase4_router.get("/github/account", summary="Get authenticated GitHub account info and rate limit")
async def get_github_account(client: GitHubClient = Depends(get_github_client)):
    return await client.get_account_info()


@phase4_router.get("/github/repositories", summary="List remote GitHub repositories accessible with token")
async def get_github_repositories(
    per_page: int = 50,
    client: GitHubClient = Depends(get_github_client),
):
    return await client.list_repositories(per_page=per_page)


@phase4_router.post("/github/disconnect", response_model=GenericMessageResponse, summary="Disconnect GitHub account")
def disconnect_github(client: GitHubClient = Depends(get_github_client)):
    client.disconnect_account()
    return GenericMessageResponse(success=True, message="GitHub account disconnected successfully.")


@phase4_router.get(
    "/github/sync/status/{repository_id}",
    response_model=RemoteStatusResponse,
    summary="Get remote repository synchronization status",
)
def get_remote_status(
    repository_id: int,
    inspector: RemoteStatusInspector = Depends(get_remote_inspector),
):
    try:
        status_model = inspector.get_remote_status(repository_id, refresh=True)
        return RemoteStatusResponse(**dataclasses.asdict(status_model))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@phase4_router.post(
    "/github/sync/fetch/{repository_id}",
    response_model=SyncOperationResponse,
    summary="Fetch from remote without modifying local working tree",
)
def fetch_from_remote(
    repository_id: int,
    sync_engine: GitHubSyncEngine = Depends(get_sync_engine),
):
    try:
        res = sync_engine.fetch_repository(repository_id)
        if not res.get("success"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.get("error"))
        return SyncOperationResponse(**res)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@phase4_router.post(
    "/github/sync/push/{repository_id}",
    response_model=SyncOperationResponse,
    summary="Push authorized commits to remote (enforces remote_push permission)",
)
def push_to_remote(
    repository_id: int,
    branch: Optional[str] = None,
    sync_engine: GitHubSyncEngine = Depends(get_sync_engine),
):
    try:
        res = sync_engine.push_repository(repository_id, branch=branch)
        if not res.get("success") and not res.get("pushed"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=res.get("error"))
        return SyncOperationResponse(**res)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@phase4_router.get(
    "/github/sync/history/{repository_id}",
    response_model=List[GitHubSyncHistoryResponse],
    summary="Get GitHub synchronization audit history",
)
def get_sync_history(
    repository_id: int,
    limit: int = 20,
    sync_repo: SyncRepository = Depends(get_sync_repo),
):
    records = sync_repo.list_sync_history(repository_id, limit=limit)
    return [GitHubSyncHistoryResponse(**dataclasses.asdict(r)) for r in records]


# ============================================================================
# 2. Main Dashboard & Analytics Endpoints
# ============================================================================

@phase4_router.get(
    "/dashboard/overview",
    response_model=DashboardOverviewResponse,
    summary="Get real-time dashboard overview metrics",
)
def get_dashboard_overview(db_mgr: DatabaseManager = Depends(get_db)):
    perm_mgr = PermissionManager(db_mgr)
    scheduler = WeeklyScheduler(db_mgr)

    total_repos = len(db_mgr.list_repositories())
    auth_repos = len(perm_mgr.get_authorized_repositories("monitoring"))

    # Active sessions
    with db_mgr.get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as cnt FROM development_sessions WHERE status = 'running'")
        active_sessions = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM execution_history WHERE status = 'committed'")
        total_commits = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM execution_history WHERE status = 'awaiting_approval'")
        pending_approvals = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM validation_results WHERE status = 'FAILED'")
        validation_failures = cursor.fetchone()["cnt"]

    schedule, _ = scheduler.get_or_create_current_week_schedule()
    scheduler_active = scheduler.is_active()
    monitoring_active = len(file_monitor._observers) > 0

    return DashboardOverviewResponse(
        total_repositories=total_repos,
        authorized_repositories=auth_repos,
        active_sessions=active_sessions,
        total_commits=total_commits,
        pending_approvals=pending_approvals,
        validation_failures=validation_failures,
        monitoring_active=monitoring_active,
        scheduler_active=scheduler_active,
        current_week=schedule.week_identifier,
        agents_online=8,
    )


@phase4_router.get(
    "/dashboard/activity",
    response_model=List[DashboardActivityItem],
    summary="Get combined chronological activity stream",
)
def get_dashboard_activity(
    limit: int = 30, db_mgr: DatabaseManager = Depends(get_db)
):
    items: List[DashboardActivityItem] = []

    # Commits & Proposals from execution_history
    with db_mgr.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT e.id, e.repository_id, e.execution_mode, e.status, e.commit_hash, e.commit_message,
                   e.created_at, e.error_summary, r.repository_name
            FROM execution_history e
            LEFT JOIN repositories r ON e.repository_id = r.id
            ORDER BY e.id DESC LIMIT ?
            """,
            (limit,),
        )
        for r in cursor.fetchall():
            items.append(
                DashboardActivityItem(
                    id=f"exec-{r['id']}",
                    type="commit" if r["status"] == "committed" else "proposal",
                    repository_id=r["repository_id"],
                    repository_name=r["repository_name"],
                    title=f"{r['execution_mode'].upper()} Commit [{r['status']}]",
                    description=(r["commit_message"] or r["error_summary"] or "Execution proposal")[:120],
                    timestamp=r["created_at"],
                    status=r["status"],
                )
            )

        # Development sessions
        cursor.execute(
            """
            SELECT d.id, d.repository_id, d.status, d.branch_name, d.tasks_summary, d.created_at, r.repository_name
            FROM development_sessions d
            LEFT JOIN repositories r ON d.repository_id = r.id
            ORDER BY d.id DESC LIMIT ?
            """,
            (limit,),
        )
        for r in cursor.fetchall():
            items.append(
                DashboardActivityItem(
                    id=f"dev-{r['id']}",
                    type="session",
                    repository_id=r["repository_id"],
                    repository_name=r["repository_name"],
                    title=f"Autonomous Session ({r['branch_name']})",
                    description=r["tasks_summary"] or "Development session",
                    timestamp=r["created_at"],
                    status=r["status"],
                )
            )

    items.sort(key=lambda x: x.timestamp, reverse=True)
    return items[:limit]


@phase4_router.get("/dashboard/agents", summary="Get status and details of all 8 AI agents")
def get_dashboard_agents(db_mgr: DatabaseManager = Depends(get_db)):
    agents = [
        {"name": "Diff Analysis Agent", "role": "Analyzes modified, added, deleted files & diff chunking", "status": "online"},
        {"name": "Code Understanding Agent", "role": "Analyzes semantic intent, language, and change risk", "status": "online"},
        {"name": "Change Grouping Agent", "role": "Groups cohesive multi-file changes into atomic units", "status": "online"},
        {"name": "Commit Message Generator", "role": "Generates Conventional Commit messages with heuristic fallback", "status": "online"},
        {"name": "Validation Agent", "role": "Orchestrates secret scanner, policy checks, test runners", "status": "online"},
        {"name": "Development Agent", "role": "Executes autonomous development sessions in isolated worktrees", "status": "online"},
        {"name": "Task Planning Agent", "role": "Selects and formulates 2-3 targeted improvement tasks", "status": "online"},
        {"name": "Development Review Agent", "role": "Pre-commit peer review for task satisfaction and code quality", "status": "online"},
    ]
    return {"total_agents": len(agents), "agents": agents}


@phase4_router.get("/dashboard/upcoming-sessions", summary="Get upcoming scheduled sessions for current week")
def get_upcoming_sessions(db_mgr: DatabaseManager = Depends(get_db)):
    scheduler = WeeklyScheduler(db_mgr)
    schedule, sessions = scheduler.get_or_create_current_week_schedule()
    today_str = scheduler.get_current_time().date().isoformat()
    upcoming = [s for s in sessions if s.scheduled_date >= today_str]
    return {
        "week": schedule.week_identifier,
        "upcoming_count": len(upcoming),
        "sessions": [dataclasses.asdict(s) for s in upcoming],
    }


# ============================================================================
# 3. Commit History Endpoints
# ============================================================================

@phase4_router.get("/dashboard/commits", summary="List commits across registered repositories")
def list_commits(
    repository_id: Optional[int] = None,
    limit: int = 30,
    db_mgr: DatabaseManager = Depends(get_db),
):
    repos = [db_mgr.get_repository(repository_id)] if repository_id else db_mgr.list_repositories()
    commits_list = []

    for repo in repos:
        if not repo or not Path(repo.repository_path).exists():
            continue
        repo_path = Path(repo.repository_path)
        git_mgr = GitManager(repo_path)
        branch = git_mgr.get_current_branch() or "main"

        # Build mapping of commit_hash -> (push_sync_status, execution_id) from execution_history
        hash_to_sync: Dict[str, Any] = {}
        with db_mgr.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, commit_hash, push_sync_status, branch_name
                FROM execution_history
                WHERE repository_id = ? AND commit_hash IS NOT NULL
                ORDER BY id DESC
                """,
                (repo.id,),
            )
            for row in cursor.fetchall():
                d = dict(row)
                ch = (d.get("commit_hash") or "").strip()
                if ch and ch not in hash_to_sync:
                    hash_to_sync[ch] = {
                        "push_sync_status": d.get("push_sync_status", "LOCAL_ONLY"),
                        "execution_id": d["id"],
                        "branch_name": d.get("branch_name"),
                    }

        # Read git log: format: hash|short_hash|author|date|subject
        exit_code, stdout, _ = safe_subprocess_run(
            ["git", "log", f"-{limit}", "--pretty=format:%H|%h|%an|%cI|%s", "--all"],
            cwd=repo_path,
            timeout=10.0,
        )
        if exit_code == 0 and stdout:
            for line in stdout.splitlines():
                parts = line.split("|", 4)
                if len(parts) >= 5:
                    fhash, shash, author, dt, subj = parts
                    github_url = f"{repo.remote_url.rstrip('.git')}/commit/{fhash}" if repo.remote_url and "github.com" in repo.remote_url else None

                    # Determine push_sync_status: check if on origin
                    sync_info = hash_to_sync.get(fhash) or {}
                    push_sync_status = sync_info.get("push_sync_status", "LOCAL_ONLY")
                    execution_id = sync_info.get("execution_id")

                    # If not in DB, check if already pushed via git branch -r --contains
                    if not sync_info:
                        rc_br, br_out, _ = safe_subprocess_run(
                            ["git", "branch", "-r", "--contains", fhash],
                            cwd=repo_path,
                            timeout=5.0,
                        )
                        if rc_br == 0 and "origin/" in br_out:
                            push_sync_status = "PUSHED"
                        else:
                            push_sync_status = "LOCAL_ONLY"

                    commits_list.append(
                        {
                            "commit_hash": fhash,
                            "short_hash": shash,
                            "message": subj,
                            "author": author,
                            "date": dt,
                            "branch": sync_info.get("branch_name") or branch,
                            "repository_id": repo.id,
                            "repository_name": repo.repository_name,
                            "github_commit_url": github_url,
                            "push_sync_status": push_sync_status,
                            "execution_id": execution_id,
                        }
                    )

    commits_list.sort(key=lambda x: x["date"], reverse=True)
    return commits_list[:limit]


@phase4_router.get(
    "/dashboard/commits/{commit_hash}",
    response_model=CommitDetailResponse,
    summary="Get commit details and changed file list",
)
def get_commit_detail(
    commit_hash: str,
    repository_id: Optional[int] = None,
    db_mgr: DatabaseManager = Depends(get_db),
):
    repos = [db_mgr.get_repository(repository_id)] if repository_id else db_mgr.list_repositories()
    for repo in repos:
        if not repo or not Path(repo.repository_path).exists():
            continue
        repo_path = Path(repo.repository_path)
        # Check if commit exists in this repo
        exit_code, stdout, _ = safe_subprocess_run(
            ["git", "cat-file", "-t", commit_hash], cwd=repo_path, timeout=5.0
        )
        if exit_code == 0 and stdout.strip() == "commit":
            # Extract commit info
            _, meta, _ = safe_subprocess_run(
                ["git", "show", "--pretty=format:%H|%h|%an|%cI|%B---FILES---", "--name-only", commit_hash],
                cwd=repo_path,
                timeout=10.0,
            )
            parts = meta.split("---FILES---")
            header = parts[0]
            files_part = parts[1] if len(parts) > 1 else ""
            h_parts = header.split("|", 4)
            if len(h_parts) >= 5:
                fhash, shash, author, dt, msg = h_parts
                files_changed = [f.strip() for f in files_part.splitlines() if f.strip()]
                github_url = f"{repo.remote_url.rstrip('.git')}/commit/{fhash}" if repo.remote_url and "github.com" in repo.remote_url else None
                return CommitDetailResponse(
                    commit_hash=fhash,
                    short_hash=shash,
                    message=msg.strip(),
                    author=author,
                    date=dt,
                    branch=GitManager(repo_path).get_current_branch() or "main",
                    repository_id=repo.id,
                    repository_name=repo.repository_name,
                    files_changed=files_changed,
                    github_commit_url=github_url,
                    validation_status="PASSED",
                )

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Commit '{commit_hash}' not found in registered repositories.")


# ============================================================================
# 4. Notifications Endpoints
# ============================================================================

@phase4_router.get(
    "/notifications",
    response_model=List[NotificationResponse],
    summary="List in-app notifications",
)
def get_notifications(
    limit: int = 50,
    unread_only: bool = False,
    notif_repo: NotificationRepository = Depends(get_notif_repo),
):
    items = notif_repo.list_notifications(limit=limit, unread_only=unread_only)
    return [NotificationResponse(**dataclasses.asdict(i)) for i in items]


@phase4_router.post(
    "/notifications/{notification_id}/read",
    response_model=GenericMessageResponse,
    summary="Mark single notification as read",
)
def mark_notification_read(
    notification_id: int,
    notif_repo: NotificationRepository = Depends(get_notif_repo),
):
    success = notif_repo.mark_read(notification_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return GenericMessageResponse(success=True, message="Notification marked as read.")


@phase4_router.post(
    "/notifications/read-all",
    response_model=GenericMessageResponse,
    summary="Mark all notifications as read",
)
def mark_all_notifications_read(
    notif_repo: NotificationRepository = Depends(get_notif_repo),
):
    count = notif_repo.mark_all_read()
    return GenericMessageResponse(success=True, message=f"Marked {count} notifications as read.")


@phase4_router.get("/notifications/unread-count", summary="Get unread notifications count")
def get_unread_count(notif_repo: NotificationRepository = Depends(get_notif_repo)):
    return {"unread_count": notif_repo.get_unread_count()}


# ============================================================================
# 5. Background Service & Health Endpoints
# ============================================================================

@phase4_router.get("/service/status", response_model=ServiceStatusResponse, summary="Get background service process status")
def get_service_status():
    stat = service_manager.get_status()
    return ServiceStatusResponse(
        is_running=stat["is_running"],
        pid=stat["pid"],
        lock_file=stat["lock_file"],
        status="running" if stat["is_running"] else "stopped",
    )


@phase4_router.post("/service/start", response_model=GenericMessageResponse, summary="Start background service")
def start_service():
    res = service_manager.start_service()
    return GenericMessageResponse(success=res["success"], message=res.get("message") or res.get("error", "Error"))


@phase4_router.post("/service/stop", response_model=GenericMessageResponse, summary="Stop background service")
def stop_service():
    res = service_manager.stop_service()
    return GenericMessageResponse(success=res["success"], message=res.get("message") or res.get("error", "Error"))


@phase4_router.post("/service/restart", response_model=GenericMessageResponse, summary="Restart background service")
def restart_service():
    res = service_manager.restart_service()
    return GenericMessageResponse(success=res["success"], message=res.get("message") or res.get("error", "Error"))


@phase4_router.get("/service/health", summary="Get comprehensive health inspection report")
def get_service_health(health_mgr: HealthMonitor = Depends(get_health_monitor)):
    return health_mgr.check_health()


# ============================================================================
# 6. Live Event Streaming (Server-Sent Events)
# ============================================================================

@phase4_router.get(
    "/events/stream",
    summary="Live Server-Sent Events (SSE) stream for real-time dashboard updates",
)
async def event_stream():
    """Streams live application events via Server-Sent Events (SSE)."""
    queue = await event_dispatcher.subscribe()

    async def _sse_generator():
        try:
            # Initial connection handshake event
            yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'message': 'Subscribed to AutoGit AI live events'})}\n\n"

            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                    event_type = payload.get("event", "message")
                    data_str = json.dumps(payload)
                    yield f"event: {event_type}\ndata: {data_str}\n\n"
                except asyncio.TimeoutError:
                    # Send periodic keepalive comment so connection does not time out
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await event_dispatcher.unsubscribe(queue)

    return StreamingResponse(
        _sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================================================
# 7. Commit Push Sync Endpoints
# ============================================================================

@phase4_router.get("/commits/pending", summary="List execution history records awaiting approval")
def get_pending_commits(
    repository_id: Optional[int] = None,
    limit: int = 50,
    db_mgr: DatabaseManager = Depends(get_db),
):
    """List execution_history records with status='awaiting_approval'."""
    with db_mgr.get_cursor() as cursor:
        if repository_id:
            cursor.execute(
                """
                SELECT e.id, e.repository_id, e.execution_mode, e.status, e.commit_hash,
                       e.commit_message, e.created_at, e.proposal_data, e.push_sync_status,
                       e.branch_name, r.repository_name, r.remote_url
                FROM execution_history e
                LEFT JOIN repositories r ON e.repository_id = r.id
                WHERE e.status = 'awaiting_approval' AND e.repository_id = ?
                ORDER BY e.id DESC LIMIT ?
                """,
                (repository_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT e.id, e.repository_id, e.execution_mode, e.status, e.commit_hash,
                       e.commit_message, e.created_at, e.proposal_data, e.push_sync_status,
                       e.branch_name, r.repository_name, r.remote_url
                FROM execution_history e
                LEFT JOIN repositories r ON e.repository_id = r.id
                WHERE e.status = 'awaiting_approval'
                ORDER BY e.id DESC LIMIT ?
                """,
                (limit,),
            )
        rows = cursor.fetchall()

    result = []
    for r in rows:
        d = dict(r)
        proposal_data = {}
        try:
            import json as _json
            proposal_data = _json.loads(d.get("proposal_data") or "{}")
        except Exception:
            pass
        result.append({
            "execution_id": d["id"],
            "repository_id": d["repository_id"],
            "repository_name": d["repository_name"],
            "execution_mode": d["execution_mode"],
            "status": d["status"],
            "commit_hash": d["commit_hash"],
            "commit_message": d["commit_message"],
            "created_at": d["created_at"],
            "push_sync_status": d.get("push_sync_status", "LOCAL_ONLY"),
            "branch_name": d.get("branch_name"),
            "proposed_files": proposal_data.get("staged_files", []),
        })
    return result


@phase4_router.get("/commits/history", summary="List all execution history records with push sync status")
def get_commit_execution_history(
    repository_id: Optional[int] = None,
    limit: int = 50,
    db_mgr: DatabaseManager = Depends(get_db),
):
    """List execution_history records with their push_sync_status (committed executions + pending)."""
    with db_mgr.get_cursor() as cursor:
        if repository_id:
            cursor.execute(
                """
                SELECT e.id, e.repository_id, e.execution_mode, e.status, e.commit_hash,
                       e.commit_message, e.created_at, e.completed_at, e.error_summary,
                       e.push_sync_status, e.branch_name, r.repository_name, r.remote_url
                FROM execution_history e
                LEFT JOIN repositories r ON e.repository_id = r.id
                WHERE e.repository_id = ?
                ORDER BY e.id DESC LIMIT ?
                """,
                (repository_id, limit),
            )
        else:
            cursor.execute(
                """
                SELECT e.id, e.repository_id, e.execution_mode, e.status, e.commit_hash,
                       e.commit_message, e.created_at, e.completed_at, e.error_summary,
                       e.push_sync_status, e.branch_name, r.repository_name, r.remote_url
                FROM execution_history e
                LEFT JOIN repositories r ON e.repository_id = r.id
                ORDER BY e.id DESC LIMIT ?
                """,
                (limit,),
            )
        rows = cursor.fetchall()

    return [
        {
            "execution_id": dict(r)["id"],
            "repository_id": dict(r)["repository_id"],
            "repository_name": dict(r)["repository_name"],
            "execution_mode": dict(r)["execution_mode"],
            "status": dict(r)["status"],
            "commit_hash": dict(r)["commit_hash"],
            "commit_message": dict(r)["commit_message"],
            "created_at": dict(r)["created_at"],
            "completed_at": dict(r)["completed_at"],
            "error_summary": dict(r)["error_summary"],
            "push_sync_status": dict(r).get("push_sync_status", "LOCAL_ONLY"),
            "branch_name": dict(r).get("branch_name"),
            "remote_url": dict(r)["remote_url"],
        }
        for r in rows
    ]


@phase4_router.post("/commits/{execution_id}/push", summary="Push the branch containing a specific committed execution")
def push_execution_commit(
    execution_id: int,
    db_mgr: DatabaseManager = Depends(get_db),
    sync_engine: GitHubSyncEngine = Depends(get_sync_engine),
):
    """
    Push the branch that contains the given execution's commit to origin.
    Steps:
    1. Load execution record from DB.
    2. Enforce remote_push permission.
    3. Determine and validate branch from execution record or development_sessions.
    4. Execute secure push via GIT_ASKPASS credential handler.
    5. Verify remote commit reachable via merge-base.
    6. Return verified result.
    """
    exec_repo = ExecutionRepository(db_mgr)
    execution = exec_repo.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Execution {execution_id} not found.")

    try:
        result = sync_engine.push_repository(
            repository_id=execution.repository_id,
            execution_id=execution_id,
        )
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not result.get("success") and result.get("pushed") is not False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error", "Push failed"))

    return {**result, "execution_id": execution_id}


@phase4_router.get("/commits/{execution_id}/sync-status", summary="Get push_sync_status for a specific execution")
def get_execution_sync_status(execution_id: int, db_mgr: DatabaseManager = Depends(get_db)):
    with db_mgr.get_cursor() as cursor:
        cursor.execute(
            "SELECT id, status, commit_hash, push_sync_status, branch_name FROM execution_history WHERE id = ?",
            (execution_id,),
        )
        row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Execution {execution_id} not found.")
    d = dict(row)
    return {
        "execution_id": d["id"],
        "status": d["status"],
        "commit_hash": d["commit_hash"],
        "push_sync_status": d.get("push_sync_status", "LOCAL_ONLY"),
        "branch_name": d.get("branch_name"),
    }


@phase4_router.post(
    "/github/sync/push-branch/{repository_id}",
    summary="Push a specific named branch to origin (for autonomous dev session branches)",
)
def push_named_branch(
    repository_id: int,
    body: Optional[Dict[str, Any]] = None,
    branch: Optional[str] = Query(default=None),
    sync_engine: GitHubSyncEngine = Depends(get_sync_engine),
):
    """
    Push a specific branch to origin.
    Branch can be specified via:
    - Query parameter: ?branch=autogit/dev-...
    - JSON body: {"branch": "autogit/dev-..."}
    """
    target_branch = branch
    if not target_branch and body:
        target_branch = body.get("branch")

    if not target_branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Branch name is required. Pass via query param ?branch=... or JSON body {\"branch\": \"...\"}",
        )

    try:
        result = sync_engine.push_repository(repository_id=repository_id, branch=target_branch)
    except PermissionDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    if not result.get("success") and result.get("pushed") is not False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error", "Push failed"))

    return result
