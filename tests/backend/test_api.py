import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rag_api import jobs
from rag_api.config import Settings
from rag_api.main import create_app
from rag_api.models import (
    Chunk,
    Conversation,
    Document,
    Feedback,
    Job,
    Message,
    Organization,
    Usage,
    Workspace,
)
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def service(tmp_path):
    seen = []

    def retrieve(query, chunks, namespace, **kwargs):
        seen.append(chunks)
        # Like the real retriever: chunks are ids only; text is loaded for the final candidates.
        loaded = kwargs["fetch"]([c["id"] for c in chunks[:5]])
        return {"evidence": loaded, "candidates": loaded, "timings": {}, "query": query}

    pipeline = SimpleNamespace(
        index_signature=lambda: "test-index",
        contextual_query=lambda question, history: question,
        parse_document=lambda data, filename: [{"text": data.decode(), "page": 1}],
        chunk_pages=lambda pages: pages,
        embed_texts=lambda texts: [[1.0, 0.0] for _ in texts],
        index_chunks=lambda *args: None,
        delete_vectors=lambda *args, **kwargs: None,
        retrieve=retrieve,
        generate_answer=lambda question, evidence, history=None: {
            "answer": "Supported answer" if evidence else "No evidence",
            "citations": evidence,
            "status": "answered" if evidence else "abstained",
        },
    )
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}", data_dir=str(tmp_path), jwt_secret="x" * 48
    )
    app = create_app(settings, pipeline)
    with TestClient(app) as client:
        yield client, app, seen


def register(client, name):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"{name}@example.com", "password": "correct-horse-battery", "name": name},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    return {"Authorization": f"Bearer {result['access_token']}"}, result["user"]


def upload(client, headers, scope="workspace", content=b"The policy is 20 days leave."):
    result = client.post(
        "/api/v1/documents",
        headers=headers,
        data={"access_scope": scope},
        files={"file": ("policy.txt", content)},
    )
    assert result.status_code == 201, result.text
    return result.json()


def test_tenant_isolation_and_current_chunks(service):
    client, app, seen = service
    alice, a = register(client, "alice")
    bob, b = register(client, "bob")
    doc = upload(client, alice)
    assert client.post("/api/v1/ingestion-jobs/run", headers=alice).status_code == 200
    assert client.get(f"/api/v1/documents/{doc['id']}/source", headers=bob).status_code == 404
    assert client.get("/api/v1/documents", headers=bob).json() == []
    assert client.post("/api/v1/search", headers=bob, json={"query": "policy"}).json()["evidence"] == []
    response = client.post("/api/v1/chat", headers=alice, json={"question": "policy?"})
    assert response.status_code == 200, response.text
    cid = response.json()["session_id"]
    assert client.get(f"/api/v1/chat/sessions/{cid}", headers=bob).status_code == 404
    assert (
        client.post("/api/v1/chat", headers=bob, json={"question": "policy", "session_id": cid}).status_code
        == 404
    )
    client.post(f"/api/v1/documents/{doc['id']}/reindex", headers=alice)
    assert client.post("/api/v1/search", headers=alice, json={"query": "policy"}).json()["evidence"] == []
    assert client.get(f"/api/v1/chat/sessions/{cid}", headers=alice).json()["messages"][-1]["citations"] == []


def test_document_search_filters_before_pagination_and_counts_ready_chunks(service):
    client, _, _ = service
    owner, _ = register(client, "library-owner")
    first = upload(client, owner)
    assert client.post("/api/v1/ingestion-jobs/run", headers=owner).status_code == 200
    second = client.post(
        "/api/v1/documents", headers=owner, files={"file": ("benefits.txt", b"Benefits guide")}
    )
    assert second.status_code == 201
    listing = client.get("/api/v1/documents", headers=owner, params={"q": "POLICY", "limit": 1})
    assert listing.status_code == 200
    assert [(doc["id"], doc["chunk_count"]) for doc in listing.json()] == [(first["id"], 1)]
    for params in ({"q": "%"}, {"q": "policy", "offset": 1}):
        assert client.get("/api/v1/documents", headers=owner, params=params).json() == []


def test_private_acl_roles_groups_and_revocation(service):
    client, app, seen = service
    admin, a = register(client, "admin")
    member, m = register(client, "member")
    client.post("/api/v1/admin/members", headers=admin, json={"email": m["email"], "role": "viewer"})
    member["X-Workspace-ID"] = a["workspace_id"]
    doc = upload(client, admin, "private")
    client.post("/api/v1/ingestion-jobs/run", headers=admin)
    assert client.get("/api/v1/documents", headers=member).json() == []
    assert (
        client.post("/api/v1/documents", headers=member, files={"file": ("x.txt", b"x")}).status_code == 403
    )
    group = client.post("/api/v1/groups", headers=admin, json={"name": "team", "members": [m["id"]]}).json()
    response = client.patch(
        f"/api/v1/documents/{doc['id']}/permissions",
        headers=admin,
        json={"access_scope": "restricted", "allowed_groups": [group["id"]]},
    )
    assert response.status_code == 200
    options_path = f"/api/v1/documents/{doc['id']}/permission-options"
    options = client.get(options_path, headers=admin).json()
    assert {entry["id"] for entry in options["members"]} == {a["id"], m["id"]}
    assert options["groups"] == [{"id": group["id"], "name": "team"}]
    assert client.get(options_path, headers=member).status_code == 403
    assert (
        len(client.post("/api/v1/search", headers=member, json={"query": "policy"}).json()["evidence"]) == 1
    )
    client.patch(
        f"/api/v1/documents/{doc['id']}/permissions", headers=admin, json={"access_scope": "private"}
    )
    assert client.post("/api/v1/search", headers=member, json={"query": "policy"}).json()["evidence"] == []


def test_feedback_replaces_vote_and_reloads_in_owned_history(service):
    client, app, _ = service
    owner, _ = register(client, "feedback-owner")
    outsider, _ = register(client, "feedback-outsider")
    chat = client.post("/api/v1/chat", headers=owner, json={"question": "What is the policy?"})
    assert chat.status_code == 200, chat.text
    result = chat.json()
    history_path = f"/api/v1/chat/sessions/{result['session_id']}"
    payload = {"message_id": result["message_id"], "rating": 1}
    assert client.post("/api/v1/feedback", headers=outsider, json=payload).status_code == 404
    first = client.post("/api/v1/feedback", headers=owner, json=payload)
    changed = client.post("/api/v1/feedback", headers=owner, json={**payload, "rating": -1})
    assert first.status_code == changed.status_code == 200
    assert first.json()["id"] == changed.json()["id"]
    history = client.get(history_path, headers=owner).json()["messages"]
    assert history[-1]["feedback_rating"] == -1
    assert (
        client.post(
            "/api/v1/feedback", headers=owner, json={**payload, "message_id": history[0]["id"]}
        ).status_code
        == 404
    )
    with app.state.sessions() as db:
        assert db.query(Feedback).filter_by(message_id=result["message_id"]).count() == 1
    assert client.delete(history_path, headers=owner).status_code == 200


def test_jobs_retry_delete_and_duplicate(service):
    client, app, _ = service
    admin, _ = register(client, "admin")
    doc = upload(client, admin)
    assert upload(client, admin)["id"] == doc["id"]
    app.state.pipeline.index_chunks = lambda *args: (_ for _ in ()).throw(RuntimeError("network"))
    client.post("/api/v1/ingestion-jobs/run", headers=admin)
    failed = client.get("/api/v1/ingestion-jobs", headers=admin).json()[0]
    assert failed["status"] == "failed"
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=admin).json()["status"] == "failed"
    app.state.pipeline.index_chunks = lambda *args: None
    assert client.post(f"/api/v1/ingestion-jobs/{failed['id']}/retry", headers=admin).status_code == 200
    client.post("/api/v1/ingestion-jobs/run", headers=admin)
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=admin).json()["status"] == "ready"
    client.delete(f"/api/v1/documents/{doc['id']}", headers=admin)
    assert client.get(f"/api/v1/documents/{doc['id']}/source", headers=admin).status_code == 404
    client.post("/api/v1/ingestion-jobs/run", headers=admin)
    with app.state.sessions() as db:
        assert db.query(Chunk).count() == 0
        assert db.get(Document, doc["id"]).status == "deleted"


def test_expired_worker_cannot_publish_manifest_or_fail_reclaimable_job(service, monkeypatch):
    client, app, _ = service
    owner, _ = register(client, "lease-owner")
    doc = upload(client, owner)
    clock = SimpleNamespace(now=1000.0)
    monkeypatch.setattr(jobs, "time", SimpleNamespace(time=lambda: clock.now))

    def slow_chunking(pages):
        clock.now += 901
        return pages

    monkeypatch.setattr(app.state.pipeline, "chunk_pages", slow_chunking)
    assert client.post("/api/v1/ingestion-jobs/run", headers=owner).status_code == 200
    with app.state.sessions() as db:
        assert db.query(Chunk).filter_by(document_id=doc["id"]).count() == 0
        assert db.query(Job).filter_by(document_id=doc["id"]).one().status == "running"
        assert db.get(Document, doc["id"]).status == "chunking"

    monkeypatch.setattr(app.state.pipeline, "chunk_pages", lambda pages: pages)
    assert client.post("/api/v1/ingestion-jobs/run", headers=owner).status_code == 200
    with app.state.sessions() as db:
        assert db.get(Document, doc["id"]).status == "ready"
        assert db.query(Job).filter_by(document_id=doc["id"]).one().attempts == 2


def test_upload_validation_and_budget(service):
    client, app, _ = service
    admin, _ = register(client, "admin")
    assert (
        client.post("/api/v1/documents", headers=admin, files={"file": ("fake.pdf", b"hello")}).status_code
        == 422
    )
    assert (
        client.post("/api/v1/documents", headers=admin, files={"file": ("bad.txt", b"MZevil")}).status_code
        == 422
    )
    app.state.settings.monthly_query_limit = 1
    assert client.post("/api/v1/search", headers=admin, json={"query": "hello"}).status_code == 200
    assert client.post("/api/v1/search", headers=admin, json={"query": "hello"}).status_code == 429


def test_sse_errors_are_honest_and_persist_usage(service):
    client, app, _ = service
    admin, _ = register(client, "admin")
    app.state.pipeline.generate_answer = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("quota"))
    response = client.post("/api/v1/chat/stream", headers=admin, json={"question": "hello"})
    assert "event: error" in response.text and "event: done" in response.text
    with app.state.sessions() as db:
        assert db.query(Conversation).count() == 0
        assert db.query(Message).count() == 0
        assert db.query(Usage).first().status == "failed"


def test_hosted_requires_persistence(tmp_path):
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(environment="hosted", data_dir=str(tmp_path)).validate_runtime()


def test_authentication_rate_limit(service):
    client, _, _ = service
    for _ in range(20):
        assert client.post("/api/v1/auth/demo").status_code == 503
    assert client.post("/api/v1/auth/demo").status_code == 429


def test_admin_cannot_demote_owner(service):
    client, _, _ = service
    owner, principal = register(client, "owner")
    admin, other = register(client, "admin")
    assert (
        client.post(
            "/api/v1/admin/members", headers=owner, json={"email": other["email"], "role": "admin"}
        ).status_code
        == 200
    )
    admin["X-Workspace-ID"] = principal["workspace_id"]
    assert (
        client.post(
            "/api/v1/admin/members", headers=admin, json={"email": principal["email"], "role": "viewer"}
        ).status_code
        == 403
    )


def test_revoked_source_is_not_returned_after_generation(service):
    client, app, _ = service
    owner, principal = register(client, "owner")
    member, other = register(client, "member")
    client.post("/api/v1/admin/members", headers=owner, json={"email": other["email"], "role": "viewer"})
    member["X-Workspace-ID"] = principal["workspace_id"]
    doc = upload(client, owner)
    client.post("/api/v1/ingestion-jobs/run", headers=owner)

    def revoke(question, evidence, history=None):
        with app.state.sessions() as db:
            row = db.get(Document, doc["id"])
            row.access_scope = "private"
            db.commit()
        return {"answer": "Do not release", "citations": evidence}

    app.state.pipeline.generate_answer = revoke
    response = client.post("/api/v1/chat", headers=member, json={"question": "leave policy"})
    assert response.status_code == 503 and "Do not release" not in response.text


def test_search_does_not_release_chunks_revoked_during_retrieval(service):
    client, app, _ = service
    owner, principal = register(client, "search-owner")
    member, other = register(client, "search-viewer")
    client.post("/api/v1/admin/members", headers=owner, json={"email": other["email"], "role": "viewer"})
    member["X-Workspace-ID"] = principal["workspace_id"]
    doc = upload(client, owner)
    client.post("/api/v1/ingestion-jobs/run", headers=owner)
    retrieve = app.state.pipeline.retrieve

    def revoke(*args, **kwargs):
        result = retrieve(*args, **kwargs)
        assert result["evidence"]
        with app.state.sessions() as db:
            db.get(Document, doc["id"]).access_scope = "private"
            db.commit()
        return result

    app.state.pipeline.retrieve = revoke
    response = client.post("/api/v1/search", headers=member, json={"query": "leave"})
    assert response.status_code == 409 and doc["id"] not in response.text


def test_duplicate_upload_cannot_silently_reuse_different_visibility(service):
    client, _, _ = service
    owner, _ = register(client, "upload-owner")
    doc = upload(client, owner, content=b"Sensitive policy")
    duplicate = client.post(
        "/api/v1/documents",
        headers=owner,
        data={"access_scope": "private"},
        files={"file": ("policy.txt", b"Sensitive policy")},
    )
    assert duplicate.status_code == 409
    assert client.get(f"/api/v1/documents/{doc['id']}", headers=owner).json()["access_scope"] == "workspace"


def test_rate_limit_keys_on_forwarded_ip_only_when_trusted_and_keeps_cors_headers(service):
    client, app, _ = service
    cors = {"Origin": "http://localhost:3000"}
    for _ in range(20):
        spoofed = {**cors, "X-Forwarded-For": "9.9.9.9"}
        assert client.post("/api/v1/auth/demo", headers=spoofed).status_code == 503
    # Untrusted proxy header is ignored: every spoofed value shares the socket address bucket.
    limited = client.post("/api/v1/auth/demo", headers={**cors, "X-Forwarded-For": "8.8.8.8"})
    assert limited.status_code == 429
    assert limited.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert limited.headers["x-request-id"] and limited.headers["retry-after"] == "60"
    app.state.settings.trust_proxy = True
    assert (
        client.post("/api/v1/auth/demo", headers={"X-Forwarded-For": "spoofed, 7.7.7.7"}).status_code == 503
    )
    for _ in range(19):
        client.post("/api/v1/auth/demo", headers={"X-Forwarded-For": "7.7.7.7"})
    assert client.post("/api/v1/auth/demo", headers={"X-Forwarded-For": "other, 7.7.7.7"}).status_code == 429


def test_stale_index_chunks_are_reported_and_acl_still_applies_in_sql(service, caplog):
    client, app, _ = service
    owner, principal = register(client, "stale-owner")
    viewer, other = register(client, "stale-viewer")
    client.post("/api/v1/admin/members", headers=owner, json={"email": other["email"], "role": "viewer"})
    viewer["X-Workspace-ID"] = principal["workspace_id"]
    upload(client, owner, "private")
    upload(client, owner, "workspace", b"Public handbook")
    client.post("/api/v1/ingestion-jobs/run", headers=owner)
    client.post("/api/v1/ingestion-jobs/run", headers=owner)
    fresh = client.post("/api/v1/search", headers=owner, json={"query": "x"}).json()
    assert len(fresh["evidence"]) == 2 and fresh["stale_index_chunks"] == 0
    assert len(client.post("/api/v1/search", headers=viewer, json={"query": "x"}).json()["evidence"]) == 1
    app.state.pipeline.index_signature = lambda: "new-index"
    with caplog.at_level("WARNING"):
        stale = client.post("/api/v1/search", headers=viewer, json={"query": "x"}).json()
    assert stale["evidence"] == [] and stale["stale_index_chunks"] == 1  # private chunk stays hidden
    assert "excluded" in caplog.text
    chat = client.post("/api/v1/chat", headers=owner, json={"question": "x"}).json()
    assert chat["metrics"]["stale_index_chunks"] == 2


def test_upload_size_cap_and_workspace_quota(service):
    client, app, _ = service
    owner, _ = register(client, "quota-owner")
    app.state.settings.max_upload_bytes = 10
    big = client.post("/api/v1/documents", headers=owner, files={"file": ("a.txt", b"x" * 11)})
    assert big.status_code == 413
    huge = client.post("/api/v1/documents", headers=owner, files={"file": ("a.txt", b"x" * 200_000)})
    assert huge.status_code == 413  # rejected on Content-Length before parsing
    app.state.settings.max_workspace_documents = 1
    assert (
        client.post("/api/v1/documents", headers=owner, files={"file": ("a.txt", b"one")}).status_code == 201
    )
    assert (
        client.post("/api/v1/documents", headers=owner, files={"file": ("b.txt", b"two")}).status_code == 403
    )
    assert (
        client.post("/api/v1/documents", headers=owner, files={"file": ("a.txt", b"one")}).status_code == 201
    )


def test_unique_indexes_block_duplicate_live_documents_and_active_jobs(service):
    client, app, _ = service
    owner, _ = register(client, "race-owner")
    doc = upload(client, owner)
    with app.state.sessions() as db:
        row = db.get(Document, doc["id"])
        db.add(Job(document_id=row.id, workspace_id=row.workspace_id, version=1))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(
            Document(
                workspace_id=row.workspace_id,
                owner_id=row.owner_id,
                title="dup",
                checksum=row.checksum,
                storage_key="k",
                size=1,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
    assert client.post(f"/api/v1/documents/{doc['id']}/reindex", headers=owner).status_code == 409


def test_config_validation():
    with pytest.raises(ValidationError):
        Settings(environment="prod")
    assert Settings(cors_origins=" http://a.test , ,http://b.test,").cors_origin_list == [
        "http://a.test",
        "http://b.test",
    ]


def test_demo_accounts_are_capped(service):
    client, app, _ = service
    with app.state.sessions() as db:
        org = Organization(name="demo")
        db.add(org)
        db.flush()
        ws = Workspace(name="demo", organization_id=org.id)
        db.add(ws)
        db.commit()
        app.state.settings.demo_workspace_id = ws.id
    app.state.settings.demo_enabled = True
    app.state.settings.demo_accounts_per_hour = 2
    assert [client.post("/api/v1/auth/demo").status_code for _ in range(3)] == [200, 200, 429]


def test_logout_and_password_change_revoke_tokens(service):
    client, _, _ = service
    headers, user = register(client, "lifecycle")
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    wrong = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "nope-nope-nope", "new_password": "another-long-password"},
    )
    assert wrong.status_code == 401
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "correct-horse-battery", "new_password": "another-long-password"},
    )
    assert changed.status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    fresh = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=fresh).status_code == 200
    credentials = {"email": user["email"], "password": "another-long-password"}
    assert client.post("/api/v1/auth/login", json=credentials).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=fresh).status_code == 200
    assert client.get("/api/v1/auth/me", headers=fresh).status_code == 401
    ghost = {"email": "ghost@example.com", "password": "whatever-long-1"}
    assert client.post("/api/v1/auth/login", json=ghost).status_code == 401


def test_remove_member_revokes_access_and_protects_last_admin(service):
    client, _, _ = service
    owner, principal = register(client, "remove-owner")
    member, other = register(client, "remove-member")
    client.post("/api/v1/admin/members", headers=owner, json={"email": other["email"], "role": "viewer"})
    member["X-Workspace-ID"] = principal["workspace_id"]
    assert client.get("/api/v1/auth/me", headers=member).status_code == 200
    assert client.delete(f"/api/v1/admin/members/{other['id']}", headers=member).status_code == 403
    assert client.delete(f"/api/v1/admin/members/{other['id']}", headers=owner).status_code == 200
    assert client.get("/api/v1/auth/me", headers=member).status_code == 401
    assert client.delete(f"/api/v1/admin/members/{other['id']}", headers=owner).status_code == 404
    assert client.delete(f"/api/v1/admin/members/{principal['id']}", headers=owner).status_code == 409


def test_sse_heartbeat_and_unexpected_failures_emit_error_then_done(service):
    client, app, _ = service
    admin, _ = register(client, "sse-admin")
    app.state.settings.sse_heartbeat_seconds = 0.05

    def slow(question, evidence, history=None):
        time.sleep(0.3)
        return {"answer": "ok", "citations": [], "status": "answered"}

    app.state.pipeline.generate_answer = slow
    ok = client.post("/api/v1/chat/stream", headers=admin, json={"question": "hello"})
    assert ": keep-alive" in ok.text and "event: result" in ok.text
    assert ok.text.endswith("event: done\ndata: {}\n\n")
    app.state.pipeline.index_signature = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    failed = client.post("/api/v1/chat/stream", headers=admin, json={"question": "hello"})
    assert failed.text.index("event: error") < failed.text.index("event: done")


def test_analytics_orders_latest_first_with_sql_limit(service):
    client, app, _ = service
    admin, principal = register(client, "analytics-admin")
    with app.state.sessions() as db:
        for i in range(120):
            db.add(
                Usage(
                    workspace_id=principal["workspace_id"],
                    user_id=principal["id"],
                    status="completed",
                    latency_ms=i,
                    created_at=1000 + i,
                )
            )
        db.commit()
    body = client.get("/api/v1/analytics", headers=admin).json()
    assert body["queries"] == 120 and len(body["usage"]) == 100
    assert body["usage"][0]["created_at"] == 1119
    assert body["latency_p50_ms"] == 60 and body["latency_p95_ms"] == 114


def test_alembic_head_matches_models(tmp_path, monkeypatch):
    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from rag_api.models import Base
    from sqlalchemy import create_engine

    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(ROOT / "apps/api/alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "apps/api/migrations"))
    command.upgrade(config, "0002")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users (id, created_at, email, name, password_hash, token_version)"
            " VALUES ('u1', 1, 'old@example.com', 'Old', 'x', 0)"
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        # Pre-existing accounts are grandfathered as verified so nobody is locked out.
        assert connection.exec_driver_sql("SELECT email_verified_at FROM users").scalar() > 0
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_reranker_fallback_is_reported_in_search_chat_and_stream(service):
    client, app, _ = service
    owner, _ = register(client, "rerank-owner")
    upload(client, owner)
    client.post("/api/v1/ingestion-jobs/run", headers=owner)
    retrieve = app.state.pipeline.retrieve

    def degraded(*args, **kwargs):
        return {
            **retrieve(*args, **kwargs),
            "reranker_status": "timeout_fallback",
            "reranker_reason": "reranker exceeded 15s",
            "reranker_fallback": True,
        }

    app.state.pipeline.retrieve = degraded
    search = client.post("/api/v1/search", headers=owner, json={"query": "leave"}).json()
    assert search["reranker_fallback"] is True and search["reranker_reason"] == "reranker exceeded 15s"
    chat = client.post("/api/v1/chat", headers=owner, json={"question": "leave"}).json()
    assert (
        chat["metrics"]["reranker_fallback"] is True
        and chat["metrics"]["reranker_status"] == "timeout_fallback"
    )
    stream = client.post("/api/v1/chat/stream", headers=owner, json={"question": "leave"}).text
    assert '"reranker_fallback": true' in stream and "reranker exceeded 15s" in stream
    with app.state.sessions() as db:
        assert all(
            u.metrics["reranker_fallback"] is True for u in db.query(Usage).filter_by(status="completed")
        )
