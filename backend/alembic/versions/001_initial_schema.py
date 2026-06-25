"""Initial PostgreSQL schema baseline — tables created by create_all in lifespan."""
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass  # Tables created by Base.metadata.create_all on startup


def downgrade() -> None:
    pass
