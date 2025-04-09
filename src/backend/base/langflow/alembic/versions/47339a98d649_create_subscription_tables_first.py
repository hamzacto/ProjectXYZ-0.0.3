"""create_subscription_tables_first

Revision ID: 47339a98d649
Revises: 3d743a48639b
Create Date: 2025-04-08 01:42:58.824558

"""
from typing import Sequence, Union
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.engine.reflection import Inspector
from alembic.operations import Operations
from alembic.operations.ops import MigrationScript


# revision identifiers, used by Alembic.
revision: str = '47339a98d649'
down_revision: Union[str, None] = '3d743a48639b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # We'll use a brute-force approach to clear previous tables/FKs and build from scratch
    # This is safe since we're in the initial development phase
    
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # Drop tables if they exist (in reverse dependency order)
    for table in ['invoice', 'daily_usage_summary', 'kbusagedetail', 'toolusagedetail', 
                 'tokenusagedetail', 'usagerecord', 'billingperiod', 'subscriptionplan']:
        if table in inspector.get_table_names():
            try:
                # Try to drop any foreign keys first
                for fk in inspector.get_foreign_keys(table):
                    if fk.get('name'):
                        op.drop_constraint(fk['name'], table, type_='foreignkey')
            except Exception:
                pass  # Ignore errors if constraints don't exist
                
            print(f"Dropping {table} table...")
            op.drop_table(table)
    
    # Clean up user table
    user_columns = [column['name'] for column in inspector.get_columns('user')]
    billing_columns = [
        'subscription_plan_id', 'credits_balance', 'billing_day', 'subscription_status',
        'subscription_start_date', 'subscription_end_date', 'trial_start_date',
        'trial_end_date', 'trial_converted', 'daily_flow_runs', 'daily_flow_runs_reset_at',
        'daily_kb_queries', 'daily_kb_queries_reset_at'
    ]
    
    for column in billing_columns:
        if column in user_columns:
            print(f"Dropping {column} column from User table...")
            try:
                op.drop_column('user', column)
            except Exception:
                pass  # Ignore errors if column doesn't exist
    
    # STAGE 1: Create all tables with appropriate foreign keys
    
    # Step 1: Create the subscriptionplan table (no foreign keys)
    print("Creating SubscriptionPlan table...")
    op.create_table(
        'subscriptionplan',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False, index=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('monthly_quota_credits', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('max_flows', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('max_flow_runs_per_day', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('max_concurrent_flows', sa.Integer(), nullable=False, server_default="1"),
        sa.Column('max_kb_storage_mb', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('max_kbs_per_user', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('max_kb_entries_per_kb', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('max_tokens_per_kb_entry', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('max_kb_queries_per_day', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('allowed_models', sa.JSON(), nullable=False),
        sa.Column('price_monthly_usd', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('price_yearly_usd', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('features', sa.JSON(), nullable=False),
        sa.Column('allowed_premium_tools', sa.JSON(), nullable=False),
        sa.Column('overage_price_per_credit', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('allows_overage', sa.Boolean(), nullable=False, server_default="0"),
        sa.Column('trial_days', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default="1"),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    
    # Step 2: Add billing columns to User table
    print("Adding billing columns to User table...")
    op.add_column('user', sa.Column('credits_balance', sa.Float(), nullable=True))
    op.add_column('user', sa.Column('billing_day', sa.Integer(), nullable=True))
    op.add_column('user', sa.Column('subscription_plan_id', sa.Uuid(), nullable=True))
    op.add_column('user', sa.Column('subscription_status', sa.String(), nullable=True))
    op.add_column('user', sa.Column('subscription_start_date', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('subscription_end_date', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('trial_start_date', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('trial_end_date', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('trial_converted', sa.Boolean(), nullable=True))
    op.add_column('user', sa.Column('daily_flow_runs', sa.Integer(), nullable=True))
    op.add_column('user', sa.Column('daily_flow_runs_reset_at', sa.DateTime(), nullable=True))
    op.add_column('user', sa.Column('daily_kb_queries', sa.Integer(), nullable=True))
    op.add_column('user', sa.Column('daily_kb_queries_reset_at', sa.DateTime(), nullable=True))
    
    # Set default values for new columns
    if conn.dialect.name == 'sqlite':
        print("Setting default values for newly added columns...")
        op.execute("UPDATE user SET credits_balance = 0.0 WHERE credits_balance IS NULL")
        op.execute("UPDATE user SET billing_day = 1 WHERE billing_day IS NULL")
        op.execute("UPDATE user SET subscription_status = 'trial' WHERE subscription_status IS NULL")
        op.execute("UPDATE user SET trial_converted = 0 WHERE trial_converted IS NULL")
        op.execute("UPDATE user SET daily_flow_runs = 0 WHERE daily_flow_runs IS NULL")
        op.execute("UPDATE user SET daily_kb_queries = 0 WHERE daily_kb_queries IS NULL")
    
    # Use batch mode to add the foreign key constraint for SQLite compatibility
    print("Creating foreign key fk_user_subscription_plan_id...")
    with op.batch_alter_table('user') as batch_op:
        batch_op.create_foreign_key(
            op.f("fk_user_subscription_plan_id"), 
            "subscriptionplan", 
            ["subscription_plan_id"], 
            ["id"]
        )

    # Add the index explicitly (Moved outside the else block)
    # Ensure column type in index matches column definition (sa.Uuid())
    op.create_index(op.f('ix_user_subscription_plan_id'), 'user', [sa.Column('subscription_plan_id', sa.Uuid(), nullable=True)], unique=False)
    
    # Step 3: Create billingperiod table with foreign keys included in table definition
    # Verify FK naming consistency below
    print("Creating BillingPeriod table...")
    op.create_table(
        'billingperiod',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), nullable=False, index=True),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=False),
        sa.Column('subscription_plan_id', sa.Uuid(), nullable=True, index=True),
        sa.Column('status', sa.String(), nullable=False, server_default="active"),
        sa.Column('quota_override', sa.Float(), nullable=True),
        sa.Column('quota_used', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('quota_remaining', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('overage_credits', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('overage_cost', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('is_plan_change', sa.Boolean(), nullable=False, server_default="0"),
        sa.Column('previous_plan_id', sa.Uuid(), nullable=True),
        sa.Column('invoiced', sa.Boolean(), nullable=False, server_default="0"),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        # Use op.f() for constraint names or ensure explicit names are consistent
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_billingperiod_user_id'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_plan_id'], ['subscriptionplan.id'], name=op.f('fk_billingperiod_subscription_plan_id'))
    )
    # Add index for status column
    op.create_index(op.f('ix_billingperiod_status'), 'billingperiod', ['status'], unique=False)
    
    # Step 4: Create usagerecord table with foreign keys included in table definition
    print("Creating UsageRecord table...")
    op.create_table(
        'usagerecord',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), nullable=False, index=True),
        sa.Column('flow_id', sa.Uuid(), nullable=False, index=True),
        sa.Column('session_id', sa.String(), nullable=False, index=True),
        sa.Column('fixed_cost', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('llm_cost', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('tools_cost', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('kb_cost', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('total_cost', sa.Float(), nullable=False, server_default="0.0"),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('billing_period_id', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_usagerecord_user_id'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['flow_id'], ['flow.id'], name=op.f('fk_usagerecord_flow_id'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['billing_period_id'], ['billingperiod.id'], name=op.f('fk_usagerecord_billing_period_id'))
    )
    
    # Step 5: Create tokenusagedetail table with foreign keys included in table definition
    print("Creating TokenUsageDetail table...")
    op.create_table(
        'tokenusagedetail',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('usage_record_id', sa.Uuid(), nullable=False, index=True),
        sa.Column('model_name', sa.String(), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('cost', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usage_record_id'], ['usagerecord.id'], name=op.f('fk_tokenusagedetail_usage_record_id'), ondelete='CASCADE')
    )
    
    # Step 6: Create toolusagedetail table with foreign keys included in table definition
    print("Creating ToolUsageDetail table...")
    op.create_table(
        'toolusagedetail',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('usage_record_id', sa.Uuid(), nullable=False, index=True),
        sa.Column('tool_name', sa.String(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default="1"),
        sa.Column('cost', sa.Float(), nullable=False),
        sa.Column('is_premium', sa.Boolean(), nullable=False, server_default="0"),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usage_record_id'], ['usagerecord.id'], name=op.f('fk_toolusagedetail_usage_record_id'), ondelete='CASCADE')
    )
    
    # Step 7: Create kbusagedetail table with foreign keys included in table definition
    print("Creating KBUsageDetail table...")
    op.create_table(
        'kbusagedetail',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('usage_record_id', sa.Uuid(), nullable=False, index=True),
        sa.Column('kb_name', sa.String(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False, server_default="1"),
        sa.Column('cost', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['usage_record_id'], ['usagerecord.id'], name=op.f('fk_kbusagedetail_usage_record_id'), ondelete='CASCADE')
    )
    
    # Step 8: Create daily_usage_summary table with foreign keys included in table definition
    print("Creating DailyUsageSummary table...")
    op.create_table(
        'daily_usage_summary',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), nullable=False, index=True),
        sa.Column('date', sa.DateTime(), nullable=False, index=True),
        sa.Column('flow_runs', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('kb_queries', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('api_calls', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('tokens_used', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('total_cost', sa.Float(), nullable=False, server_default="0.0"),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_daily_usage_summary_user_id'), ondelete='CASCADE')
    )
    
    # Step 9: Create invoice table with foreign keys included in table definition
    print("Creating Invoice table...")
    op.create_table(
        'invoice',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), nullable=False, index=True),
        sa.Column('billing_period_id', sa.Uuid(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default="pending"),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], name=op.f('fk_invoice_user_id'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['billing_period_id'], ['billingperiod.id'], name=op.f('fk_invoice_billing_period_id'))
    )
    
    print("Migration complete!")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # Drop tables in reverse order of creation (to respect foreign key constraints)
    for table in ['invoice', 'daily_usage_summary', 'kbusagedetail', 'toolusagedetail', 
                 'tokenusagedetail', 'usagerecord', 'billingperiod']:
        if table in inspector.get_table_names():
            print(f"Dropping {table} table...")
            op.drop_table(table)
    
    # Check user columns and drop them if they exist
    user_columns = [column['name'] for column in inspector.get_columns('user')]
    billing_columns = [
        'subscription_plan_id', 'credits_balance', 'billing_day', 'subscription_status',
        'subscription_start_date', 'subscription_end_date', 'trial_start_date',
        'trial_end_date', 'trial_converted', 'daily_flow_runs', 'daily_flow_runs_reset_at',
        'daily_kb_queries', 'daily_kb_queries_reset_at'
    ]
    
    for column in billing_columns:
        if column in user_columns:
            print(f"Dropping {column} column from User table...")
            try:
                op.drop_column('user', column)
            except Exception:
                pass  # Ignore errors
    
    # Drop subscription plan table last (after FK references are gone)
    if 'subscriptionplan' in inspector.get_table_names():
        print("Dropping subscriptionplan table...")
        op.drop_table('subscriptionplan')
    
    print("Downgrade complete!")
