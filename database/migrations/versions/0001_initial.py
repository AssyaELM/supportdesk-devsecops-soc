"""Initial schema. Frozen migration independent of future ORM changes."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sd_users', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('email', sa.String(254), nullable=False, unique=True), sa.Column('name', sa.String(100), nullable=False), sa.Column('password_hash', sa.String(255), nullable=False), sa.Column('role', sa.String(10), nullable=False), sa.Column('active', sa.Boolean(), nullable=False), sa.Column('demo_key', sa.String(60), unique=True), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.CheckConstraint("role in ('user','admin')"))
    op.create_table('sd_categories', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('name', sa.String(60), unique=True, nullable=False))
    op.create_table('sd_sessions', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('token_hash', sa.String(64), unique=True, nullable=False), sa.Column('csrf_hash', sa.String(64), nullable=False), sa.Column('user_id', sa.Integer(), sa.ForeignKey('sd_users.id'), nullable=False), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_sd_sessions_user_id', 'sd_sessions', ['user_id'])
    op.create_index('ix_sd_sessions_expires_at', 'sd_sessions', ['expires_at'])
    op.create_table('sd_password_resets', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('token_hash', sa.String(64), unique=True, nullable=False), sa.Column('user_id', sa.Integer(), sa.ForeignKey('sd_users.id'), nullable=False), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('sd_tickets', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('title', sa.String(160), nullable=False), sa.Column('description', sa.Text(), nullable=False), sa.Column('category_id', sa.Integer(), sa.ForeignKey('sd_categories.id'), nullable=False), sa.Column('priority', sa.String(15), nullable=False), sa.Column('status', sa.String(20), nullable=False), sa.Column('requester_id', sa.Integer(), sa.ForeignKey('sd_users.id'), nullable=False), sa.Column('assignee_id', sa.Integer(), sa.ForeignKey('sd_users.id')), sa.Column('demo_key', sa.String(60), unique=True), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False), sa.CheckConstraint("status in ('Nouveau','En cours','En attente','Résolu')"), sa.CheckConstraint("priority in ('Basse','Moyenne','Haute')"))
    for col in ['requester_id', 'status']:
        op.create_index('ix_sd_tickets_' + col, 'sd_tickets', [col])
    op.create_table('sd_messages', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('sd_tickets.id'), nullable=False), sa.Column('author_id', sa.Integer(), sa.ForeignKey('sd_users.id'), nullable=False), sa.Column('body', sa.Text(), nullable=False), sa.Column('internal', sa.Boolean(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_sd_messages_ticket_id', 'sd_messages', ['ticket_id'])
    op.create_table('sd_ticket_history', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('ticket_id', sa.Integer(), sa.ForeignKey('sd_tickets.id'), nullable=False), sa.Column('actor_id', sa.Integer(), sa.ForeignKey('sd_users.id'), nullable=False), sa.Column('field', sa.String(30), nullable=False), sa.Column('old_value', sa.String(160)), sa.Column('new_value', sa.String(160), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_sd_ticket_history_ticket_id', 'sd_ticket_history', ['ticket_id'])
    op.create_table('sd_audit_events', sa.Column('id', sa.Integer(), primary_key=True), sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False), sa.Column('event', sa.String(40), nullable=False), sa.Column('user_id', sa.Integer()), sa.Column('role', sa.String(10)), sa.Column('result', sa.String(20), nullable=False), sa.Column('request_id', sa.String(64), nullable=False), sa.Column('resource', sa.String(100)), sa.Column('demo', sa.Boolean(), nullable=False), sa.Column('details', sa.JSON(), nullable=False))
    for col in ['timestamp', 'event']:
        op.create_index('ix_sd_audit_events_' + col, 'sd_audit_events', [col])


def downgrade():
    raise RuntimeError('Suppression destructive désactivée. Prévoir une restauration validée.')
