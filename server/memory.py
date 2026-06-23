import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import Session
from server.database import Base

class ChatMessage(Base):
    """Database model for storing conversation history."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), index=True, nullable=False)
    role = Column(String(50), nullable=False)  # 'user', 'model', 'system', 'tool'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def save_message(db: Session, session_id: str, role: str, content: str) -> ChatMessage:
    """Save a chat message to persistent memory."""
    db_message = ChatMessage(session_id=session_id, role=role, content=content)
    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message

def get_session_history(db: Session, session_id: str, limit: int = 10) -> list[ChatMessage]:
    """Retrieve the recent chat history for a session."""
    recent_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(recent_messages))

def clear_session_history(db: Session, session_id: str) -> None:
    """Clear chat history for a specific session."""
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.commit()
