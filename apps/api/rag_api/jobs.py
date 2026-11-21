"""Durable, fenced ingestion. Chunk IDs are deterministic per document version.

Only one worker may own a job lease; expired workers cannot publish SQL results.
External vector upserts are idempotent, and retrieval checks SQL's current version.
"""

import time
import uuid

from sqlalchemy import or_, update

from .models import Chunk, Document, Job, Workspace

# Each lease increments attempts; a job whose lease expired this many times is abandoned.
MAX_JOB_ATTEMPTS = 5


def namespace(db, workspace_id):
    ws = db.get(Workspace, workspace_id)
    return f"{ws.organization_id}:{ws.id}"


def _fail_exhausted(db, job, now):
    # Fenced like a lease: only the expired, still-exhausted job row transitions.
    error = f"LeaseExpired: abandoned after {job.attempts} attempts; inspect worker logs"
    job_id = job.id
    changed = db.execute(
        update(Job)
        .where(
            Job.id == job.id,
            Job.status == "running",
            Job.lease_until < now,
            Job.attempts >= MAX_JOB_ATTEMPTS,
        )
        .values(status="failed", error=error)
    )
    if changed.rowcount:
        db.execute(
            update(Document)
            .where(
                Document.id == job.document_id,
                Document.version == job.version,
                Document.status.notin_(["deleting", "deleted"]),
            )
            .values(status="failed", error=error)
        )
        db.commit()
        return job_id
    return None


def run_one(session_factory, storage, pipeline, lease_seconds=900, workspace_id=None):
    with session_factory() as db:
        now = time.time()
        query = db.query(Job).filter(
            or_(Job.status == "queued", (Job.status == "running") & (Job.lease_until < now))
        )
        if workspace_id:
            query = query.filter(Job.workspace_id == workspace_id)
        candidate = query.order_by(Job.created_at).first()
        if not candidate:
            return None
        if candidate.status == "running" and candidate.attempts >= MAX_JOB_ATTEMPTS:
            return _fail_exhausted(db, candidate, now)
        token = str(uuid.uuid4())
        result = db.execute(
            update(Job)
            .where(
                Job.id == candidate.id,
                or_(Job.status == "queued", (Job.status == "running") & (Job.lease_until < now)),
            )
            .values(
                status="running",
                lease_token=token,
                lease_until=now + lease_seconds,
                attempts=Job.attempts + 1,
            )
        )
        db.commit()
        if not result.rowcount:
            return None
        job_id = candidate.id

    def owned_lease(job):
        return update(Job).where(
            Job.id == job.id,
            Job.lease_token == token,
            Job.status == "running",
            Job.lease_until > time.time(),
        )

    def state(db, job, status):
        # Match the API's document-then-job write order. Both writes roll back
        # together when the document changed or another worker owns the lease.
        allowed_status = (
            Document.status == "deleting"
            if job.kind == "delete"
            else Document.status.notin_(["deleting", "deleted"])
        )
        fields = {"status": status}
        if status in {"ready", "deleted"}:
            fields["error"] = None
        changed = db.execute(
            update(Document)
            .where(Document.id == job.document_id, Document.version == job.version, allowed_status)
            .values(**fields)
        )
        if not changed.rowcount:
            raise RuntimeError("Document version superseded")
        renewed = db.execute(owned_lease(job).values(lease_until=time.time() + lease_seconds))
        if not renewed.rowcount:
            raise RuntimeError("Worker lease lost")

    try:
        with session_factory() as db:
            job = db.get(Job, job_id)
            ns = namespace(db, job.workspace_id)
            state(db, job, "deleting" if job.kind == "delete" else "parsing")
            db.commit()
            doc = db.get(Document, job.document_id)
            old = db.query(Chunk).filter(Chunk.document_id == doc.id).all()
            if job.kind == "delete":
                for signature in {c.payload.get("index_signature") for c in old}:
                    pipeline.delete_vectors(
                        ns,
                        [c.id for c in old if c.payload.get("index_signature") == signature],
                        signature=signature,
                    )
                storage.delete(doc.storage_key)
                state(db, job, "deleted")
                db.query(Chunk).filter(Chunk.document_id == doc.id).delete()
            else:
                pages = pipeline.parse_document(storage.get(doc.storage_key), doc.title)
                state(db, job, "chunking")
                db.commit()
                pieces = pipeline.chunk_pages(pages)
                if not pieces or len(pieces) > 2000:
                    raise ValueError("No extractable content or document exceeds 2000 chunks")
                chunks = []
                for i, piece in enumerate(pieces):
                    cid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc.id}:{job.version}:{i}"))
                    chunks.append(
                        {
                            **piece,
                            "id": cid,
                            "document_id": doc.id,
                            "title": doc.title,
                            "version": job.version,
                            "index_signature": pipeline.index_signature(),
                        }
                    )
                # Fence the manifest write as well as the document status transition.
                state(db, job, "embedding")
                for chunk in chunks:
                    db.merge(Chunk(id=chunk["id"], document_id=doc.id, version=job.version, payload=chunk))
                db.commit()
                embeddings = pipeline.embed_texts([c["text"] for c in chunks])
                if len(embeddings) != len(chunks):
                    raise ValueError("Embedding provider returned an invalid batch")
                state(db, job, "indexing")
                db.commit()
                pipeline.index_chunks(
                    ns, [{**c, "embedding": e} for c, e in zip(chunks, embeddings, strict=True)]
                )
                for signature in {c.payload.get("index_signature") for c in old if c.version != job.version}:
                    stale = [
                        c.id
                        for c in old
                        if c.version != job.version and c.payload.get("index_signature") == signature
                    ]
                    pipeline.delete_vectors(ns, stale, signature=signature)
                state(db, job, "ready")
                db.query(Chunk).filter(Chunk.document_id == doc.id, Chunk.version != job.version).delete()
            job.status = "completed"
            job.error = None
            db.commit()
    except Exception as exc:
        with session_factory() as db:
            job = db.get(Job, job_id)
            error = f"{type(exc).__name__}: processing failed; inspect worker logs"
            db.execute(
                update(Document)
                .where(
                    Document.id == job.document_id,
                    Document.version == job.version,
                    Document.status.notin_(["deleted", "deleting"]),
                )
                .values(status="failed", error=error)
            )
            failed = db.execute(owned_lease(job).values(status="failed", error=error))
            if failed.rowcount:
                db.commit()
    return job_id
