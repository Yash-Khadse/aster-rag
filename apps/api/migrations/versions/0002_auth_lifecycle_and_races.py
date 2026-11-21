"""Token versioning plus unique indexes that close upload-dedup and reindex races."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # shortcut: fails if a workspace already holds duplicate live uploads or two active jobs
    # for one document; resolve those rows manually before upgrading such a database.
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("token_version", sa.Integer, nullable=False, server_default="0"))
    for name, table, columns, where in [
        (
            "uq_documents_active_checksum",
            "documents",
            ["workspace_id", "owner_id", "checksum"],
            "status NOT IN ('deleted', 'deleting')",
        ),
        ("uq_jobs_active_document", "jobs", ["document_id"], "status IN ('queued', 'running')"),
    ]:
        op.create_index(
            name, table, columns, unique=True, sqlite_where=sa.text(where), postgresql_where=sa.text(where)
        )


def downgrade():
    op.drop_index("uq_jobs_active_document", "jobs")
    op.drop_index("uq_documents_active_checksum", "documents")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("token_version")
