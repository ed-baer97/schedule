"""User models for auth / multi-tenant admin."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db import Base

ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_SCHOOL_ADMIN = "school_admin"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default=ROLE_SCHOOL_ADMIN)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=_utc_now)

    school = relationship("School", back_populates="users")

    @property
    def is_platform_admin(self) -> bool:
        return self.role == ROLE_PLATFORM_ADMIN

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class InviteToken(Base):
    """Reserved table from 8auth_tenancy. Invite flow is not implemented;
    school admins are created by platform_admin via /api/admin."""

    __tablename__ = "invite_tokens"

    id = Column(Integer, primary_key=True)
    token = Column(String(64), nullable=False, unique=True)
    email = Column(String(255), nullable=False)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    role = Column(String(32), nullable=False, default=ROLE_SCHOOL_ADMIN)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utc_now)

    school = relationship("School")
