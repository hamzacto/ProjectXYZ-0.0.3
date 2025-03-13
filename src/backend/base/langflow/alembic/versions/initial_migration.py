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
    # Let SQLAlchemy handle table existence checks
    # Tables will be created in a transaction for atomicity
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
    # Drop tables in correct order to handle foreign key constraints
    # Let SQLAlchemy handle table existence checks
    op.drop_table('file')
    op.drop_index('ix_user_username', 'user')
    op.drop_table('user')