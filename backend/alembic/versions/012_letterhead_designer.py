"""Letterhead Designer — create letterhead_templates and letterhead_versions tables."""
from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS letterhead_templates (
            id                  varchar PRIMARY KEY,
            tenant_id           varchar,
            branch_id           varchar,
            template_name       varchar,
            theme               varchar DEFAULT 'corporate_blue',
            page_size           varchar DEFAULT 'A4',
            margin_top          numeric(18,4) DEFAULT 20,
            margin_bottom       numeric(18,4) DEFAULT 20,
            margin_left         numeric(18,4) DEFAULT 20,
            margin_right        numeric(18,4) DEFAULT 20,
            header_height       numeric(18,4) DEFAULT 35,
            footer_height       numeric(18,4) DEFAULT 25,
            logo_position       varchar DEFAULT 'left',
            logo_url            varchar,
            logo2_url           varchar,
            logo_width_mm       numeric(18,4) DEFAULT 40,
            logo_height_mm      numeric(18,4) DEFAULT 20,
            header_elements     jsonb,
            footer_elements     jsonb,
            watermark_text      varchar,
            watermark_opacity   numeric(18,4) DEFAULT 0.08,
            watermark_angle     numeric(18,4) DEFAULT -45,
            watermark_font_size numeric(18,4) DEFAULT 60,
            watermark_color     varchar DEFAULT '#888888',
            background_image    varchar,
            primary_color       varchar DEFAULT '#1a56db',
            secondary_color     varchar DEFAULT '#f3f4f6',
            accent_color        varchar DEFAULT '#f59e0b',
            text_color          varchar DEFAULT '#111827',
            header_bg_color     varchar DEFAULT '#ffffff',
            footer_bg_color     varchar DEFAULT '#f8fafc',
            font_family         varchar DEFAULT 'Helvetica',
            font_size_body      numeric(18,4) DEFAULT 10,
            applied_to          jsonb DEFAULT '[]'::jsonb,
            is_default          boolean NOT NULL DEFAULT FALSE,
            is_active           boolean NOT NULL DEFAULT TRUE,
            version             integer DEFAULT 1,
            created_by          varchar,
            updated_by          varchar,
            is_deleted          boolean NOT NULL DEFAULT FALSE,
            deleted_at          varchar,
            created_at          varchar,
            updated_at          varchar
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_letterhead_templates_tenant_id ON letterhead_templates (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_letterhead_templates_tenant_default ON letterhead_templates (tenant_id, is_default)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS letterhead_versions (
            id          varchar PRIMARY KEY,
            tenant_id   varchar,
            template_id varchar,
            version     integer DEFAULT 1,
            snapshot    jsonb,
            changed_by  varchar,
            change_note varchar,
            created_at  varchar
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_letterhead_versions_template_id ON letterhead_versions (template_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_letterhead_versions_tenant_id ON letterhead_versions (tenant_id)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS letterhead_versions")
    op.execute("DROP TABLE IF EXISTS letterhead_templates")
