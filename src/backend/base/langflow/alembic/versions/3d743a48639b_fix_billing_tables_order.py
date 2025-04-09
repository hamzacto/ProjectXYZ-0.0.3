"""fix_billing_tables_order

Revision ID: 3d743a48639b
Revises: 0cb2d40f2398
Create Date: 2025-04-08 01:35:24.042968

"""
from typing import Sequence, Union
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = '3d743a48639b'
down_revision: Union[str, None] = '0cb2d40f2398'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # First, check if subscription_plan_id column exists in user table and remove it if needed
    user_columns = [column['name'] for column in inspector.get_columns('user')]
    if 'subscription_plan_id' in user_columns:
        print("Temporarily removing subscription_plan_id from User table...")
        # Check for and drop any indexes on the column first
        indexes = inspector.get_indexes('user')
        for index in indexes:
            if 'subscription_plan_id' in index['column_names']:
                print(f"Dropping index {index['name']} first...")
                op.drop_index(index['name'], table_name='user')
        
        # Now drop the column using batch mode for SQLite compatibility
        with op.batch_alter_table('user') as batch_op:
            batch_op.drop_column('subscription_plan_id')
    
    # Step 1: Create the subscriptionplan table if it doesn't exist
    if "subscriptionplan" not in inspector.get_table_names():
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
    
    # Step 2: Now that subscriptionplan table exists, add the foreign key column to user
    if 'subscription_plan_id' not in user_columns:
        print("Adding subscription_plan_id column to User table...")
        op.add_column('user', sa.Column('subscription_plan_id', sa.Uuid(), nullable=True))
        
        # Add the foreign key constraint separately
        print("Adding foreign key constraint to subscription_plan_id...")
        op.create_foreign_key(
            "fk_user_subscription_plan_id", 
            "user", 
            "subscriptionplan", 
            ["subscription_plan_id"], 
            ["id"]
        )
    
    # Step 3: Create remaining billing tables
    if "billingperiod" not in inspector.get_table_names():
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
        )
        
        # Add foreign keys for billingperiod separately
        op.create_foreign_key(
            "fk_billingperiod_user_id", 
            "billingperiod", 
            "user", 
            ["user_id"], 
            ["id"], 
            ondelete="CASCADE"
        )
        op.create_foreign_key(
            "fk_billingperiod_subscription_plan_id", 
            "billingperiod", 
            "subscriptionplan", 
            ["subscription_plan_id"], 
            ["id"]
        )
    
    if "usagerecord" not in inspector.get_table_names():
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
        )
        
        # Add foreign keys for usagerecord separately
        op.create_foreign_key(
            "fk_usagerecord_user_id", 
            "usagerecord", 
            "user", 
            ["user_id"], 
            ["id"], 
            ondelete="CASCADE"
        )
        op.create_foreign_key(
            "fk_usagerecord_flow_id", 
            "usagerecord", 
            "flow", 
            ["flow_id"], 
            ["id"], 
            ondelete="CASCADE"
        )
        op.create_foreign_key(
            "fk_usagerecord_billing_period_id", 
            "usagerecord", 
            "billingperiod", 
            ["billing_period_id"], 
            ["id"]
        )
    
    if "tokenusagedetail" not in inspector.get_table_names():
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
        )
        
        # Add foreign key for tokenusagedetail separately
        op.create_foreign_key(
            "fk_tokenusagedetail_usage_record_id", 
            "tokenusagedetail", 
            "usagerecord", 
            ["usage_record_id"], 
            ["id"], 
            ondelete="CASCADE"
        )
    
    if "toolusagedetail" not in inspector.get_table_names():
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
        )
        
        # Add foreign key for toolusagedetail separately
        op.create_foreign_key(
            "fk_toolusagedetail_usage_record_id", 
            "toolusagedetail", 
            "usagerecord", 
            ["usage_record_id"], 
            ["id"], 
            ondelete="CASCADE"
        )
    
    if "kbusagedetail" not in inspector.get_table_names():
        print("Creating KBUsageDetail table...")
        op.create_table(
            'kbusagedetail',
            sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('usage_record_id', sa.Uuid(), nullable=False, index=True),
            sa.Column('kb_name', sa.String(), nullable=False),
            sa.Column('count', sa.Integer(), nullable=False, server_default="1"),
            sa.Column('cost', sa.Float(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False),
        )
        
        # Add foreign key for kbusagedetail separately
        op.create_foreign_key(
            "fk_kbusagedetail_usage_record_id", 
            "kbusagedetail", 
            "usagerecord", 
            ["usage_record_id"], 
            ["id"], 
            ondelete="CASCADE"
        )
    
    if "daily_usage_summary" not in inspector.get_table_names():
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
        )
        
        # Add foreign key for daily_usage_summary separately
        op.create_foreign_key(
            "fk_daily_usage_summary_user_id", 
            "daily_usage_summary", 
            "user", 
            ["user_id"], 
            ["id"], 
            ondelete="CASCADE"
        )
    
    if "invoice" not in inspector.get_table_names():
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
        )
        
        # Add foreign keys for invoice separately
        op.create_foreign_key(
            "fk_invoice_user_id", 
            "invoice", 
            "user", 
            ["user_id"], 
            ["id"], 
            ondelete="CASCADE"
        )
        op.create_foreign_key(
            "fk_invoice_billing_period_id", 
            "invoice", 
            "billingperiod", 
            ["billing_period_id"], 
            ["id"]
        )
    
    # Add other user billing fields if they don't exist
    user_columns = [column['name'] for column in inspector.get_columns('user')]
    
    if 'credits_balance' not in user_columns:
        print("Adding credits_balance column to User table...")
        op.add_column('user', sa.Column('credits_balance', sa.Float(), nullable=True))
    
    if 'billing_day' not in user_columns:
        print("Adding billing_day column to User table...")
        op.add_column('user', sa.Column('billing_day', sa.Integer(), nullable=True))
    
    if 'subscription_status' not in user_columns:
        print("Adding subscription_status column to User table...")
        op.add_column('user', sa.Column('subscription_status', sa.String(), nullable=True))
    
    if 'subscription_start_date' not in user_columns:
        print("Adding subscription_start_date column to User table...")
        op.add_column('user', sa.Column('subscription_start_date', sa.DateTime(), nullable=True))
    
    if 'subscription_end_date' not in user_columns:
        print("Adding subscription_end_date column to User table...")
        op.add_column('user', sa.Column('subscription_end_date', sa.DateTime(), nullable=True))
    
    if 'trial_start_date' not in user_columns:
        print("Adding trial_start_date column to User table...")
        op.add_column('user', sa.Column('trial_start_date', sa.DateTime(), nullable=True))
    
    if 'trial_end_date' not in user_columns:
        print("Adding trial_end_date column to User table...")
        op.add_column('user', sa.Column('trial_end_date', sa.DateTime(), nullable=True))
    
    if 'trial_converted' not in user_columns:
        print("Adding trial_converted column to User table...")
        op.add_column('user', sa.Column('trial_converted', sa.Boolean(), nullable=True))
    
    if 'daily_flow_runs' not in user_columns:
        print("Adding daily_flow_runs column to User table...")
        op.add_column('user', sa.Column('daily_flow_runs', sa.Integer(), nullable=True))
    
    if 'daily_flow_runs_reset_at' not in user_columns:
        print("Adding daily_flow_runs_reset_at column to User table...")
        op.add_column('user', sa.Column('daily_flow_runs_reset_at', sa.DateTime(), nullable=True))
    
    if 'daily_kb_queries' not in user_columns:
        print("Adding daily_kb_queries column to User table...")
        op.add_column('user', sa.Column('daily_kb_queries', sa.Integer(), nullable=True))
    
    if 'daily_kb_queries_reset_at' not in user_columns:
        print("Adding daily_kb_queries_reset_at column to User table...")
        op.add_column('user', sa.Column('daily_kb_queries_reset_at', sa.DateTime(), nullable=True))
    
    # Update non-null values with defaults
    if conn.dialect.name == 'sqlite':
        print("Setting default values for newly added columns...")
        op.execute("UPDATE user SET credits_balance = 0.0 WHERE credits_balance IS NULL")
        op.execute("UPDATE user SET billing_day = 1 WHERE billing_day IS NULL")
        op.execute("UPDATE user SET subscription_status = 'trial' WHERE subscription_status IS NULL")
        op.execute("UPDATE user SET trial_converted = 0 WHERE trial_converted IS NULL")
        op.execute("UPDATE user SET daily_flow_runs = 0 WHERE daily_flow_runs IS NULL")
        op.execute("UPDATE user SET daily_kb_queries = 0 WHERE daily_kb_queries IS NULL")
    
    print("Migration complete!")


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # Drop foreign keys first
    for fk_name in [
        "fk_invoice_billing_period_id",
        "fk_invoice_user_id",
        "fk_daily_usage_summary_user_id",
        "fk_kbusagedetail_usage_record_id",
        "fk_toolusagedetail_usage_record_id",
        "fk_tokenusagedetail_usage_record_id",
        "fk_usagerecord_billing_period_id",
        "fk_usagerecord_flow_id",
        "fk_usagerecord_user_id",
        "fk_billingperiod_subscription_plan_id",
        "fk_billingperiod_user_id",
        "fk_user_subscription_plan_id"
    ]:
        try:
            op.drop_constraint(fk_name, table_name=fk_name.split("_")[1], type_="foreignkey")
        except Exception:
            # Constraint might not exist
            pass
    
    # Drop tables in reverse order of creation (to respect foreign key constraints)
    for table in ['invoice', 'daily_usage_summary', 'kbusagedetail', 'toolusagedetail', 
                 'tokenusagedetail', 'usagerecord', 'billingperiod']:
        if table in inspector.get_table_names():
            print(f"Dropping {table} table...")
            op.drop_table(table)
    
    # Check user columns and drop them if they exist
    user_columns = [column['name'] for column in inspector.get_columns('user')]
    
    billing_columns = [
        'daily_kb_queries_reset_at', 'daily_kb_queries', 'daily_flow_runs_reset_at',
        'daily_flow_runs', 'trial_converted', 'trial_end_date', 'trial_start_date',
        'subscription_end_date', 'subscription_start_date', 'subscription_status',
        'subscription_plan_id', 'billing_day', 'credits_balance'
    ]
    
    for column in billing_columns:
        if column in user_columns:
            print(f"Dropping {column} column from User table...")
            op.drop_column('user', column)
    
    # Drop the subscription plan table last (because it has FKs pointing to it)
    if 'subscriptionplan' in inspector.get_table_names():
        print("Dropping subscriptionplan table...")
        op.drop_table('subscriptionplan')
    
    print("Downgrade complete!")
