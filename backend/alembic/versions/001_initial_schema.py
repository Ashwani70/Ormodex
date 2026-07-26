"""Initial PostgreSQL schema baseline."""
import sys
from pathlib import Path
from alembic import op

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.db import Base
# Import for side effect: registers every ORM model on Base.metadata. Without
# this, create_all() below silently creates ZERO tables (Base alone carries an
# empty metadata) and every later migration fails on missing relations.
import core.schema  # noqa: F401

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    pass

