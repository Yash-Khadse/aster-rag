import time
import uuid

from sqlalchemy import JSON, Column, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def uid():
    return str(uuid.uuid4())


class Record:
    id = Column(String(36), primary_key=True, default=uid)
    created_at = Column(Float, default=time.time, nullable=False)


class Organization(Record, Base):
    __tablename__ = "organizations"
    name = Column(String(200), nullable=False)


class Workspace(Record, Base):
    __tablename__ = "workspaces"
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)


class User(Record, Base):
    __tablename__ = "users"
    email = Column(String(320), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    password_hash = Column(Text, nullable=False)
    # Bumped on logout/password change; tokens carry the value they were issued with.
    token_version = Column(Integer, default=0, server_default="0", nullable=False)
    email_verified_at = Column(Float, nullable=True)
    # sha256 of the emailed token; the token itself is never stored.
    email_verification_token_hash = Column(String(64), nullable=True, index=True)
    email_verification_expires_at = Column(Float, nullable=True)


class Membership(Record, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id"),)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="viewer")


class Group(Record, Base):
    __tablename__ = "groups"
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    members = Column(JSON, default=list, nullable=False)


class Collection(Record, Base):
    __tablename__ = "collections"
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)


ACTIVE_DOCUMENT = "status NOT IN ('deleted', 'deleting')"
ACTIVE_JOB = "status IN ('queued', 'running')"


class Document(Record, Base):
    __tablename__ = "documents"
    __table_args__ = (
        # Closes the upload dedup check-then-insert race.
        Index(
            "uq_documents_active_checksum",
            "workspace_id",
            "owner_id",
            "checksum",
            unique=True,
            sqlite_where=text(ACTIVE_DOCUMENT),
            postgresql_where=text(ACTIVE_DOCUMENT),
        ),
    )
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    collection_id = Column(String(36), ForeignKey("collections.id"), nullable=True)
    title = Column(String(255), nullable=False)
    checksum = Column(String(64), nullable=False, index=True)
    storage_key = Column(String(255), nullable=False)
    size = Column(Integer, nullable=False)
    access_scope = Column(String(20), default="workspace", nullable=False)
    allowed_groups = Column(JSON, default=list, nullable=False)
    allowed_users = Column(JSON, default=list, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    status = Column(String(20), default="queued", nullable=False)
    error = Column(Text, nullable=True)


class Chunk(Record, Base):
    __tablename__ = "chunks"
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    payload = Column(JSON, nullable=False)


class Job(Record, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        # One active job per document closes the reindex/retry check-then-insert race.
        Index(
            "uq_jobs_active_document",
            "document_id",
            unique=True,
            sqlite_where=text(ACTIVE_JOB),
            postgresql_where=text(ACTIVE_JOB),
        ),
    )
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    kind = Column(String(20), default="ingest", nullable=False)
    status = Column(String(20), default="queued", nullable=False, index=True)
    lease_until = Column(Float, default=0, nullable=False)
    lease_token = Column(String(36), nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    error = Column(Text, nullable=True)


class Conversation(Record, Base):
    __tablename__ = "conversations"
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    title = Column(String(200), default="New conversation", nullable=False)


class Message(Record, Base):
    __tablename__ = "messages"
    conversation_id = Column(String(36), ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    citations = Column(JSON, default=list, nullable=False)
    metrics = Column(JSON, default=dict, nullable=False)


class Usage(Record, Base):
    __tablename__ = "usage"
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(30), default="reserved", nullable=False)
    latency_ms = Column(Float, default=0, nullable=False)
    metrics = Column(JSON, default=dict, nullable=False)


class Feedback(Record, Base):
    __tablename__ = "feedback"
    message_id = Column(String(36), ForeignKey("messages.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, default="", nullable=False)


class Audit(Record, Base):
    __tablename__ = "audit"
    workspace_id = Column(String(36), index=True)
    user_id = Column(String(36))
    action = Column(String(100), nullable=False)
    target_id = Column(String(36))


class Evaluation(Record, Base):
    __tablename__ = "evaluations"
    workspace_id = Column(String(36), ForeignKey("workspaces.id"), nullable=False, index=True)
    status = Column(String(30), nullable=False)
    result = Column(JSON, default=dict, nullable=False)
