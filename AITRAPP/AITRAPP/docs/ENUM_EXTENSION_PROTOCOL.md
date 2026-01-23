# Enum Extension Protocol

When adding a new audit action in the future, follow this protocol to ensure safe, reversible changes.

## ⚠️ Never Edit Enum Values In Place

**DO NOT** directly modify existing enum values. Always use `ALTER TYPE ... ADD VALUE` in a migration.

## ✅ Correct Process

### 1. Add to Model First

Update `packages/storage/models.py`:

```python
class AuditActionEnum(PyEnum):
    """Audit log action types"""
    # ... existing values ...
    NEW_ACTION = "NEW_ACTION"  # Add new value
```

### 2. Create Migration

Create a new Alembic migration:

```python
"""Add NEW_ACTION to auditactionenum

Revision ID: YYYYMMDD_add_new_action
Revises: <previous_revision>
Create Date: YYYY-MM-DD

"""
from alembic import op

revision = 'YYYYMMDD_add_new_action'
down_revision = '<previous_revision>'
branch_labels = None
depends_on = None

def upgrade():
    # Add new value to enum type
    op.execute("ALTER TYPE auditactionenum ADD VALUE IF NOT EXISTS 'NEW_ACTION'")

def downgrade():
    # Note: PostgreSQL doesn't support removing enum values
    # If you need to remove, you'll need to:
    # 1. Create new enum type without the value
    # 2. Migrate data
    # 3. Drop old enum
    # This is complex - consider deprecating instead of removing
    pass
```

### 3. Update Code

Use the new enum value in your code:

```python
from packages.storage.models import AuditActionEnum

audit_log = AuditLog(
    action=AuditActionEnum.NEW_ACTION,
    message="New action occurred",
    details={"key": "value"}
)
```

### 4. Update Tests

Add tests for the new action:

```python
def test_new_action_audit_log():
    # Test that new action can be created and retrieved
    pass
```

### 5. Update CI/CD

Ensure CI runs migrations and tests pass.

## 📋 Checklist

- [ ] Added to `AuditActionEnum` in models
- [ ] Created migration with `ALTER TYPE ... ADD VALUE`
- [ ] Updated code to use new enum value
- [ ] Added tests
- [ ] CI passes
- [ ] Documentation updated (if needed)

## 🔄 Rollback

If you need to rollback:

1. **Deprecate, don't remove**: Mark the enum value as deprecated in code
2. **Stop using**: Remove all code that uses the deprecated value
3. **Data migration**: Update existing records if needed
4. **Enum removal**: Only if absolutely necessary, create a complex migration to:
   - Create new enum without the value
   - Migrate all data
   - Drop old enum
   - Rename new enum

**Recommendation**: Keep deprecated values in the enum but stop using them in code. This avoids complex migrations.

## 💡 Best Practices

1. **Plan ahead**: Think about what actions you'll need before creating the enum
2. **Document**: Add docstrings explaining what each action means
3. **Test**: Always test enum additions in a development environment first
4. **Review**: Have migrations reviewed before merging
5. **Monitor**: Watch for any issues after deploying enum changes

## 🚫 Anti-Patterns

- ❌ **Don't** edit enum values directly in the database
- ❌ **Don't** remove enum values without a migration plan
- ❌ **Don't** use string literals instead of enum values
- ❌ **Don't** skip migrations for enum changes

