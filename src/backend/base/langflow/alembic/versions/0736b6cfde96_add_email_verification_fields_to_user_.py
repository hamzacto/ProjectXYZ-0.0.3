"""Add email verification fields to user table

Revision ID: 0736b6cfde96
Revises: 6049ac734dc9
Create Date: 2025-04-01 21:56:21.556407

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.engine.reflection import Inspector
from langflow.utils import migration
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '0736b6cfde96'
down_revision: Union[str, None] = '6049ac734dc9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Get existing columns in the user table
    columns = [col['name'] for col in inspector.get_columns('user')]
    
    # Only proceed with adding columns that don't already exist
    with op.batch_alter_table('user', schema=None) as batch_op:
        # Add email column if it doesn't exist
        if 'email' not in columns:
            batch_op.add_column(sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
            
        # Add is_verified column if it doesn't exist
        if 'is_verified' not in columns:
            batch_op.add_column(sa.Column('is_verified', sa.Boolean(), nullable=True))
            
        # Add verification_token column if it doesn't exist
        if 'verification_token' not in columns:
            batch_op.add_column(sa.Column('verification_token', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
            
        # Add verification_token_expiry column if it doesn't exist
        if 'verification_token_expiry' not in columns:
            batch_op.add_column(sa.Column('verification_token_expiry', sa.DateTime(), nullable=True))
    
    # Only update columns that were newly added
    if 'email' not in columns:
        # For email, we'll use username + @example.com as a temporary value
        op.execute("UPDATE \"user\" SET email = username || '@example.com' WHERE email IS NULL")
    
    if 'is_verified' not in columns:
        # For is_verified, we'll set existing users as verified (True)
        op.execute("UPDATE \"user\" SET is_verified = TRUE WHERE is_verified IS NULL")
    
    # Only add constraints for columns that were newly added
    with op.batch_alter_table('user', schema=None) as batch_op:
        if 'email' not in columns:
            # Alter email column to add NOT NULL constraint
            batch_op.alter_column('email', existing_type=sqlmodel.sql.sqltypes.AutoString(), nullable=False)
            # Create unique index for email
            batch_op.create_index(batch_op.f('ix_user_email'), ['email'], unique=True)
            
        if 'is_verified' not in columns:
            # Alter is_verified column to add NOT NULL constraint
            batch_op.alter_column('is_verified', existing_type=sa.Boolean(), nullable=False)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Get existing columns in the user table
    columns = [col['name'] for col in inspector.get_columns('user')]
    
    # Only proceed with dropping columns that exist
    with op.batch_alter_table('user', schema=None) as batch_op:
        # Drop index on email if it exists
        indices = [idx['name'] for idx in inspector.get_indexes('user')]
        if 'ix_user_email' in indices:
            batch_op.drop_index(batch_op.f('ix_user_email'))
        
        # Drop columns if they exist
        if 'verification_token_expiry' in columns:
            batch_op.drop_column('verification_token_expiry')
        
        if 'verification_token' in columns:
            batch_op.drop_column('verification_token')
        
        if 'is_verified' in columns:
            batch_op.drop_column('is_verified')
        
        if 'email' in columns:
            batch_op.drop_column('email')
