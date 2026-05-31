"""Initial schema for HeavySwarm Due Diligence Engine.

Revision ID: 001
Revises: 
Create Date: 2026-05-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create diligence_states table
    op.create_table(
        "diligence_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("state", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Create index on status for filtering
    op.create_index(
        "idx_diligence_status",
        "diligence_states",
        [sa.text("(state->>'status')")],
    )
    
    # Create index on ticker for filtering
    op.create_index(
        "idx_diligence_ticker",
        "diligence_states",
        [sa.text("(state->'thesis'->>'ticker')")],
    )
    
    # Create index on updated_at for sorting
    op.create_index(
        "idx_diligence_updated",
        "diligence_states",
        ["updated_at"],
    )
    
    # Create audit_events table
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("diligence_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("agent_id", sa.String(50), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False, default={}),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Create index on diligence_id for lookups
    op.create_index(
        "idx_audit_diligence",
        "audit_events",
        ["diligence_id"],
    )
    
    # Create index on timestamp for sorting
    op.create_index(
        "idx_audit_timestamp",
        "audit_events",
        ["timestamp"],
    )
    
    # Create data_provenance table
    op.create_table(
        "data_provenance",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("diligence_id", sa.String(36), nullable=False),
        sa.Column("data_id", sa.String(100), nullable=False),
        sa.Column("value", postgresql.JSONB()),
        sa.Column("source_url", sa.Text()),
        sa.Column("verification_level", sa.String(10)),
        sa.Column("confidence", sa.Float()),
        sa.Column("chain_of_custody", postgresql.JSONB(), default=[]),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Create index on diligence_id for lookups
    op.create_index(
        "idx_provenance_diligence",
        "data_provenance",
        ["diligence_id"],
    )
    
    # Create index on data_id for lookups
    op.create_index(
        "idx_provenance_data",
        "data_provenance",
        ["data_id"],
    )
    
    # Create webhooks table
    op.create_table(
        "webhooks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("events", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("secret", sa.String(255)),
        sa.Column("metadata", postgresql.JSONB(), default={}),
        sa.Column("status", sa.String(20), default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Create index on status for filtering
    op.create_index(
        "idx_webhook_status",
        "webhooks",
        ["status"],
    )
    
    # Create api_keys table for authentication
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(100)),
        sa.Column("scopes", postgresql.ARRAY(sa.String()), default=[]),
        sa.Column("rate_limit", sa.Integer(), default=100),
        sa.Column("status", sa.String(20), default="active"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    
    # Create index on key_hash for lookups
    op.create_index(
        "idx_api_key_hash",
        "api_keys",
        ["key_hash"],
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("api_keys")
    op.drop_table("webhooks")
    op.drop_table("data_provenance")
    op.drop_table("audit_events")
    op.drop_table("diligence_states")
