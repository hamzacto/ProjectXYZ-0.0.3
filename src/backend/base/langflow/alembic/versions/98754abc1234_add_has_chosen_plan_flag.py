"""Add has_chosen_plan flag to User model

Revision ID: 98754abc1234
Revises: 24ee770258a4
Create Date: 2025-04-17 10:45:23.571829

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = '98754abc1234'
down_revision: Union[str, None] = '24ee770258a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    # Add has_chosen_plan column to user table if it exists
    if 'user' in tables:
        columns = inspector.get_columns('user')
        column_names = [column['name'] for column in columns]
        
        with op.batch_alter_table('user', schema=None) as batch_op:
            # Only add the column if it doesn't already exist
            if 'has_chosen_plan' not in column_names:
                batch_op.add_column(sa.Column('has_chosen_plan', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()
    
    # Remove has_chosen_plan column from user table if it exists
    if 'user' in tables:
        columns = inspector.get_columns('user')
        column_names = [column['name'] for column in columns]
        
        with op.batch_alter_table('user', schema=None) as batch_op:
            if 'has_chosen_plan' in column_names:
                batch_op.drop_column('has_chosen_plan') 