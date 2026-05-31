"""Add webhook_deliveries table for delivery tracking.

Revision ID: 002
Revises: 001
Create Date: 2026-05-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create webhook_deliveries table
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("webhook_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, default={}),
        sa.Column("status", sa.String(20), default="pending"),  # pending, delivered, failed, retrying, dead_letter
        sa.Column("attempt_count", sa.Integer(), default=0),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("http_status", sa.Integer()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Create indexes
    op.create_index(
        "idx_delivery_webhook",
        "webhook_deliveries",
        ["webhook_id"],
    )
    
    op.create_index(
        "idx_delivery_status",
        "webhook_deliveries",
        ["status"],
    )
    
    op.create_index(
        "idx_delivery_created",
        "webhook_deliveries",
        ["created_at"],
    )
    
    op.create_index(
        "idx_delivery_next_retry",
        "webhook_deliveries",
        ["next_retry_at"],
    )
    
    # Add consecutive_failures column to webhooks table
    op.add_column(
        "webhooks",
        sa.Column("consecutive_failures", sa.Integer(), default=0),
    )
    
    op.add_column(
        "webhooks",
        sa.Column("last_delivered_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    # Drop columns from webhooks
    op.drop_column("webhooks", "consecutive_failures")
    op.drop_column("webhooks", "last_delivered_at")
    
    # Drop webhook_deliveries table
    op.drop_table("webhook_deliveries")
