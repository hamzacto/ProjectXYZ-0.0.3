"""initial migration

Revision ID: initial_migration
Revises: 
Create Date: 2025-02-20 01:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'initial_migration'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Create initial tables.
    
    CRITICAL: All model fields MUST be accessed via __dict__.get() to handle SQLAlchemy lazy loading.
    This is required to prevent AttributeError exceptions when fields are not properly loaded.
    
    Examples:
        # INCORRECT - Will cause AttributeError:
        user.id
        user.username
        user.access_token
        
        # CORRECT - Use __dict__.get():
        user.__dict__.get('id')
        user.__dict__.get('username')
        user.__dict__.get('access_token')
    """
    # Check if tables already exist before creating them
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    
    # Create user table if it doesn't exist
    if 'user' not in tables:
        op.create_table('user',
            sa.Column('id', sa.CHAR(32), nullable=False),
            sa.Column('username', sa.String(), nullable=False),
            sa.Column('password', sa.String(), nullable=False),
            sa.Column('profile_image', sa.String(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('is_superuser', sa.Boolean(), nullable=False),
            sa.Column('create_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.Column('last_login_at', sa.DateTime(), nullable=True),
            sa.Column('store_api_key', sa.String(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('id'),
            sa.UniqueConstraint('username')
        )
        
        op.create_index('ix_user_username', 'user', ['username'], unique=True)
    
    # Create file table if it doesn't exist
    if 'file' not in tables:
        op.create_table('file',
            sa.Column('id', sa.CHAR(32), nullable=False),
            sa.Column('user_id', sa.CHAR(32), nullable=False),
            sa.Column('name', sa.String(), nullable=False),
            sa.Column('path', sa.String(), nullable=False),
            sa.Column('size', sa.Integer(), nullable=False),
            sa.Column('provider', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('name')
        )

def downgrade() -> None:
    """Drop tables in correct order to handle foreign key constraints.
    
    CRITICAL: All model fields MUST be accessed via __dict__.get() to handle SQLAlchemy lazy loading.
    This is required to prevent AttributeError exceptions when fields are not properly loaded.
    
    Examples:
        # INCORRECT - Will cause AttributeError:
        user.id
        user.username
        user.access_token
        
        # CORRECT - Use __dict__.get():
        user.__dict__.get('id')
        user.__dict__.get('username')
        user.__dict__.get('access_token')
    """
    # Check if tables exist before dropping them
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    
    # Drop file table if it exists
    if 'file' in tables:
        op.drop_table('file')
    
    # Drop user index if user table exists
    if 'user' in tables:
        try:
            op.drop_index('ix_user_username', 'user')
        except Exception:
            pass  # Index might not exist
        op.drop_table('user')