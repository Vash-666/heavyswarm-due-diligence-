"""Add checkpoints table and archive support.

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
    # Add archived columns to diligence_states
    op.add_column(
        "diligence_states",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "diligence_states",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create index on archived for filtering
    op.create_index(
        "idx_diligence_archived",
        "diligence_states",
        ["archived"],
    )
    
    # Create checkpoints table
    op.create_table(
        "diligence_checkpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("diligence_id", sa.String(36), nullable=False),
        sa.Column("checkpoint_data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column("phase", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False, default=[]),
        sa.Column("parent_checkpoint_id", sa.String(36), nullable=True),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    
    # Create indexes for checkpoints
    op.create_index(
        "idx_checkpoint_diligence",
        "diligence_checkpoints",
        ["diligence_id"],
    )
    op.create_index(
        "idx_checkpoint_created",
        "diligence_checkpoints",
        ["created_at"],
    )
    op.create_index(
        "idx_checkpoint_parent",
        "diligence_checkpoints",
        ["parent_checkpoint_id"],
    )
    op.create_index(
        "idx_checkpoint_deleted",
        "diligence_checkpoints",
        ["deleted"],
    )


def downgrade() -> None:
    # Drop checkpoint indexes
    op.drop_index("idx_checkpoint_deleted", table_name="diligence_checkpoints")
    op.drop_index("idx_checkpoint_parent", table_name="diligence_checkpoints")
    op.drop_index("idx_checkpoint_created", table_name="diligence_checkpoints")
    op.drop_index("idx_checkpoint_diligence", table_name="diligence_checkpoints")
    
    # Drop checkpoints table
    op.drop_table("diligence_checkpoints")
    
    # Drop archived columns from diligence_states
    op.drop_index("idx_diligence_archived", table_name="diligence_states")
    op.drop_column("diligence_states", "archived_at")
    op.drop_column("diligence_states", "archived")
