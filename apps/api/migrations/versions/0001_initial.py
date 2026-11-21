"""Initial schema, frozen: later model changes need their own migration."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABLES = [
    "organizations",
    "workspaces",
    "users",
    "memberships",
    "groups",
    "collections",
    "documents",
    "chunks",
    "jobs",
    "conversations",
    "messages",
    "usage",
    "feedback",
    "audit",
    "evaluations",
]


def record():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.Float, nullable=False),
    ]


def fk(column, target):
    return sa.Column(column, sa.String(36), sa.ForeignKey(target), nullable=False)


def upgrade():
    op.create_table("organizations", *record(), sa.Column("name", sa.String(200), nullable=False))
    op.create_table(
        "workspaces",
        *record(),
        fk("organization_id", "organizations.id"),
        sa.Column("name", sa.String(200), nullable=False),
    )
    op.create_table(
        "users",
        *record(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "memberships",
        *record(),
        fk("user_id", "users.id"),
        fk("workspace_id", "workspaces.id"),
        sa.Column("role", sa.String(20), nullable=False),
        sa.UniqueConstraint("user_id", "workspace_id"),
    )
    op.create_table(
        "groups",
        *record(),
        fk("workspace_id", "workspaces.id"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("members", sa.JSON, nullable=False),
    )
    op.create_table(
        "collections",
        *record(),
        fk("workspace_id", "workspaces.id"),
        sa.Column("name", sa.String(200), nullable=False),
    )
    op.create_table(
        "documents",
        *record(),
        fk("workspace_id", "workspaces.id"),
        fk("owner_id", "users.id"),
        sa.Column("collection_id", sa.String(36), sa.ForeignKey("collections.id")),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("access_scope", sa.String(20), nullable=False),
        sa.Column("allowed_groups", sa.JSON, nullable=False),
        sa.Column("allowed_users", sa.JSON, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text),
    )
    op.create_table(
        "chunks",
        *record(),
        fk("document_id", "documents.id"),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
    )
    op.create_table(
        "jobs",
        *record(),
        fk("document_id", "documents.id"),
        fk("workspace_id", "workspaces.id"),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("lease_until", sa.Float, nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("error", sa.Text),
    )
    op.create_table(
        "conversations",
        *record(),
        fk("user_id", "users.id"),
        fk("workspace_id", "workspaces.id"),
        sa.Column("title", sa.String(200), nullable=False),
    )
    op.create_table(
        "messages",
        *record(),
        fk("conversation_id", "conversations.id"),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("citations", sa.JSON, nullable=False),
        sa.Column("metrics", sa.JSON, nullable=False),
    )
    op.create_table(
        "usage",
        *record(),
        fk("workspace_id", "workspaces.id"),
        fk("user_id", "users.id"),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("latency_ms", sa.Float, nullable=False),
        sa.Column("metrics", sa.JSON, nullable=False),
    )
    op.create_table(
        "feedback",
        *record(),
        fk("message_id", "messages.id"),
        fk("user_id", "users.id"),
        sa.Column("rating", sa.Integer, nullable=False),
        sa.Column("comment", sa.Text, nullable=False),
    )
    op.create_table(
        "audit",
        *record(),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("user_id", sa.String(36)),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_id", sa.String(36)),
    )
    op.create_table(
        "evaluations",
        *record(),
        fk("workspace_id", "workspaces.id"),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
    )
    for table, column in [
        ("workspaces", "organization_id"),
        ("memberships", "user_id"),
        ("memberships", "workspace_id"),
        ("groups", "workspace_id"),
        ("collections", "workspace_id"),
        ("documents", "workspace_id"),
        ("documents", "checksum"),
        ("chunks", "document_id"),
        ("jobs", "document_id"),
        ("jobs", "workspace_id"),
        ("jobs", "status"),
        ("conversations", "user_id"),
        ("conversations", "workspace_id"),
        ("messages", "conversation_id"),
        ("usage", "workspace_id"),
        ("usage", "user_id"),
        ("audit", "workspace_id"),
        ("evaluations", "workspace_id"),
    ]:
        op.create_index(f"ix_{table}_{column}", table, [column])
    if op.get_bind().dialect.name == "postgresql":
        # Browser Supabase roles receive no policies. All access is mediated by
        # the API's membership/ACL checks using a server-only database account.
        for table in TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade():
    for table in reversed(TABLES):
        op.drop_table(table)
