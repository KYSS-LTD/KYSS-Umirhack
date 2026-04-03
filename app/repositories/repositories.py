from datetime import datetime
from sqlalchemy.orm import Session

from app.models.models import Agent, Task, TaskStatus, User


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def upsert_agent(db: Session, agent_uid: str, hostname: str, public_key: str) -> Agent:
    agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
    if agent:
        agent.hostname = hostname
        agent.public_key = public_key
    else:
        agent = Agent(agent_uid=agent_uid, hostname=hostname, public_key=public_key)
        db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def get_agent_by_uid(db: Session, agent_uid: str) -> Agent | None:
    return db.query(Agent).filter(Agent.agent_uid == agent_uid).first()


def touch_agent(db: Session, agent: Agent) -> None:
    agent.last_seen_at = datetime.utcnow()
    db.commit()


def create_task(db: Session, task_uid: str, task_type: str, command: str | None) -> Task:
    task = Task(task_uid=task_uid, task_type=task_type, command=command, status=TaskStatus.pending)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_next_task_for_agent(db: Session, agent: Agent) -> Task | None:
    task = db.query(Task).filter(Task.status == TaskStatus.pending).order_by(Task.created_at.asc()).first()
    if task:
        task.status = TaskStatus.assigned
        task.agent_id = agent.id
        db.commit()
        db.refresh(task)
    return task


def get_task_by_uid(db: Session, task_uid: str) -> Task | None:
    return db.query(Task).filter(Task.task_uid == task_uid).first()
