import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.core.database import Base


class PublishStatus(str, enum.Enum):
    draft = "draft"
    published = "published"


class PublishRunOutcome(str, enum.Enum):
    success = "success"
    failed = "failed"
    partial = "partial"


class Show(Base):
    __tablename__ = "shows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    section = Column(String(50), nullable=True)
    categories = Column(JSON, nullable=False, default=list)
    synopsis = Column(Text, nullable=False, default="")
    status = Column(SAEnum(PublishStatus), nullable=False, default=PublishStatus.draft)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    seasons = relationship("Season", back_populates="show", cascade="all, delete-orphan")
    artworks = relationship("Artwork", back_populates="show", cascade="all, delete-orphan")


class Season(Base):
    __tablename__ = "seasons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    show_id = Column(UUID(as_uuid=True), ForeignKey("shows.id", ondelete="CASCADE"), nullable=False)
    season_number = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("show_id", "season_number", name="uq_show_season"),
    )

    show = relationship("Show", back_populates="seasons")
    episodes = relationship("Episode", back_populates="season", cascade="all, delete-orphan")


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    episode_number = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    duration_seconds = Column(Integer, nullable=True)
    language = Column(String(10), nullable=False, default="en")
    content_group = Column(String(255), nullable=False)
    synopsis = Column(Text, nullable=False, default="")
    status = Column(SAEnum(PublishStatus), nullable=False, default=PublishStatus.draft)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("season_id", "episode_number", "language", name="uq_season_episode_lang"),
        UniqueConstraint("content_group", "language", name="uq_content_group_lang"),
        Index("ix_episodes_content_group", "content_group"),
        Index("ix_episodes_status", "status"),
    )

    season = relationship("Season", back_populates="episodes")
    artworks = relationship("Artwork", back_populates="episode", cascade="all, delete-orphan")


class Artwork(Base):
    __tablename__ = "artworks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    show_id = Column(UUID(as_uuid=True), ForeignKey("shows.id", ondelete="CASCADE"), nullable=True)
    episode_id = Column(UUID(as_uuid=True), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=True)
    artwork_type = Column(String(20), nullable=False)  # poster, banner, thumbnail
    file_path = Column(String(500), nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_artworks_show", "show_id"),
        Index("ix_artworks_episode", "episode_id"),
    )

    show = relationship("Show", back_populates="artworks")
    episode = relationship("Episode", back_populates="artworks")


class PublishRun(Base):
    __tablename__ = "publish_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    published_by = Column(String(255), nullable=False)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    outcome = Column(SAEnum(PublishRunOutcome), nullable=True)
    shows_published = Column(Integer, default=0)
    episodes_published = Column(Integer, default=0)
    catalogue_path = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    is_current = Column(Boolean, default=False)
