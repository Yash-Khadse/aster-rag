import hashlib
import hmac
import json
import logging
import secrets
import smtplib
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Literal

import jwt
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from sqlalchemy import and_, create_engine, event, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .jobs import namespace, run_one
from .models import (
    Audit,
    Base,
    Chunk,
    Collection,
    Conversation,
    Document,
    Evaluation,
    Feedback,
    Group,
    Job,
    Membership,
    Message,
    Organization,
    Usage,
    User,
    Workspace,
)
from .storage import Storage, validate_upload

log = logging.getLogger(__name__)
passwords = PasswordHash.recommended()
# Verified against when the account is unknown/disabled so login timing does not reveal accounts.
DUMMY_HASH = passwords.hash("not-a-real-password")
bearer = HTTPBearer(auto_error=False)
SESSION_COOKIE = "atlas_session"
VERIFY_TTL_SECONDS = 24 * 3600


def send_mail(settings, to, subject, body):
    """Module-level so tests can replace it; blocking SMTP is fine in a threadpool endpoint."""
    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


class Register(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12, max_length=256)
    name: str = Field(min_length=1, max_length=200)
    organization_name: str = Field(default="My organization", min_length=1, max_length=200)


class Login(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=256)


class VerifyEmail(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class Resend(BaseModel):
    email: str = Field(max_length=320)


class ChangePassword(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class Search(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    strategy: Literal["dense", "bm25", "hybrid"] = "hybrid"
    top_k: int = Field(default=5, ge=1, le=20)
    rerank: bool = False


class Chat(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    strategy: Literal["dense", "bm25", "hybrid"] = "hybrid"
    top_k: int = Field(default=5, ge=1, le=20)
    rerank: bool = False


class Named(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ACL(BaseModel):
    access_scope: Literal["workspace", "private", "restricted"]
    allowed_users: list[str] = Field(default_factory=list, max_length=100)
    allowed_groups: list[str] = Field(default_factory=list, max_length=100)
    collection_id: str | None = None


class MemberInput(BaseModel):
    email: str
    role: Literal["admin", "knowledge_manager", "member", "viewer", "editor"] = "viewer"


class GroupInput(Named):
    members: list[str] = Field(default_factory=list, max_length=100)


class FeedbackInput(BaseModel):
    message_id: str
    rating: Literal[-1, 1]
    comment: str = Field(default="", max_length=2000)


def serialize(row):
    return {
        c.name: getattr(row, c.name)
        for c in row.__table__.columns
        if c.name not in {"password_hash", "storage_key", "lease_token", "email_verification_token_hash"}
    }


def create_app(settings=None, pipeline=None):
    from dotenv import load_dotenv

    load_dotenv(override=False)
    settings = settings or Settings()
    settings.validate_runtime()
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
        pool_pre_ping=True,
    )
    if settings.database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def sqlite_pragmas(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=10000")

    sessions = sessionmaker(engine, expire_on_commit=False)
    storage = Storage(settings)
    if pipeline is None:
        from services.rag import pipeline

    @asynccontextmanager
    async def lifespan(app):
        if settings.environment != "hosted":
            Base.metadata.create_all(engine)
        yield

    app = FastAPI(title="Enterprise RAG", version="0.1.0", lifespan=lifespan)
    app.state.sessions = sessions
    app.state.settings = settings
    app.state.storage = storage
    app.state.pipeline = pipeline
    # shortcut: per-process fixed window, so N replicas allow N x the limit and a restart resets it;
    # put a shared (edge/Redis) limiter in front before scaling out.
    from collections import OrderedDict
    from threading import Lock

    auth_attempts = OrderedDict()
    auth_lock = Lock()
    upload_slack = 64 * 1024  # multipart framing overhead on top of the file cap

    def client_ip(request):
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
        if settings.trust_proxy and forwarded:  # last hop is the one our trusted proxy appended
            return forwarded
        return request.client.host if request.client else "unknown"

    @app.middleware("http")
    async def request_id(request, call_next):
        rejected = None
        if request.url.path.startswith("/api/v1/auth/") and request.method == "POST":
            key = client_ip(request)
            now = time.monotonic()
            with auth_lock:
                attempts = [stamp for stamp in auth_attempts.get(key, []) if now - stamp < 60]
                if len(attempts) >= 20:
                    rejected = JSONResponse(
                        {"detail": "Authentication rate limit exceeded"},
                        status_code=429,
                        headers={"Retry-After": "60"},
                    )
                else:
                    auth_attempts[key] = [*attempts, now]
                    auth_attempts.move_to_end(key)
                    if len(auth_attempts) > 10000:
                        auth_attempts.popitem(last=False)
        elif request.url.path == "/api/v1/documents" and request.method == "POST":
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > settings.max_upload_bytes + upload_slack:
                rejected = JSONResponse({"detail": "Upload exceeds size limit"}, status_code=413)
        response = rejected or await call_next(request)
        response.headers["X-Request-ID"] = str(uuid.uuid4())
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    # Added last so it is outermost: early rejections above still receive CORS headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Workspace-ID", "X-CSRF-Token"],
    )

    def db_session():
        with sessions() as db:
            yield db

    def csrf_for(jwt_string):
        return hmac.new(settings.jwt_secret.encode(), jwt_string.encode(), "sha256").hexdigest()

    def cookie_attrs():
        hosted = settings.environment == "hosted"  # cross-site frontend needs SameSite=None; Secure
        return {"httponly": True, "secure": hosted, "samesite": "none" if hosted else "lax", "path": "/"}

    def actor(
        request: Request,
        credentials: HTTPAuthorizationCredentials = Depends(bearer),
        x_workspace_id: str | None = Header(default=None),
        x_csrf_token: str | None = Header(default=None),
        db=Depends(db_session),
    ):
        via_cookie = credentials is None
        raw = request.cookies.get(SESSION_COOKIE, "") if via_cookie else credentials.credentials
        try:
            token = jwt.decode(
                raw,
                settings.jwt_secret,
                algorithms=["HS256"],
                options={"require": ["exp", "sub"]},
            )
            user = db.get(User, token["sub"])
            membership = (
                db.query(Membership)
                .filter_by(user_id=token["sub"], workspace_id=x_workspace_id or token["wid"])
                .first()
            )
            if not user or not membership or token.get("tv", 0) != user.token_version:
                raise ValueError("No membership or revoked token")
            ws = db.get(Workspace, membership.workspace_id)
        except (jwt.PyJWTError, ValueError, KeyError):
            raise HTTPException(401, "Authentication required") from None
        csrf = csrf_for(raw)
        # Cookies ride along on cross-site requests, so cookie-only auth needs the CSRF header.
        if via_cookie and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not hmac.compare_digest((x_csrf_token or "").encode(), csrf.encode()):
                raise HTTPException(403, "CSRF token missing or invalid")
        return {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": membership.role,
            "organization_id": ws.organization_id,
            "workspace_id": ws.id,
            **({"csrf_token": csrf} if via_cookie else {}),
        }

    def require(user, roles=("admin",)):
        normalized = {"owner": "admin", "knowledge_manager": "editor", "member": "viewer"}.get(
            user["role"], user["role"]
        )
        if normalized not in roles:
            raise HTTPException(403, "Insufficient permissions")

    def audit(db, user, action, target=None):
        db.add(Audit(workspace_id=user["workspace_id"], user_id=user["id"], action=action, target_id=target))

    def issue(user, membership, db):
        ws = db.get(Workspace, membership.workspace_id)
        token = jwt.encode(
            {
                "sub": user.id,
                "wid": ws.id,
                "tv": user.token_version,
                "exp": int(time.time()) + settings.token_minutes * 60,
            },
            settings.jwt_secret,
            algorithm="HS256",
        )
        return {
            "access_token": token,
            "csrf_token": csrf_for(token),
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": membership.role,
                "workspace_id": ws.id,
                "organization_id": ws.organization_id,
            },
        }

    def start_session(response, result):
        response.set_cookie(
            SESSION_COOKIE, result["access_token"], max_age=settings.token_minutes * 60, **cookie_attrs()
        )
        return result

    def clear_session(response):
        response.delete_cookie(SESSION_COOKIE, **cookie_attrs())

    def send_verification(db, user):
        token = secrets.token_urlsafe(32)
        user.email_verification_token_hash = hashlib.sha256(token.encode()).hexdigest()
        user.email_verification_expires_at = time.time() + VERIFY_TTL_SECONDS
        db.commit()
        link = f"{settings.web_url.rstrip('/')}/?verify={token}"
        try:
            send_mail(
                settings,
                user.email,
                "Verify your email",
                f"Confirm your email address (link valid 24 hours):\n\n{link}\n",
            )
        except Exception:  # registration must not fail on mail; the user can request a resend
            log.exception("Verification email to user %s failed", user.id)

    def first_membership(db, user):
        return (
            db.query(Membership)
            .filter_by(user_id=user.id)
            .order_by(Membership.created_at, Membership.id)
            .first()
        )

    def can_read(doc, user, db):
        if doc.workspace_id != user["workspace_id"] or doc.status in {"deleted", "deleting"}:
            return False
        if (
            user["role"] in {"owner", "admin"}
            or doc.owner_id == user["id"]
            or doc.access_scope == "workspace"
        ):
            return True
        if doc.access_scope == "restricted":
            if user["id"] in doc.allowed_users:
                return True
            return any(
                user["id"] in g.members
                for g in db.query(Group)
                .filter(Group.workspace_id == user["workspace_id"], Group.id.in_(doc.allowed_groups))
                .all()
            )
        return False

    def document(doc_id, user, db, write=False):
        doc = db.get(Document, doc_id)
        if not doc or not can_read(doc, user, db):
            raise HTTPException(404, "Document not found")
        if write and not (
            user["role"] in {"owner", "admin"}
            or (user["role"] in {"editor", "knowledge_manager"} and doc.owner_id == user["id"])
        ):
            raise HTTPException(403, "Document owner or admin required")
        return doc

    def conversation(cid, user, db):
        row = (
            db.query(Conversation)
            .filter_by(id=cid, user_id=user["id"], workspace_id=user["workspace_id"])
            .first()
        )
        if not row:
            raise HTTPException(404, "Conversation not found")
        return row

    def readable_document_ids(user, db):
        """ACL gate on document metadata only; no chunk text is loaded."""
        membership = (
            db.query(Membership).filter_by(user_id=user["id"], workspace_id=user["workspace_id"]).first()
        )
        if not membership:
            return []
        user = {**user, "role": membership.role}
        docs = db.query(
            Document.id,
            Document.workspace_id,
            Document.status,
            Document.owner_id,
            Document.access_scope,
            Document.allowed_users,
            Document.allowed_groups,
        ).filter(Document.workspace_id == user["workspace_id"], Document.status == "ready")
        if user["role"] not in {"owner", "admin"}:
            docs = docs.filter(
                or_(Document.owner_id == user["id"], Document.access_scope.in_(["workspace", "restricted"]))
            )
        return [d.id for d in docs if can_read(d, user, db)]

    def current_chunks(db, document_ids, *columns):
        # Only the document's current version is ever readable.
        return (
            db.query(*columns)
            .select_from(Chunk)
            .join(Document, and_(Chunk.document_id == Document.id, Chunk.version == Document.version))
            .filter(Chunk.document_id.in_(document_ids))
        )

    signature_of = Chunk.payload["index_signature"].as_string()

    def authorized_chunk_ids(user, db, chunk_ids):
        """Subset of chunk_ids the caller may currently read (ids only, no payload loaded)."""
        if not chunk_ids:
            return set()
        rows = current_chunks(db, readable_document_ids(user, db), Chunk.id).filter(
            Chunk.id.in_(chunk_ids), signature_of == pipeline.index_signature()
        )
        return {row[0] for row in rows}

    def authorized_chunks(user, db):
        """Return ({id-only chunks}, stale count, retrieve() loaders).

        Chunk text is never bulk-loaded: `fetch` loads full payloads for the final candidate ids and `scan`
        streams (id, text) in batches for BM25. Both re-apply the same ACL/version/signature filters.
        """
        signature = pipeline.index_signature()
        allowed = readable_document_ids(user, db)
        limit = settings.max_retrieval_chunks
        rows = (
            current_chunks(db, allowed, Chunk.id)
            .filter(signature_of == signature)
            .order_by(Chunk.id)
            .limit(limit + 1)
            .all()
        )

        def fetch(ids):
            return [
                r[0]
                for r in current_chunks(db, allowed, Chunk.payload).filter(
                    Chunk.id.in_(ids), signature_of == signature
                )
            ]

        def scan():
            query = current_chunks(db, allowed, Chunk.id, Chunk.payload["text"].as_string())
            return query.filter(signature_of == signature).order_by(Chunk.id).limit(limit).yield_per(500)

        if len(rows) > limit:
            log.warning("Workspace %s exceeds %d chunks; retrieval is truncated", user["workspace_id"], limit)
            rows = rows[:limit]
        stale = (
            current_chunks(db, allowed, func.count(Chunk.id))
            .filter(or_(signature_of.is_(None), signature_of != signature))
            .scalar()
        )
        if stale:
            log.warning(
                "Workspace %s: %d chunks excluded (index signature differs from %s); reindex documents",
                user["workspace_id"],
                stale,
                signature,
            )
        return [{"id": row[0]} for row in rows], stale, {"fetch": fetch, "scan": scan}

    def sources_still_allowed(ids, user, db):
        db.expire_all()
        return ids <= authorized_chunk_ids(user, db, ids)

    def reserve(user, db):
        # Serialize budget checks per workspace across API processes.
        db.query(Workspace).filter_by(id=user["workspace_id"]).update({Workspace.name: Workspace.name})
        now = time.time()
        month = (
            datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
        )
        if (
            db.query(Usage)
            .filter(
                Usage.workspace_id == user["workspace_id"],
                Usage.created_at >= month,
                Usage.status != "failed",  # provider failures do not consume the monthly budget
            )
            .count()
            >= settings.monthly_query_limit
        ):
            raise HTTPException(429, "Monthly query budget exhausted")
        if (
            db.query(Usage).filter(Usage.user_id == user["id"], Usage.created_at > now - 60).count()
            >= settings.requests_per_minute
        ):
            raise HTTPException(429, "Query rate limit exceeded")
        if (
            db.query(Usage)
            .filter(Usage.user_id == user["id"], Usage.status == "reserved", Usage.created_at > now - 180)
            .count()
            >= 2
        ):
            raise HTTPException(429, "Too many concurrent requests")
        usage = Usage(workspace_id=user["workspace_id"], user_id=user["id"])
        db.add(usage)
        db.commit()
        return usage

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "mode": settings.environment, "inference": "configured; not probed"}

    @app.post("/api/v1/auth/register")
    def register(body: Register, response: Response, db=Depends(db_session)):
        if not settings.registration_enabled:
            raise HTTPException(403, "Registration disabled")
        if db.query(User).filter_by(email=body.email.lower()).first():
            raise HTTPException(409, "Account already exists")
        user = User(
            email=body.email.lower(),
            name=body.name,
            password_hash=passwords.hash(body.password),
            email_verified_at=None if settings.require_email_verification else time.time(),
        )
        org = Organization(name=body.organization_name)
        db.add_all([user, org])
        db.flush()
        ws = Workspace(name="Knowledge workspace", organization_id=org.id)
        db.add(ws)
        db.flush()
        membership = Membership(user_id=user.id, workspace_id=ws.id, role="owner")
        db.add(membership)
        try:
            db.commit()
        except IntegrityError:  # concurrent registration won the unique email
            db.rollback()
            raise HTTPException(409, "Account already exists") from None
        if settings.require_email_verification:
            send_verification(db, user)
            response.status_code = 202
            return {"verification_required": True}
        return start_session(response, issue(user, membership, db))

    @app.post("/api/v1/auth/verify-email")
    def verify_email(body: VerifyEmail, response: Response, db=Depends(db_session)):
        user = (
            db.query(User)
            .filter_by(email_verification_token_hash=hashlib.sha256(body.token.encode()).hexdigest())
            .first()
        )
        membership = first_membership(db, user) if user else None
        if not user or not membership or (user.email_verification_expires_at or 0) < time.time():
            raise HTTPException(400, "Invalid or expired verification link")
        user.email_verified_at = time.time()
        user.email_verification_token_hash = None
        user.email_verification_expires_at = None
        db.commit()
        return start_session(response, issue(user, membership, db))

    @app.post("/api/v1/auth/resend-verification", status_code=202)
    def resend_verification(body: Resend, db=Depends(db_session)):
        user = db.query(User).filter_by(email=body.email.lower()).first()
        if user and not user.email_verified_at and user.password_hash != "disabled":
            send_verification(db, user)
        return {"status": "accepted"}

    @app.post("/api/v1/auth/login")
    def login(body: Login, response: Response, db=Depends(db_session)):
        user = db.query(User).filter_by(email=body.email.lower()).first()
        usable = user is not None and user.password_hash != "disabled"
        verified = passwords.verify(body.password, user.password_hash if usable else DUMMY_HASH)
        if not (usable and verified):
            raise HTTPException(401, "Invalid email or password")
        if settings.require_email_verification and not user.email_verified_at:
            raise HTTPException(403, "email_not_verified")
        membership = first_membership(db, user)
        if not membership:
            raise HTTPException(403, "No workspace membership")
        return start_session(response, issue(user, membership, db))

    @app.post("/api/v1/auth/demo")
    def demo(response: Response, db=Depends(db_session)):
        ws = db.get(Workspace, settings.demo_workspace_id)
        if not settings.demo_enabled or not ws:
            raise HTTPException(503, "Demo workspace is not configured")
        recent = (
            db.query(Membership)
            .filter(
                Membership.workspace_id == ws.id,
                Membership.role == "demo",
                Membership.created_at > time.time() - 3600,
            )
            .count()
        )
        if recent >= settings.demo_accounts_per_hour:
            raise HTTPException(429, "Demo capacity reached; try again later")
        user = User(
            email=f"demo-{uuid.uuid4()}@example.invalid",
            name="Demo visitor",
            password_hash="disabled",
            email_verified_at=time.time(),
        )
        db.add(user)
        db.flush()
        membership = Membership(user_id=user.id, workspace_id=ws.id, role="demo")
        db.add(membership)
        db.commit()
        return start_session(response, issue(user, membership, db))

    @app.get("/api/v1/auth/me")
    def me(user=Depends(actor)):
        return user

    @app.post("/api/v1/auth/logout")
    def logout(response: Response, user=Depends(actor), db=Depends(db_session)):
        # Invalidates every token issued to this user (bearer tokens are otherwise stateless).
        db.get(User, user["id"]).token_version += 1
        audit(db, user, "auth.logout", user["id"])
        db.commit()
        clear_session(response)
        return {"status": "logged_out"}

    @app.post("/api/v1/auth/change-password")
    def change_password(
        body: ChangePassword, response: Response, user=Depends(actor), db=Depends(db_session)
    ):
        row = db.get(User, user["id"])
        if row.password_hash == "disabled":
            raise HTTPException(403, "This account has no password")
        if not passwords.verify(body.current_password, row.password_hash):
            raise HTTPException(401, "Current password is incorrect")
        row.password_hash = passwords.hash(body.new_password)
        row.token_version += 1
        audit(db, user, "auth.change_password", row.id)
        db.commit()
        membership = db.query(Membership).filter_by(user_id=row.id, workspace_id=user["workspace_id"]).first()
        clear_session(response)  # the old cookie is revoked; the body carries a fresh bearer token
        return issue(row, membership, db)

    @app.get("/api/v1/organizations")
    def organizations(user=Depends(actor), db=Depends(db_session)):
        return [serialize(db.get(Organization, user["organization_id"]))]

    @app.get("/api/v1/workspaces")
    def workspaces(user=Depends(actor), db=Depends(db_session)):
        return [
            serialize(w)
            for w in db.query(Workspace).join(Membership).filter(Membership.user_id == user["id"]).all()
        ]

    @app.get("/api/v1/documents")
    def documents(
        user=Depends(actor), db=Depends(db_session), offset: int = 0, limit: int = 100, q: str = ""
    ):
        query = db.query(Document).filter_by(workspace_id=user["workspace_id"])
        term = q.strip()[:255]
        if term:
            query = query.filter(func.lower(Document.title).contains(term.lower(), autoescape=True))
        rows = query.order_by(Document.created_at.desc(), Document.id.desc()).all()
        start = max(offset, 0)
        page = [doc for doc in rows if can_read(doc, user, db)][start : start + min(max(limit, 1), 100)]
        ready_ids = [doc.id for doc in page if doc.status == "ready"]
        counts = (
            dict(
                db.query(Chunk.document_id, func.count(Chunk.id))
                .join(Document, (Chunk.document_id == Document.id) & (Chunk.version == Document.version))
                .filter(Chunk.document_id.in_(ready_ids))
                .group_by(Chunk.document_id)
                .all()
            )
            if ready_ids
            else {}
        )
        return [{**serialize(doc), "chunk_count": counts.get(doc.id, 0)} for doc in page]

    # Plain `def`: FastAPI runs it in the threadpool, so blocking storage/DB work stays off the event loop.
    @app.post("/api/v1/documents", status_code=201)
    def upload(
        file: UploadFile = File(...),
        access_scope: str = Form("workspace"),
        user=Depends(actor),
        db=Depends(db_session),
    ):
        require(user, ("admin", "editor"))
        if access_scope not in {"workspace", "private", "restricted"}:
            raise HTTPException(422, "Invalid access scope")
        # shortcut: Starlette has already spooled the multipart body to disk by now (the middleware
        # rejects oversized Content-Length earlier); chunked uploads without a length are still spooled.
        buffer = bytearray()
        while block := file.file.read(64 * 1024):
            buffer += block
            if len(buffer) > settings.max_upload_bytes:
                raise HTTPException(413, "Upload exceeds size limit")
        data = bytes(buffer)
        filename = Path((file.filename or "document.txt").replace("\\", "/")).name[:255]
        try:
            validate_upload(data, filename)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        checksum = hashlib.sha256(data).hexdigest()

        def existing():
            return (
                db.query(Document)
                .filter_by(workspace_id=user["workspace_id"], owner_id=user["id"], checksum=checksum)
                .filter(Document.status.notin_(["deleted", "deleting"]))
                .first()
            )

        def reuse(duplicate):
            if duplicate.access_scope != access_scope or (
                access_scope == "restricted" and (duplicate.allowed_users or duplicate.allowed_groups)
            ):
                raise HTTPException(
                    409,
                    "This content already exists with different access. Edit the existing document's access to change it.",
                )
            return serialize(duplicate)

        if duplicate := existing():
            return reuse(duplicate)
        used_documents, used_bytes = (
            db.query(func.count(Document.id), func.coalesce(func.sum(Document.size), 0))
            .filter(
                Document.workspace_id == user["workspace_id"], Document.status.notin_(["deleted", "deleting"])
            )
            .one()
        )
        if (
            used_documents >= settings.max_workspace_documents
            or used_bytes + len(data) > settings.max_workspace_bytes
        ):
            raise HTTPException(403, "Workspace document or storage quota exceeded")
        did = str(uuid.uuid4())
        key = f"{user['workspace_id']}/{did}{Path(filename).suffix.lower()}"
        storage.put(key, data)
        doc = Document(
            id=did,
            workspace_id=user["workspace_id"],
            owner_id=user["id"],
            title=filename,
            checksum=checksum,
            storage_key=key,
            size=len(data),
            access_scope=access_scope,
        )
        try:
            db.add(doc)
            db.flush()
            db.add(Job(document_id=did, workspace_id=doc.workspace_id, version=1))
            audit(db, user, "document.upload", did)
            db.commit()
        except Exception as exc:
            db.rollback()
            storage.delete(key)
            if isinstance(exc, IntegrityError) and (duplicate := existing()):  # lost the dedup race
                return reuse(duplicate)
            raise
        return serialize(doc)

    @app.get("/api/v1/documents/{doc_id}")
    def get_document(doc_id: str, user=Depends(actor), db=Depends(db_session)):
        return serialize(document(doc_id, user, db))

    @app.get("/api/v1/documents/{doc_id}/source")
    def source(doc_id: str, user=Depends(actor), db=Depends(db_session)):
        doc = document(doc_id, user, db)
        return Response(
            storage.get(doc.storage_key),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="source{Path(doc.title).suffix}"',
                "Content-Security-Policy": "sandbox",
            },
        )

    @app.get("/api/v1/documents/{doc_id}/permission-options")
    def permission_options(doc_id: str, user=Depends(actor), db=Depends(db_session)):
        doc = document(doc_id, user, db, True)
        members = (
            db.query(User.id, User.name)
            .join(Membership, Membership.user_id == User.id)
            .filter(Membership.workspace_id == doc.workspace_id)
            .order_by(User.name, User.id)
        )
        return {
            "members": [{"id": member.id, "name": member.name} for member in members],
            "groups": [
                {"id": group.id, "name": group.name}
                for group in db.query(Group)
                .filter_by(workspace_id=doc.workspace_id)
                .order_by(Group.name, Group.id)
            ],
            "collections": [
                {"id": collection.id, "name": collection.name}
                for collection in db.query(Collection)
                .filter_by(workspace_id=doc.workspace_id)
                .order_by(Collection.name, Collection.id)
            ],
        }

    @app.patch("/api/v1/documents/{doc_id}/permissions")
    def permissions(doc_id: str, body: ACL, user=Depends(actor), db=Depends(db_session)):
        doc = document(doc_id, user, db, True)
        member_ids = {m.user_id for m in db.query(Membership).filter_by(workspace_id=user["workspace_id"])}
        group_ids = {g.id for g in db.query(Group).filter_by(workspace_id=user["workspace_id"])}
        if not set(body.allowed_users) <= member_ids or not set(body.allowed_groups) <= group_ids:
            raise HTTPException(422, "Permissions must reference workspace members and groups")
        if (
            body.collection_id
            and not db.query(Collection)
            .filter_by(id=body.collection_id, workspace_id=user["workspace_id"])
            .first()
        ):
            raise HTTPException(422, "Collection not found")
        for key, value in body.model_dump().items():
            setattr(doc, key, value)
        audit(db, user, "document.permissions", doc.id)
        db.commit()
        return serialize(doc)

    @app.post("/api/v1/documents/{doc_id}/reindex")
    def reindex(doc_id: str, user=Depends(actor), db=Depends(db_session)):
        doc = document(doc_id, user, db, True)
        if db.query(Job).filter_by(document_id=doc.id).filter(Job.status.in_(["queued", "running"])).first():
            raise HTTPException(409, "Document already has an active job")
        doc.version += 1
        doc.status = "queued"
        doc.error = None
        job = Job(document_id=doc.id, workspace_id=doc.workspace_id, version=doc.version)
        db.add(job)
        audit(db, user, "document.reindex", doc.id)
        try:
            db.commit()
        except IntegrityError:  # unique active-job index: a concurrent request queued one first
            db.rollback()
            raise HTTPException(409, "Document already has an active job") from None
        return serialize(job)

    @app.delete("/api/v1/documents/{doc_id}")
    def delete_document(doc_id: str, user=Depends(actor), db=Depends(db_session)):
        doc = document(doc_id, user, db, True)
        # Fence any in-flight ingest before making document invisible immediately.
        doc.status = "deleting"
        doc.version += 1
        db.query(Job).filter_by(document_id=doc.id).filter(Job.status.in_(["queued", "running"])).update(
            {"status": "cancelled"}
        )
        db.add(Job(document_id=doc.id, workspace_id=doc.workspace_id, version=doc.version, kind="delete"))
        audit(db, user, "document.delete", doc.id)
        db.commit()
        return {"status": "deleting"}

    @app.get("/api/v1/ingestion-jobs")
    def jobs(user=Depends(actor), db=Depends(db_session)):
        require(user, ("admin", "editor"))
        query = db.query(Job).filter_by(workspace_id=user["workspace_id"])
        if user["role"] not in {"owner", "admin"}:
            query = query.join(Document).filter(Document.owner_id == user["id"])
        return [serialize(j) for j in query.order_by(Job.created_at.desc()).limit(100)]

    @app.post("/api/v1/ingestion-jobs/run")
    def run_jobs(user=Depends(actor)):
        require(user)
        return {"job_id": run_one(sessions, storage, pipeline, settings.lease_seconds, user["workspace_id"])}

    @app.post("/api/v1/ingestion-jobs/{job_id}/retry")
    def retry_job(job_id: str, user=Depends(actor), db=Depends(db_session)):
        require(user)
        job = db.query(Job).filter_by(id=job_id, workspace_id=user["workspace_id"], status="failed").first()
        if not job:
            raise HTTPException(404, "Failed job not found")
        doc = db.get(Document, job.document_id)
        if doc.version != job.version:
            raise HTTPException(409, "Job version has been superseded")
        job.status = "queued"
        job.error = None
        if job.kind != "delete":
            doc.status = "queued"
            doc.error = None
        try:
            db.commit()
        except IntegrityError:  # the document already has another active job
            db.rollback()
            raise HTTPException(409, "Document already has an active job") from None
        return serialize(job)

    @app.get("/api/v1/collections")
    def collections(user=Depends(actor), db=Depends(db_session)):
        return [serialize(c) for c in db.query(Collection).filter_by(workspace_id=user["workspace_id"])]

    @app.post("/api/v1/collections")
    def add_collection(body: Named, user=Depends(actor), db=Depends(db_session)):
        require(user, ("admin", "editor"))
        row = Collection(name=body.name, workspace_id=user["workspace_id"])
        db.add(row)
        db.commit()
        return serialize(row)

    @app.post("/api/v1/groups")
    def add_group(body: GroupInput, user=Depends(actor), db=Depends(db_session)):
        require(user)
        valid = {m.user_id for m in db.query(Membership).filter_by(workspace_id=user["workspace_id"])}
        if not set(body.members) <= valid:
            raise HTTPException(422, "Group members must belong to workspace")
        group = Group(workspace_id=user["workspace_id"], **body.model_dump())
        db.add(group)
        db.commit()
        return serialize(group)

    @app.post("/api/v1/admin/members")
    def add_member(body: MemberInput, user=Depends(actor), db=Depends(db_session)):
        require(user)
        target = db.query(User).filter_by(email=body.email.lower()).first()
        if not target:
            raise HTTPException(404, "User must register first")
        if not target.email_verified_at:
            raise HTTPException(409, "User has not verified their email")
        member = db.query(Membership).filter_by(user_id=target.id, workspace_id=user["workspace_id"]).first()
        if member and target.id == user["id"]:
            raise HTTPException(409, "Cannot change own admin membership")
        if member and member.role == "owner" and user["role"] != "owner":
            raise HTTPException(403, "Only an organization owner can change another owner's role")
        if not member:
            member = Membership(user_id=target.id, workspace_id=user["workspace_id"])
            db.add(member)
        member.role = body.role
        audit(db, user, "membership.update", target.id)
        db.commit()
        return serialize(member)

    @app.delete("/api/v1/admin/members/{user_id}")
    def remove_member(user_id: str, user=Depends(actor), db=Depends(db_session)):
        require(user)
        # Serialize admin-count checks per workspace (same no-op write as reserve()).
        db.query(Workspace).filter_by(id=user["workspace_id"]).update({Workspace.name: Workspace.name})
        member = db.query(Membership).filter_by(user_id=user_id, workspace_id=user["workspace_id"]).first()
        if not member:
            raise HTTPException(404, "Member not found")
        if member.role == "owner" and user["role"] != "owner":
            raise HTTPException(403, "Only an organization owner can remove another owner")
        admins = (
            db.query(Membership)
            .filter(Membership.workspace_id == user["workspace_id"], Membership.role.in_(["owner", "admin"]))
            .count()
        )
        if member.role in {"owner", "admin"} and admins <= 1:
            raise HTTPException(409, "Cannot remove the last admin")
        # The actor() membership check rejects this user's existing tokens for this workspace at once;
        # token_version is not bumped so their sessions in other workspaces survive.
        db.delete(member)
        audit(db, user, "membership.remove", user_id)
        db.commit()
        return {"status": "removed"}

    def fail_usage(usage_id, start, db):
        db.rollback()
        db.execute(
            update(Usage)
            .where(Usage.id == usage_id)
            .values(status="failed", latency_ms=(time.perf_counter() - start) * 1000)
        )
        db.commit()

    def search_impl(body, user, db):
        usage = reserve(user, db)
        usage_id = usage.id
        start = time.perf_counter()
        try:
            chunks, stale, loaders = authorized_chunks(user, db)
            result = pipeline.retrieve(
                body.query,
                chunks,
                namespace(db, user["workspace_id"]),
                strategy=body.strategy,
                top_k=body.top_k,
                rerank=body.rerank,
                **loaders,
            )
            result_ids = {
                chunk["id"] for field in ("evidence", "candidates") for chunk in result.get(field, [])
            }
            if not result_ids <= {chunk["id"] for chunk in chunks}:
                raise ValueError("Retriever returned an unauthorized chunk")
            if not sources_still_allowed(result_ids, user, db):
                raise HTTPException(409, "Source access changed during retrieval. Run the search again.")
            usage.status = "completed"
            usage.metrics = {
                "strategy": body.strategy,
                "timings": result.get("timings", {}),
                "reranker_status": result.get("reranker_status"),
                "reranker_reason": result.get("reranker_reason"),
                "reranker_fallback": bool(result.get("reranker_fallback")),
                "stale_index_chunks": stale,
            }
            usage.latency_ms = (time.perf_counter() - start) * 1000
            db.commit()
            return {**result, "stale_index_chunks": stale}
        except HTTPException:
            fail_usage(usage_id, start, db)
            raise
        except Exception:
            fail_usage(usage_id, start, db)
            raise HTTPException(503, "Retrieval provider unavailable; no result was fabricated") from None

    @app.post("/api/v1/search")
    def search(body: Search, user=Depends(actor), db=Depends(db_session)):
        return search_impl(body, user, db)

    @app.post("/api/v1/search/debug")
    def search_debug(body: Search, user=Depends(actor), db=Depends(db_session)):
        require(user, ("admin", "editor"))
        return search_impl(body, user, db)

    @app.get("/api/v1/chat/sessions")
    def chats(user=Depends(actor), db=Depends(db_session)):
        return [
            serialize(c)
            for c in db.query(Conversation)
            .filter_by(user_id=user["id"], workspace_id=user["workspace_id"])
            .order_by(Conversation.created_at.desc())
            .limit(100)
        ]

    @app.post("/api/v1/chat/sessions")
    def new_chat(user=Depends(actor), db=Depends(db_session)):
        row = Conversation(user_id=user["id"], workspace_id=user["workspace_id"])
        db.add(row)
        db.commit()
        return serialize(row)

    @app.get("/api/v1/chat/sessions/{cid}")
    def get_chat(cid: str, user=Depends(actor), db=Depends(db_session)):
        row = conversation(cid, user, db)
        rows = db.query(Message).filter_by(conversation_id=cid).order_by(Message.created_at).all()
        cited = {c.get("id", c.get("chunk_id")) for msg in rows for c in msg.citations} - {None}
        allowed_ids = authorized_chunk_ids(user, db, cited)
        ratings: dict[str, int] = {}
        for vote in (
            db.query(Feedback)
            .join(Message, Message.id == Feedback.message_id)
            .filter(Message.conversation_id == cid, Feedback.user_id == user["id"])
            .order_by(Feedback.created_at.desc(), Feedback.id.desc())
        ):
            ratings.setdefault(vote.message_id, vote.rating)
        messages = []
        for msg in rows:
            value = serialize(msg)
            value["feedback_rating"] = ratings.get(msg.id)
            if any(c.get("id", c.get("chunk_id")) not in allowed_ids for c in msg.citations):
                value["content"] = "This answer references sources no longer available to you."
                value["citations"] = []
            messages.append(value)
        return {**serialize(row), "messages": messages}

    @app.delete("/api/v1/chat/sessions/{cid}")
    def delete_chat(cid: str, user=Depends(actor), db=Depends(db_session)):
        row = conversation(cid, user, db)
        lock_conversation(cid, user, db)
        mids = [m.id for m in db.query(Message).filter_by(conversation_id=cid)]
        db.query(Feedback).filter(Feedback.message_id.in_(mids)).delete(synchronize_session=False)
        db.query(Message).filter_by(conversation_id=cid).delete()
        db.delete(row)
        db.commit()
        return {"status": "deleted"}

    def chat_impl(body, user, db):
        conv = conversation(body.session_id, user, db) if body.session_id else None
        usage = reserve(user, db)
        usage_id = usage.id
        start = time.perf_counter()
        try:
            chunks, stale, loaders = authorized_chunks(user, db)
            allowed = {c["id"] for c in chunks}
            # Prior prompts resolve follow-ups. Previously generated text can carry stale source material.
            history = []
            if conv is not None:
                history = [
                    {"role": message.role, "content": message.content}
                    for message in db.query(Message)
                    .filter_by(conversation_id=conv.id, role="user")
                    .order_by(Message.created_at.desc())
                    .limit(6)
                    .all()[::-1]
                ]
            rewritten = pipeline.contextual_query(body.question, history)
            retrieval = pipeline.retrieve(
                rewritten,
                chunks,
                namespace(db, user["workspace_id"]),
                strategy=body.strategy,
                top_k=body.top_k,
                rerank=body.rerank,
                **loaders,
            )
            evidence = [c for c in retrieval["evidence"] if c["id"] in allowed]
            evidence_ids = {c["id"] for c in evidence}
            # Recheck SQL after potentially slow external retrieval and again before
            # releasing an answer, so concurrent revocations cannot expose citations.
            if not sources_still_allowed(evidence_ids, user, db):
                raise ValueError("Source permissions changed during retrieval")
            result = pipeline.generate_answer(body.question, evidence, history=history)
            if not sources_still_allowed(evidence_ids, user, db):
                raise ValueError("Source permissions changed during generation")
            if any(c.get("id", c.get("chunk_id")) not in evidence_ids for c in result.get("citations", [])):
                raise ValueError("Provider returned unauthorized citation")
            metrics = {
                "latency_ms": (time.perf_counter() - start) * 1000,
                "retrieval": retrieval.get("timings", {}),
                "usage": result.get("usage", {}),
                "provider": result.get("provider"),
                "model": result.get("model"),
                "strategy": body.strategy,
                "query_rewritten": rewritten != body.question,
                "reranker_status": retrieval.get("reranker_status"),
                "reranker_reason": retrieval.get("reranker_reason"),
                "reranker_fallback": bool(retrieval.get("reranker_fallback")),
                "stale_index_chunks": stale,
            }
            if conv is None:
                conv = Conversation(
                    user_id=user["id"], workspace_id=user["workspace_id"], title=body.question[:100]
                )
                db.add(conv)
                db.flush()
            else:
                lock_conversation(body.session_id, user, db)
            db.add(Message(conversation_id=conv.id, role="user", content=body.question))
            msg = Message(
                conversation_id=conv.id,
                role="assistant",
                content=result["answer"],
                citations=result.get("citations", []),
                metrics=metrics,
            )
            db.add(msg)
            usage.status = result.get("status", "completed")
            usage.metrics = metrics
            usage.latency_ms = (time.perf_counter() - start) * 1000
            db.flush()
            response = {**result, "session_id": conv.id, "message_id": msg.id, "metrics": metrics}
            db.commit()
            return response
        except HTTPException:
            fail_usage(usage_id, start, db)
            raise
        except Exception:
            fail_usage(usage_id, start, db)
            raise HTTPException(
                503, "Model or retrieval provider unavailable; retry when configured and within quota"
            ) from None

    @app.post("/api/v1/chat")
    def chat(body: Chat, user=Depends(actor), db=Depends(db_session)):
        return chat_impl(body, user, db)

    @app.post("/api/v1/chat/stream")
    def stream(body: Chat, user=Depends(actor), db=Depends(db_session)):
        if body.session_id:
            conversation(body.session_id, user, db)

        def run():
            with sessions() as stream_db:
                return chat_impl(body, user, stream_db)

        def events():
            yield 'event: status\ndata: {"stage":"retrieving"}\n\n'
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(run)
            try:
                # Comment lines keep proxies from timing out an idle stream during slow generation.
                while not wait([future], timeout=settings.sse_heartbeat_seconds).done:
                    yield ": keep-alive\n\n"
                yield f"event: result\ndata: {json.dumps(future.result())}\n\n"
            except HTTPException as exc:
                yield f"event: error\ndata: {json.dumps({'detail': exc.detail})}\n\n"
            except Exception:
                log.exception("Chat stream failed")
                yield f"event: error\ndata: {json.dumps({'detail': 'Chat failed; retry later'})}\n\n"
            finally:
                pool.shutdown(wait=False)
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    def lock_conversation(cid, user, db):
        # Serialize feedback writes and conversation deletion without requiring a schema change.
        changed = db.execute(
            update(Conversation)
            .where(
                Conversation.id == cid,
                Conversation.user_id == user["id"],
                Conversation.workspace_id == user["workspace_id"],
            )
            .values(title=Conversation.title)
        )
        if not changed.rowcount:
            raise HTTPException(404, "Conversation not found")

    @app.post("/api/v1/feedback")
    def feedback(body: FeedbackInput, user=Depends(actor), db=Depends(db_session)):
        msg = db.get(Message, body.message_id)
        if not msg or msg.role != "assistant":
            raise HTTPException(404, "Message not found")
        lock_conversation(msg.conversation_id, user, db)
        votes = (
            db.query(Feedback)
            .filter_by(user_id=user["id"], message_id=msg.id)
            .order_by(Feedback.created_at.desc(), Feedback.id.desc())
            .all()
        )
        if votes:
            row, *duplicates = votes
            row.rating = body.rating
            row.comment = body.comment
            for duplicate in duplicates:
                db.delete(duplicate)
        else:
            row = Feedback(user_id=user["id"], **body.model_dump())
            db.add(row)
        db.commit()
        return serialize(row)

    @app.get("/api/v1/settings")
    def settings_route(user=Depends(actor)):
        import os

        return {
            "llm_provider": os.getenv("LLM_PROVIDER", "ollama"),
            "llm_model": os.getenv("LLM_MODEL", ""),
            "embedding_model": os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
            "vector_backend": settings.vector_backend,
            "retrieval_strategy": "hybrid",
            "top_k": 5,
            "reranking": False,
            "monthly_query_limit": settings.monthly_query_limit,
            "max_upload_bytes": settings.max_upload_bytes,
            "role": user["role"],
        }

    @app.get("/api/v1/analytics")
    def analytics(user=Depends(actor), db=Depends(db_session)):
        require(user)
        base = db.query(Usage).filter_by(workspace_id=user["workspace_id"])
        by_status = dict(
            db.query(Usage.status, func.count(Usage.id))
            .filter_by(workspace_id=user["workspace_id"])
            .group_by(Usage.status)
            .all()
        )
        total = sum(by_status.values())

        def latency_at(index):
            row = (
                db.query(Usage.latency_ms)
                .filter(Usage.workspace_id == user["workspace_id"])
                .order_by(Usage.latency_ms)
                .offset(index)
                .limit(1)
                .first()
            )
            return row[0] if row else None

        def count(*statuses):
            return sum(by_status.get(status, 0) for status in statuses)

        return {
            "queries": total,
            "successful_answers": count("completed", "answered", "ok"),
            "failed_requests": count("failed"),
            "abstentions": count("abstained", "insufficient_evidence"),
            "latency_p50_ms": latency_at(total // 2) if total else None,
            "latency_p95_ms": latency_at(min(total - 1, int(total * 0.95))) if total else None,
            "usage": [
                serialize(r) for r in base.order_by(Usage.created_at.desc(), Usage.id.desc()).limit(100)
            ],
        }

    @app.get("/api/v1/admin")
    def admin(user=Depends(actor), db=Depends(db_session)):
        require(user)
        members = db.query(Membership).filter_by(workspace_id=user["workspace_id"]).all()
        return {
            "members": [
                {**serialize(m), "email": db.get(User, m.user_id).email, "name": db.get(User, m.user_id).name}
                for m in members
            ],
            "groups": [serialize(g) for g in db.query(Group).filter_by(workspace_id=user["workspace_id"])],
            "audit_events": [
                serialize(a)
                for a in db.query(Audit)
                .filter_by(workspace_id=user["workspace_id"])
                .order_by(Audit.created_at.desc())
                .limit(50)
            ],
        }

    @app.get("/api/v1/evaluations")
    def evaluations(user=Depends(actor), db=Depends(db_session)):
        return [
            serialize(r)
            for r in db.query(Evaluation)
            .filter_by(workspace_id=user["workspace_id"])
            .order_by(Evaluation.created_at.desc())
        ]

    return app


app = create_app()
