"""routes.py — FastAPI endpoints for persistent multi-user chats and message history."""

from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.auth.routes import get_current_user
from backend.db.models import Chat, Message, User
from backend.db.session import get_db

router = APIRouter(prefix="/chats", tags=["Chats"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateChatRequest(BaseModel):
    title: Optional[str] = "New Chat"
    chat_type: Optional[str] = "general"


class UpdateChatRequest(BaseModel):
    title: Optional[str] = None
    chat_type: Optional[str] = None


class MessageResponse(BaseModel):
    id: str
    chat_id: str
    role: str
    content: str
    meta: Dict[str, Any]
    created_at: str

    class Config:
        from_attributes = True


class ChatResponse(BaseModel):
    id: str
    user_id: str
    title: str
    chat_type: str
    created_at: str
    updated_at: str
    message_count: Optional[int] = 0

    class Config:
        from_attributes = True


class CreateMessageRequest(BaseModel):
    role: str
    content: str
    meta: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
def create_chat(
    req: CreateChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Creates a new chat session for the authenticated user."""
    chat = Chat(
        user_id=current_user.id,
        title=req.title or "New Chat",
        chat_type=req.chat_type or "general",
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)

    return ChatResponse(
        id=str(chat.id),
        user_id=str(chat.user_id),
        title=chat.title,
        chat_type=chat.chat_type,
        created_at=chat.created_at.isoformat(),
        updated_at=chat.updated_at.isoformat(),
        message_count=0,
    )


@router.get("", response_model=List[ChatResponse])
def list_chats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lists all chats for the current user, ordered by most recently updated first."""
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == current_user.id)
        .order_by(Chat.updated_at.desc())
        .all()
    )

    result = []
    for c in chats:
        result.append(
            ChatResponse(
                id=str(c.id),
                user_id=str(c.user_id),
                title=c.title,
                chat_type=c.chat_type,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat(),
                message_count=len(c.messages),
            )
        )
    return result


@router.get("/{chat_id}", response_model=ChatResponse)
def get_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves metadata for a specific chat belonging to the current user."""
    try:
        c_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat UUID.")

    chat = db.query(Chat).filter(Chat.id == c_uuid, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    return ChatResponse(
        id=str(chat.id),
        user_id=str(chat.user_id),
        title=chat.title,
        chat_type=chat.chat_type,
        created_at=chat.created_at.isoformat(),
        updated_at=chat.updated_at.isoformat(),
        message_count=len(chat.messages),
    )


@router.patch("/{chat_id}", response_model=ChatResponse)
def update_chat(
    chat_id: str,
    req: UpdateChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates the title or type of a chat."""
    try:
        c_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat UUID.")

    chat = db.query(Chat).filter(Chat.id == c_uuid, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    if req.title is not None:
        chat.title = req.title.strip()
    if req.chat_type is not None:
        chat.chat_type = req.chat_type.strip()

    db.commit()
    db.refresh(chat)

    return ChatResponse(
        id=str(chat.id),
        user_id=str(chat.user_id),
        title=chat.title,
        chat_type=chat.chat_type,
        created_at=chat.created_at.isoformat(),
        updated_at=chat.updated_at.isoformat(),
        message_count=len(chat.messages),
    )


@router.delete("/{chat_id}")
def delete_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deletes a chat and all its associated messages."""
    try:
        c_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat UUID.")

    chat = db.query(Chat).filter(Chat.id == c_uuid, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    db.delete(chat)
    db.commit()
    return {"message": "Chat deleted successfully", "id": chat_id}


@router.get("/{chat_id}/messages", response_model=List[MessageResponse])
def get_chat_messages(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the message history for a specific chat."""
    try:
        c_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat UUID.")

    chat = db.query(Chat).filter(Chat.id == c_uuid, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    messages = (
        db.query(Message)
        .filter(Message.chat_id == c_uuid)
        .order_by(Message.created_at.asc())
        .all()
    )

    return [
        MessageResponse(
            id=str(m.id),
            chat_id=str(m.chat_id),
            role=m.role,
            content=m.content,
            meta=m.meta or {},
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.post("/{chat_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
def add_chat_message(
    chat_id: str,
    req: CreateMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Appends a new message row (user or assistant) to a chat."""
    try:
        c_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat UUID.")

    chat = db.query(Chat).filter(Chat.id == c_uuid, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found.")

    msg = Message(
        id=uuid.uuid4(),
        chat_id=c_uuid,
        role=req.role.strip().lower(),
        content=req.content,
        meta=req.meta or {},
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return MessageResponse(
        id=str(msg.id),
        chat_id=str(msg.chat_id),
        role=msg.role,
        content=msg.content,
        meta=msg.meta or {},
        created_at=msg.created_at.isoformat(),
    )
