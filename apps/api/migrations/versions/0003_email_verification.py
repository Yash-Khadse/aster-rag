"""Email verification columns; existing users are marked verified so nobody is locked out."""

import time

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email_verified_at", sa.Float, nullable=True))
        batch.add_column(sa.Column("email_verification_token_hash", sa.String(64), nullable=True))
        batch.add_column(sa.Column("email_verification_expires_at", sa.Float, nullable=True))
    op.create_index("ix_users_email_verification_token_hash", "users", ["email_verification_token_hash"])
    op.execute(sa.text("UPDATE users SET email_verified_at = :now").bindparams(now=time.time()))


def downgrade():
    op.drop_index("ix_users_email_verification_token_hash", "users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("email_verification_expires_at")
        batch.drop_column("email_verification_token_hash")
        batch.drop_column("email_verified_at")
