"""Administrative local CLI; never expose service credentials to the browser."""

import argparse
import hashlib
import json
import uuid
from pathlib import Path

from .jobs import run_one
from .main import app
from .models import Base, Document, Evaluation, Job, Membership, Organization, User, Workspace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "seed-demo", "import-evaluation"])
    parser.add_argument("--workspace")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--process", action="store_true")
    args = parser.parse_args()
    sessions = app.state.sessions
    with sessions() as db:
        if args.command == "init":
            Base.metadata.create_all(db.get_bind())
            print("Local schema initialized; use Alembic migrations for hosted installations.")
            return
        if args.command == "import-evaluation":
            if not args.report or not args.workspace or not db.get(Workspace, args.workspace):
                parser.error("A report path and existing workspace ID are required")
            report = json.loads(args.report.read_text(encoding="utf-8"))
            if (
                not report.get("id")
                or report.get("status") not in {"completed", "failed"}
                or not isinstance(report.get("variants"), list)
            ):
                parser.error("Expected a benchmark report produced by services.evaluation.benchmark")
            identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, args.workspace + report["id"]))
            db.merge(
                Evaluation(id=identifier, workspace_id=args.workspace, status=report["status"], result=report)
            )
            db.commit()
            print(f"Imported evaluation {identifier}")
            return
        root = Path(__file__).resolve().parents[3]
        corpus = json.loads((root / "datasets/corpus.json").read_text(encoding="utf-8"))
        workspace_id = args.workspace or "fictional-demo-workspace"
        ws = db.get(Workspace, workspace_id)
        if not ws:
            org = Organization(id="fictional-demo-organization", name="Aster — fictional organization")
            if not db.get(Organization, org.id):
                db.add(org)
                db.flush()
            ws = Workspace(id=workspace_id, organization_id=org.id, name="Fictional demonstration")
            db.add(ws)
            db.flush()
        user = db.query(User).filter_by(email="seed-owner@example.invalid").first()
        if not user:
            user = User(
                email="seed-owner@example.invalid", name="Demo corpus owner", password_hash="disabled"
            )
            db.add(user)
            db.flush()
        if not db.query(Membership).filter_by(user_id=user.id, workspace_id=ws.id).first():
            db.add(Membership(user_id=user.id, workspace_id=ws.id, role="owner"))
            db.flush()
        for source in corpus["documents"]:
            if source.get("access_scope") != "workspace" or not source.get("current", True):
                continue
            identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, ws.id + source["id"]))
            if db.get(Document, identifier):
                continue
            data = source["text"].encode("utf-8")
            key = f"{ws.id}/{identifier}.md"
            app.state.storage.put(key, data)
            doc = Document(
                id=identifier,
                workspace_id=ws.id,
                owner_id=user.id,
                title=source["title"] + ".md",
                checksum=hashlib.sha256(data).hexdigest(),
                storage_key=key,
                size=len(data),
                access_scope="workspace",
            )
            db.add(doc)
            db.flush()
            db.add(Job(document_id=doc.id, workspace_id=ws.id, version=1))
        db.commit()
    if args.process:
        while run_one(sessions, app.state.storage, app.state.pipeline, workspace_id=workspace_id):
            pass
        with sessions() as db:
            failed = db.query(Job).filter_by(workspace_id=workspace_id, status="failed").count()
            if failed:
                raise SystemExit(f"{failed} ingestion jobs failed; inspect jobs before enabling demo")
    print(f"Demo workspace: {workspace_id}. Set DEMO_ENABLED=true and DEMO_WORKSPACE_ID={workspace_id}.")


if __name__ == "__main__":
    main()
