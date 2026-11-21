import time
from types import SimpleNamespace

from rag_api import jobs
from rag_api.models import Base, Document, Job, Organization, User, Workspace
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(Organization(id="org", name="Org"))
        db.add(Workspace(id="ws", organization_id="org", name="Workspace"))
        db.add(User(id="user", email="u@example.invalid", name="User", password_hash="x"))
        db.add(
            Document(
                id="doc",
                workspace_id="ws",
                owner_id="user",
                title="doc.txt",
                checksum="0" * 64,
                storage_key="ws/doc.txt",
                size=1,
                version=1,
                status="chunking",
            )
        )
        db.add(
            Job(
                id="job",
                document_id="doc",
                workspace_id="ws",
                version=1,
                status="running",
                lease_until=time.time() - 10,
                lease_token="old",
                attempts=jobs.MAX_JOB_ATTEMPTS,
            )
        )
        db.commit()
    return factory


def test_job_past_max_attempts_becomes_terminal_failure(tmp_path):
    factory = _session_factory(tmp_path)
    storage = SimpleNamespace(get=lambda key: b"unused")
    pipeline = SimpleNamespace()

    assert jobs.run_one(factory, storage, pipeline) == "job"
    with factory() as db:
        job = db.get(Job, "job")
        assert job.status == "failed"
        assert job.error.startswith("LeaseExpired")
        assert job.attempts == jobs.MAX_JOB_ATTEMPTS
        document = db.get(Document, "doc")
        assert document.status == "failed"
        assert document.error == job.error

    # Terminal jobs are never re-leased.
    assert jobs.run_one(factory, storage, pipeline) is None


def test_expired_job_under_limit_is_leased_again(tmp_path):
    factory = _session_factory(tmp_path)
    with factory() as db:
        db.get(Job, "job").attempts = jobs.MAX_JOB_ATTEMPTS - 1
        db.commit()

    def unreadable(key):
        raise OSError("storage unavailable")

    storage = SimpleNamespace(get=unreadable)
    assert jobs.run_one(factory, storage, SimpleNamespace(parse_document=None)) == "job"
    with factory() as db:
        job = db.get(Job, "job")
        assert job.attempts == jobs.MAX_JOB_ATTEMPTS
        assert job.status == "failed"
        assert job.error.startswith("OSError")
