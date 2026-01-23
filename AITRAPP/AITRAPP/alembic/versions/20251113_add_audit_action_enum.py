"""Add AuditActionEnum to AuditLog (with backfill + index)

Revision ID: 20251113_add_audit_action_enum
Revises: 
Create Date: 2025-11-13

"""
revision = '20251113_add_audit_action_enum'
down_revision = None
branch_labels = None
depends_on = None
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Keep the enum name EXACTLY as in models.py to avoid type drift
AUDIT_ENUM_NAME = "auditactionenum"

# List must match your models.AuditActionEnum values 1:1
audit_enum = postgresql.ENUM(
    "KILL_SWITCH",
    "CONFIG_FROZEN",
    "MODE_CHANGE",
    "PAUSE",
    "RESUME",
    "FLATTEN",
    "RISK_BLOCK",
    "ORDER_PLACED",
    "ORDER_FILLED",
    "ORDER_CANCELLED",
    "POSITION_OPENED",
    "POSITION_CLOSED",
    name=AUDIT_ENUM_NAME,
    create_type=True,
)


def upgrade():
    # 1) Create the PostgreSQL enum type
    audit_enum.create(op.get_bind(), checkfirst=True)

    # 2) Add the column as nullable (no default for enum)
    op.add_column(
        "audit_logs",
        sa.Column("action", audit_enum, nullable=True),
    )

    # 3) Optional: add an index for faster querying by action
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade():
    # 1) Drop index
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")

    # 2) Drop column
    op.drop_column("audit_logs", "action")

    # 3) Drop enum type (must be last)
    audit_enum.drop(op.get_bind(), checkfirst=True)
