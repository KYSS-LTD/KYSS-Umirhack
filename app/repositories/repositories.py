from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.models import Agent, AgentEvent, Task, TaskStatus, User


EVENT_ONLINE = 'online'
EVENT_OFFLINE = 'offline'


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def create_user(db: Session, username: str, password_hash: str) -> User:
    user = User(username=username, password_hash=password_hash, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_or_update_agent(
    db: Session,
    agent_uid: str,
    hostname: str,
    public_key: str,
    agent_token: str,
    ip_addresses: str | None = None,
    os_version: str | None = None,
    network_interfaces: str | None = None,
) -> Agent:
    agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
    if agent:
        agent.hostname = hostname
        if public_key:
            agent.public_key = public_key
        if agent_token:
            agent.agent_token = agent_token
        agent.revoked = False
        if ip_addresses is not None:
            agent.ip_addresses = ip_addresses
        if os_version is not None:
            agent.os_version = os_version
        if network_interfaces is not None:
            agent.network_interfaces = network_interfaces
    else:
        agent = Agent(
            agent_uid=agent_uid,
            hostname=hostname,
            public_key=public_key,
            agent_token=agent_token,
            ip_addresses=ip_addresses,
            os_version=os_version,
            network_interfaces=network_interfaces,
            is_online=True,
            last_seen_at=datetime.utcnow(),
        )
        db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def get_agent_by_uid(db: Session, agent_uid: str) -> Agent | None:
    return db.query(Agent).filter(Agent.agent_uid == agent_uid).first()


def get_agent_by_token(db: Session, token: str) -> Agent | None:
    return db.query(Agent).filter(Agent.agent_token == token).first()


def add_agent_event(db: Session, agent: Agent, event_type: str, details: str | None = None) -> None:
    db.add(AgentEvent(agent_id=agent.id, event_type=event_type, details=details))


def touch_agent(db: Session, agent: Agent, payload: dict | None = None) -> None:
    was_online = bool(agent.is_online)
    agent.last_seen_at = datetime.utcnow()
    agent.is_online = True
    if not was_online:
        add_agent_event(db, agent, EVENT_ONLINE, 'agent heartbeat restored')

    if payload:
        if payload.get('ip_addresses') is not None:
            agent.ip_addresses = str(payload.get('ip_addresses'))[:1000]
        if payload.get('os_version') is not None:
            agent.os_version = str(payload.get('os_version'))[:255]
        if payload.get('network_interfaces') is not None:
            agent.network_interfaces = str(payload.get('network_interfaces'))[:2000]
    db.commit()


def mark_offline_agents(db: Session, offline_seconds: int = 30) -> int:
    threshold = datetime.utcnow() - timedelta(seconds=offline_seconds)
    agents = (
        db.query(Agent)
        .filter(Agent.is_online.is_(True), Agent.last_seen_at.is_not(None), Agent.last_seen_at < threshold)
        .all()
    )
    for agent in agents:
        agent.is_online = False
        add_agent_event(db, agent, EVENT_OFFLINE, f'no heartbeat > {offline_seconds}s')
    db.commit()
    return len(agents)


def list_recent_agent_events(db: Session, limit: int = 100) -> list[AgentEvent]:
    return db.query(AgentEvent).order_by(AgentEvent.created_at.desc()).limit(limit).all()


def create_task(db: Session, task_uid: str, task_type: str, command: str | None, agent_id: int | None = None) -> Task:
    task = Task(task_uid=task_uid, task_type=task_type, command=command, status=TaskStatus.pending, agent_id=agent_id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_next_task_for_agent(db: Session, agent: Agent) -> Task | None:
    task = (
        db.query(Task)
        .filter(Task.status == TaskStatus.pending)
        .filter((Task.agent_id.is_(None)) | (Task.agent_id == agent.id))
        .order_by(Task.created_at.asc())
        .first()
    )
    if task:
        task.status = TaskStatus.running
        task.agent_id = agent.id
        task.started_at = datetime.utcnow()
        db.commit()
        db.refresh(task)
    return task


def get_task_by_uid(db: Session, task_uid: str) -> Task | None:
    return db.query(Task).filter(Task.task_uid == task_uid).first()
