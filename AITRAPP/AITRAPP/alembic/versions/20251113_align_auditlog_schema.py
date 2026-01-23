"""Align AuditLog schema: add details JSONB; convert action to ENUM

Revision ID: 20251113_align_auditlog_schema
Revises: 20251113_add_audit_action_enum
Create Date: 2025-11-13

"""
revision = '20251113_align_auditlog_schema'
down_revision = '20251113_add_audit_action_enum'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# ⚠️ Must exactly match your models.AuditActionEnum values
ENUM_NAME = "auditactionenum"
AUDIT_VALUES = [
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
]

audit_enum = postgresql.ENUM(*AUDIT_VALUES, name=ENUM_NAME, create_type=True)


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) Ensure enum type exists
    audit_enum.create(bind, checkfirst=True)

    # 2) Add details JSONB if missing; backfill from legacy "data" if present
    cols = {c["name"] for c in insp.get_columns("audit_logs")}
    if "details" not in cols:
        op.add_column("audit_logs", sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        if "data" in cols:
            op.execute("UPDATE audit_logs SET details = data WHERE details IS NULL AND data IS NOT NULL")

    # 3) Convert action (VARCHAR/TEXT) -> ENUM safely
    cols = {c["name"] for c in insp.get_columns("audit_logs")}
    if "action" in cols:
        # Check if action is already enum type
        action_col = next((c for c in insp.get_columns("audit_logs") if c["name"] == "action"), None)
        is_enum = action_col and "enum" in str(action_col.get("type", "")).lower()
        
        if not is_enum:
            # Create temp enum column
            op.add_column("audit_logs", sa.Column("action_enum_tmp", audit_enum, nullable=True))
            
            # Map text->enum 1:1 (assumes values already match exactly; otherwise add CASE mapping)
            cases = "\n".join([f"WHEN action = '{v}' THEN '{v}'::" + ENUM_NAME for v in AUDIT_VALUES])
            op.execute(f"""
                UPDATE audit_logs
                SET action_enum_tmp = CASE
                    {cases}
                    ELSE NULL
                END
            """)
            
            # Drop old column and rename temp
            op.drop_column("audit_logs", "action")
            op.alter_column("audit_logs", "action_enum_tmp", new_column_name="action", existing_type=audit_enum, nullable=True)
            
            # Create index if it doesn't exist
            try:
                op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
            except Exception:
                pass  # Index may already exist
        else:
            # Already enum, just ensure index exists
            try:
                op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
            except Exception:
                pass
    else:
        # No action column existed; just add fresh ENUM column (nullable initially)
        op.add_column("audit_logs", sa.Column("action", audit_enum, nullable=True))
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)

    # 4) Drop legacy "data" column if still present (after backfill) - optional, keep for now
    # cols = {c["name"] for c in insp.get_columns("audit_logs")}
    # if "data" in cols:
    #     op.drop_column("audit_logs", "data")


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1) Recreate legacy "data" column (nullable) and backfill from details if needed
    cols = {c["name"] for c in insp.get_columns("audit_logs")}
    if "data" not in cols:
        op.add_column("audit_logs", sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        if "details" in cols:
            op.execute("UPDATE audit_logs SET data = details WHERE data IS NULL AND details IS NOT NULL")

    # 2) Drop index, convert ENUM -> TEXT (keeps data)
    try:
        op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    except Exception:
        pass

    cols = {c["name"] for c in insp.get_columns("audit_logs")}
    if "action" in cols:
        action_col = next((c for c in insp.get_columns("audit_logs") if c["name"] == "action"), None)
        is_enum = action_col and "enum" in str(action_col.get("type", "")).lower()
        
        if is_enum:
            op.add_column("audit_logs", sa.Column("action_text_tmp", sa.Text(), nullable=True))
            op.execute("UPDATE audit_logs SET action_text_tmp = action::text")
            op.drop_column("audit_logs", "action")
            op.alter_column("audit_logs", "action_text_tmp", new_column_name="action", existing_type=sa.Text(), nullable=True)

    # 3) Drop details if you want to restore strictly to legacy
    # op.drop_column("audit_logs", "details")

    # 4) Drop enum type last
    try:
        audit_enum.drop(bind, checkfirst=True)
    except Exception:
        pass

