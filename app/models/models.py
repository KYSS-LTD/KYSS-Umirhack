import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TaskStatus(str, enum.Enum):
    pending = 'pending'
    assigned = 'assigned'
    running = 'running'
    done = 'done'
    failed = 'failed'


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Agent(Base):
    __tablename__ = 'agents'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    agent_uid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hostname: Mapped[str] = mapped_column(String(255))
    public_key: Mapped[str] = mapped_column(Text)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Task(Base):
    __tablename__ = 'tasks'
    __table_args__ = (UniqueConstraint('task_uid', name='uq_task_uid'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_uid: Mapped[str] = mapped_column(String(64), index=True)
    task_type: Mapped[str] = mapped_column(String(64))
    command: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.pending)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey('agents.id'), nullable=True)
    agent: Mapped[Agent | None] = relationship('Agent')
