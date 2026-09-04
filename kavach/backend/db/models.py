"""models.py — SQLAlchemy database models for KAVACH persistence (users, chats, messages).

Note: Message.meta is explicitly named 'meta' (type JSONB) to avoid collisions with
SQLAlchemy's internal Base.metadata.
"""

import uuid
from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from backend.db.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan")


class Chat(Base):
    __tablename__ = "chats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    title = Column(String(255), default="New Chat", nullable=False)
    chat_type = Column(String(50), default="general", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id", ondelete="CASCADE"), index=True, nullable=False)
    role = Column(String(50), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    meta = Column(JSONB, default=dict, server_default='{}', nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    chat = relationship("Chat", back_populates="messages")
