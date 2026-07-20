import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"


class RecordingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    error = "error"


class FileType(str, enum.Enum):
    audio = "audio"
    text = "text"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(128), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.manager)
    is_approved = Column(Boolean, nullable=False, default=False)
    # Токен для автозагрузки записей с ПК менеджера (MicroSIP watcher)
    ingest_token = Column(String(64), unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    recordings = relationship("Recording", back_populates="owner", cascade="all, delete-orphan")


class Recording(Base):
    __tablename__ = "recordings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(512), nullable=False)
    stored_path = Column(String(1024), nullable=False)
    file_type = Column(Enum(FileType), nullable=False)
    status = Column(Enum(RecordingStatus), default=RecordingStatus.pending)
    transcript = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    # upload = ручная загрузка в браузере; microsip = авто из папки MicroSIP
    source = Column(String(32), nullable=False, default="upload")
    # Время звонка (из имени файла MicroSIP или mtime файла)
    recorded_at = Column(DateTime, nullable=True)
    phone = Column(String(64), nullable=True)
    # sha256 содержимого — чтобы не дублировать одну и ту же запись
    content_hash = Column(String(64), nullable=True, index=True)

    owner = relationship("User", back_populates="recordings")
    analysis = relationship("Analysis", back_populates="recording", uselist=False, cascade="all, delete-orphan")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    recording_id = Column(Integer, ForeignKey("recordings.id"), unique=True, nullable=False)
    errors_json = Column(Text, nullable=False)
    recommendations_json = Column(Text, nullable=False)
    scores_json = Column(Text, nullable=False)
    total_score = Column(Float, nullable=False)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    recording = relationship("Recording", back_populates="analysis")
