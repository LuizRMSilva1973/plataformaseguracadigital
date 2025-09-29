from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('tenants',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='active'),
        sa.Column('plan', sa.String(), nullable=False, server_default='starter'),
        sa.Column('ingest_token', sa.String(), nullable=False, unique=True),
        sa.Column('alert_email', sa.String(), nullable=True),
        sa.Column('integrations_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    op.create_table('users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False, server_default='viewer'),
        sa.Column('status', sa.String(), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('password_hash', sa.String(), nullable=True),
    )

    op.create_table('agents',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('os', sa.String(), nullable=True),
        sa.Column('version', sa.String(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(), server_default='active'),
    )

    op.create_table('ingest_batches',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('agent_id', sa.String(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('batch_id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    with op.batch_alter_table('ingest_batches', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_batch', ['tenant_id', 'agent_id', 'batch_id'])

    op.create_table('events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('agent_id', sa.String(), sa.ForeignKey('agents.id'), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('host', sa.String(), nullable=True),
        sa.Column('app', sa.String(), nullable=True),
        sa.Column('event_type', sa.String(), nullable=True),
        sa.Column('src_ip', sa.String(), nullable=True),
        sa.Column('dst_ip', sa.String(), nullable=True),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('severity', sa.String(), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
    )

    op.create_table('incidents',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=False),
        sa.Column('first_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('context_json', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='open'),
    )

    op.create_table('ip_reputation_cache',
        sa.Column('ip', sa.String(), primary_key=True),
        sa.Column('asn', sa.String(), nullable=True),
        sa.Column('country', sa.String(), nullable=True),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    op.create_table('reports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('url_pdf', sa.String(), nullable=True),
        sa.Column('score', sa.Integer(), nullable=True),
        sa.Column('summary_json', sa.JSON(), nullable=True),
    )

    op.create_table('assets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('host', sa.String(), nullable=False),
        sa.Column('os', sa.String(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('agent_id', sa.String(), nullable=True),
    )
    with op.batch_alter_table('assets', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_asset_tenant_host', ['tenant_id', 'host'])

    op.create_table('notifications',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=True),
        sa.Column('channel', sa.String(), nullable=True),
        sa.Column('payload_json', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    op.create_table('subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table('audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )

    op.create_table('checklist_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('context_json', sa.JSON(), nullable=True),
        sa.Column('done', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    with op.batch_alter_table('checklist_items', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_checklist_key', ['tenant_id', 'key'])

    op.create_table('blocked_ips',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('ip', sa.String(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    with op.batch_alter_table('blocked_ips', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_blocked_ip', ['tenant_id', 'ip', 'provider'])


def downgrade() -> None:
    with op.batch_alter_table('blocked_ips', schema=None) as batch_op:
        batch_op.drop_constraint('uq_blocked_ip', type_='unique')
    op.drop_table('blocked_ips')
    with op.batch_alter_table('checklist_items', schema=None) as batch_op:
        batch_op.drop_constraint('uq_checklist_key', type_='unique')
    op.drop_table('checklist_items')
    op.drop_table('audit_logs')
    op.drop_table('subscriptions')
    op.drop_table('notifications')
    with op.batch_alter_table('assets', schema=None) as batch_op:
        batch_op.drop_constraint('uq_asset_tenant_host', type_='unique')
    op.drop_table('assets')
    op.drop_table('reports')
    op.drop_table('ip_reputation_cache')
    op.drop_table('incidents')
    op.drop_table('events')
    with op.batch_alter_table('ingest_batches', schema=None) as batch_op:
        batch_op.drop_constraint('uq_batch', type_='unique')
    op.drop_table('ingest_batches')
    op.drop_table('agents')
    op.drop_table('users')
    op.drop_table('tenants')

