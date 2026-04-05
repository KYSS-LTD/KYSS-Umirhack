import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TaskStatus(str, enum.Enum):
    pending = 'pending'
    running = 'running'
    done = 'done'
    failed = 'failed'


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserAccess(Base):
    __tablename__ = 'user_access'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    can_view_agents: Mapped[bool] = mapped_column(Boolean, default=False)
    can_create_tasks: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped[User] = relationship('User')


class Agent(Base):
    __tablename__ = 'agents'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    agent_token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    hostname: Mapped[str] = mapped_column(String(255))
    public_key: Mapped[str] = mapped_column(Text)
    ip_addresses: Mapped[str | None] = mapped_column(Text, nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    network_interfaces: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class AgentProfile(Base):
    __tablename__ = 'agent_profiles'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey('agents.id'), unique=True, index=True)
    custom_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent: Mapped[Agent] = relationship('Agent')


class AgentEvent(Base):
    __tablename__ = 'agent_events'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey('agents.id'), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)  # online/offline/revoked
    details: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    agent: Mapped[Agent] = relationship('Agent')


class TaskScenario(Base):
    __tablename__ = 'task_scenarios'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    task_type: Mapped[str] = mapped_column(String(64))
    command: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = 'tasks'
    __table_args__ = (UniqueConstraint('task_uid', name='uq_task_uid'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_uid: Mapped[str] = mapped_column(String(64), index=True)
    task_type: Mapped[str] = mapped_column(String(64))
    command: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.pending)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey('agents.id'), nullable=True)
    agent: Mapped[Agent | None] = relationship('Agent')


class TelegramIntegrationSettings(Base):
    __tablename__ = 'telegram_integration_settings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    bot_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    events_thread_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    events_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
