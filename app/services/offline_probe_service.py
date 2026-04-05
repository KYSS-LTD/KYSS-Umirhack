import asyncio
import uuid
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.models import Agent, Task, TaskStatus

settings = get_settings()


class OfflineProbeService:
    async def loop(self) -> None:
        while True:
            db = SessionLocal()
            try:
                self._enqueue_probes(db)
            except Exception:
                pass
            finally:
                db.close()
            await asyncio.sleep(max(10, settings.offline_probe_interval_seconds))

    def _enqueue_probes(self, db) -> None:
        probe_type = 'check_system_info' if 'check_system_info' in settings.allowed_task_type_set else None
        if not probe_type:
            return

        cooldown_cutoff = datetime.utcnow() - timedelta(seconds=max(30, settings.offline_probe_cooldown_seconds))
        offline_agents = db.query(Agent).filter((Agent.is_online.is_(False)) | (Agent.revoked.is_(True))).all()
        for agent in offline_agents:
            exists_recent_probe = (
                db.query(Task)
                .filter(
                    Task.agent_id == agent.id,
                    Task.task_type == probe_type,
                    Task.status.in_([TaskStatus.pending, TaskStatus.running]),
                )
                .first()
            )
            if exists_recent_probe:
                continue

            finished_recent_probe = (
                db.query(Task)
                .filter(
                    Task.agent_id == agent.id,
                    Task.task_type == probe_type,
                    Task.finished_at.is_not(None),
                    Task.finished_at >= cooldown_cutoff,
                )
                .first()
            )
            if finished_recent_probe:
                continue

            db.add(Task(task_uid=uuid.uuid4().hex, task_type=probe_type, command=None, status=TaskStatus.pending, agent_id=agent.id))
        db.commit()


offline_probe_service = OfflineProbeService()
