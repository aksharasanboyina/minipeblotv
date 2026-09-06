from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---- Show ----
class ShowCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    section: Optional[str] = None
    categories: List[str] = []
    synopsis: str = ""
    status: str = "draft"

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in ("draft", "published"):
            raise ValueError("status must be 'draft' or 'published'")
        return v


class ShowUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    section: Optional[str] = None
    categories: Optional[List[str]] = None
    synopsis: Optional[str] = None
    status: Optional[str] = None


class ShowResponse(BaseModel):
    id: UUID
    title: str
    slug: str
    section: Optional[str]
    categories: List[str]
    synopsis: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- Season ----
class SeasonCreate(BaseModel):
    season_number: int = Field(..., ge=0)


class SeasonResponse(BaseModel):
    id: UUID
    show_id: UUID
    season_number: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Episode ----
class EpisodeCreate(BaseModel):
    episode_number: int = Field(..., ge=0)
    title: str = Field(..., min_length=1, max_length=255)
    duration_seconds: Optional[int] = Field(None, ge=0)
    language: str = "en"
    content_group: str = Field(..., min_length=1)
    synopsis: str = ""
    status: str = "draft"

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in ("draft", "published"):
            raise ValueError("status must be 'draft' or 'published'")
        return v


class EpisodeUpdate(BaseModel):
    episode_number: Optional[int] = Field(None, ge=0)
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    duration_seconds: Optional[int] = Field(None, ge=0)
    language: Optional[str] = None
    content_group: Optional[str] = None
    synopsis: Optional[str] = None
    status: Optional[str] = None


class EpisodeResponse(BaseModel):
    id: UUID
    season_id: UUID
    episode_number: int
    title: str
    duration_seconds: Optional[int]
    language: str
    content_group: str
    synopsis: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- Artwork ----
class ArtworkResponse(BaseModel):
    id: UUID
    show_id: Optional[UUID]
    episode_id: Optional[UUID]
    artwork_type: str
    file_path: str
    width: int
    height: int
    file_size_bytes: int
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Publish ----
class PublishRunResponse(BaseModel):
    id: UUID
    published_by: str
    started_at: datetime
    completed_at: Optional[datetime]
    outcome: Optional[str]
    shows_published: int
    episodes_published: int
    catalogue_path: Optional[str]
    error_message: Optional[str]
    is_current: bool

    class Config:
        from_attributes = True


# ---- Validation ----
class ValidationIssue(BaseModel):
    entity_type: str
    entity_id: str
    entity_name: str
    issues: List[str]


class ValidationReport(BaseModel):
    blocking: List[ValidationIssue]
    warnings: List[ValidationIssue]
    can_publish: bool


# ---- Auth ----
class TokenRequest(BaseModel):
    user_id: str
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("editor", "admin"):
            raise ValueError("role must be 'editor' or 'admin'")
        return v


class ViewerLoginRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


# ---- Catalogue ----
class CatalogueEpisode(BaseModel):
    episode_id: str
    title: str
    episode_number: int
    duration_seconds: Optional[int]
    synopsis: str
    languages: List[str]
    thumbnail_url: Optional[str] = None
    # Playable video: stream URL (viewer auth) + whether a file is available.
    video_url: Optional[str] = None
    has_video: bool = False


class CatalogueSeason(BaseModel):
    season_number: int
    episodes: List[CatalogueEpisode]


class CatalogueShow(BaseModel):
    show_id: str
    title: str
    slug: str
    section: str
    categories: List[str]
    synopsis: str
    poster_url: Optional[str] = None
    banner_url: Optional[str] = None
    seasons: List[CatalogueSeason]
    has_trailer: bool = False
    trailer_url: Optional[str] = None


class CatalogueSection(BaseModel):
    section: str
    shows: List[CatalogueShow]


class Catalogue(BaseModel):
    version: str
    generated_at: str
    sections: List[CatalogueSection]


# ---- Pagination ----
class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int
    total_pages: int
