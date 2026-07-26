"""Initial PostgreSQL schema baseline."""
import sys
from pathlib import Path
from alembic import op

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.db import Base

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    pass

