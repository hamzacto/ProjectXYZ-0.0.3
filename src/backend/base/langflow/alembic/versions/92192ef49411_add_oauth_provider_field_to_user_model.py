"""Add oauth_provider field to User model

Revision ID: 92192ef49411
Revises: 0736b6cfde96
Create Date: 2025-04-03 01:39:00.492429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.engine.reflection import Inspector
from langflow.utils import migration
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '92192ef49411'
down_revision: Union[str, None] = '0736b6cfde96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Get existing columns in the user table
    columns = [col['name'] for col in inspector.get_columns('user')]
    
    # Only proceed with adding the column if it doesn't already exist
    if 'oauth_provider' not in columns:
        with op.batch_alter_table('user', schema=None) as batch_op:
            batch_op.add_column(sa.Column('oauth_provider', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Get existing columns in the user table
    columns = [col['name'] for col in inspector.get_columns('user')]
    
    # Only proceed with dropping the column if it exists
    if 'oauth_provider' in columns:
        with op.batch_alter_table('user', schema=None) as batch_op:
            batch_op.drop_column('oauth_provider')
