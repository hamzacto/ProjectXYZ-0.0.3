"""add_billing_tables

Revision ID: 0cb2d40f2398
Revises: 92192ef49411
Create Date: 2025-04-08 01:31:39.005479

"""
from typing import Sequence, Union
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.engine.reflection import Inspector
from langflow.utils import migration
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base


# revision identifiers, used by Alembic.
revision: str = '0cb2d40f2398'
down_revision: Union[str, None] = '92192ef49411'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    
    # Check if the tables already exist
    if "subscriptionplan" not in inspector.get_table_names():
        print("Creating SubscriptionPlan table...")
        op.create_table(
            'subscriptionplan',
            sa.Column('id', sa.Uuid(), primary_key=True, default=uuid.uuid4),
            sa.Column('name', sa.String(), nullable=False, index=True),
            sa.Column('description', sa.String(), nullable=True),
            sa.Column('monthly_quota_credits', sa.Float(), nullable=False, default=0.0),
            sa.Column('max_flows', sa.Integer(), nullable=False, default=0),
            sa.Column('max_flow_runs_per_day', sa.Integer(), nullable=False, default=0),
            sa.Column('max_concurrent_flows', sa.Integer(), nullable=False, default=1),
            sa.Column('max_kb_storage_mb', sa.Integer(), nullable=False, default=0),
            sa.Column('max_kbs_per_user', sa.Integer(), nullable=False, default=0),
            sa.Column('max_kb_entries_per_kb', sa.Integer(), nullable=False, default=0),
            sa.Column('max_tokens_per_kb_entry', sa.Integer(), nullable=False, default=0),
            sa.Column('max_kb_queries_per_day', sa.Integer(), nullable=False, default=0),
            sa.Column('allowed_models', sa.JSON(), nullable=False, default=list),
            sa.Column('price_monthly_usd', sa.Float(), nullable=False, default=0.0),
            sa.Column('price_yearly_usd', sa.Float(), nullable=False, default=0.0),
            sa.Column('features', sa.JSON(), nullable=False, default=dict),
            sa.Column('allowed_premium_tools', sa.JSON(), nullable=False, default=list),
            sa.Column('overage_price_per_credit', sa.Float(), nullable=False, default=0.0),
            sa.Column('allows_overage', sa.Boolean(), nullable=False, default=False),
            sa.Column('trial_days', sa.Integer(), nullable=False, default=0),
            sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
            sa.Column('created_at', sa.DateTime(), nullable=False, default=lambda: datetime.now(timezone.utc)),
        )
    
    # Check if billingperiod table needs to be created
    if "billingperiod" not in inspector.get_table_names():
        print("Creating BillingPeriod table...")
        op.create_table(
            'billingperiod',
            sa.Column('id', sa.Uuid(), primary_key=True, default=uuid.uuid4),
            sa.Column('user_id', sa.Uuid(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('start_date', sa.DateTime(), nullable=False),
            sa.Column('end_date', sa.DateTime(), nullable=False),
            sa.Column('subscription_plan_id', sa.Uuid(), sa.ForeignKey('subscriptionplan.id'), nullable=True, index=True),
            sa.Column('status', sa.String(), nullable=False, default='active'),
            sa.Column('quota_override', sa.Float(), nullable=True),
            sa.Column('quota_used', sa.Float(), nullable=False, default=0.0),
            sa.Column('quota_remaining', sa.Float(), nullable=False, default=0.0),
            sa.Column('overage_credits', sa.Float(), nullable=False, default=0.0),
            sa.Column('overage_cost', sa.Float(), nullable=False, default=0.0),
            sa.Column('is_plan_change', sa.Boolean(), nullable=False, default=False),
            sa.Column('previous_plan_id', sa.Uuid(), nullable=True),
            sa.Column('invoiced', sa.Boolean(), nullable=False, default=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, default=lambda: datetime.now(timezone.utc)),
        )
    
    # Check if usagerecord table needs to be created
    if "usagerecord" not in inspector.get_table_names():
        print("Creating UsageRecord table...")
        op.create_table(
            'usagerecord',
            sa.Column('id', sa.Uuid(), primary_key=True, default=uuid.uuid4),
            sa.Column('user_id', sa.Uuid(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('flow_id', sa.Uuid(), sa.ForeignKey('flow.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('session_id', sa.String(), nullable=False, index=True),
            sa.Column('fixed_cost', sa.Float(), nullable=False, default=0.0),
            sa.Column('llm_cost', sa.Float(), nullable=False, default=0.0),
            sa.Column('tools_cost', sa.Float(), nullable=False, default=0.0),
            sa.Column('kb_cost', sa.Float(), nullable=False, default=0.0),
            sa.Column('total_cost', sa.Float(), nullable=False, default=0.0),
            sa.Column('created_at', sa.DateTime(), nullable=False, default=lambda: datetime.now(timezone.utc)),
            sa.Column('billing_period_id', sa.Uuid(), sa.ForeignKey('billingperiod.id'), nullable=True),
        )
    
    # Check if tokenusagedetail table needs to be created
    if "tokenusagedetail" not in inspector.get_table_names():
        print("Creating TokenUsageDetail table...")
        op.create_table(
            'tokenusagedetail',
            sa.Column('id', sa.Uuid(), primary_key=True, default=uuid.uuid4),
            sa.Column('usage_record_id', sa.Uuid(), sa.ForeignKey('usagerecord.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('model_name', sa.String(), nullable=False),
            sa.Column('input_tokens', sa.Integer(), nullable=False),
            sa.Column('output_tokens', sa.Integer(), nullable=False),
            sa.Column('cost', sa.Float(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, default=lambda: datetime.now(timezone.utc)),
        )
    
    # Check if toolusagedetail table needs to be created
    if "toolusagedetail" not in inspector.get_table_names():
        print("Creating ToolUsageDetail table...")
        op.create_table(
            'toolusagedetail',
            sa.Column('id', sa.Uuid(), primary_key=True, default=uuid.uuid4),
            sa.Column('usage_record_id', sa.Uuid(), sa.ForeignKey('usagerecord.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('tool_name', sa.String(), nullable=False),
            sa.Column('count', sa.Integer(), nullable=False, default=1),
            sa.Column('cost', sa.Float(), nullable=False),
            sa.Column('is_premium', sa.Boolean(), nullable=False, default=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, default=lambda: datetime.now(timezone.utc)),
        )
    
    # Check if kbusagedetail table needs to be created
    if "kbusagedetail" not in inspector.get_table_names():
        print("Creating KBUsageDetail table...")
        op.create_table(
            'kbusagedetail',
            sa.Column('id', sa.Uuid(), primary_key=True, default=uuid.uuid4),
            sa.Column('usage_record_id', sa.Uuid(), sa.ForeignKey('usagerecord.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('kb_name', sa.String(), nullable=False),
            sa.Column('count', sa.Integer(), nullable=False, default=1),
            sa.Column('cost', sa.Float(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, default=lambda: datetime.now(timezone.utc)),
        )
    
    # Check if dailyusagesummary table needs to be created
    if "daily_usage_summary" not in inspector.get_table_names():
        print("Creating DailyUsageSummary table...")
        op.create_table(
            'daily_usage_summary',
            sa.Column('id', sa.Uuid(), primary_key=True, default=uuid.uuid4),
            sa.Column('user_id', sa.Uuid(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('date', sa.DateTime(), nullable=False, index=True),
            sa.Column('flow_runs', sa.Integer(), nullable=False, default=0),
            sa.Column('kb_queries', sa.Integer(), nullable=False, default=0),
            sa.Column('api_calls', sa.Integer(), nullable=False, default=0),
            sa.Column('tokens_used', sa.Integer(), nullable=False, default=0),
            sa.Column('total_cost', sa.Float(), nullable=False, default=0.0),
        )
    
    # Check if invoice table needs to be created
    if "invoice" not in inspector.get_table_names():
        print("Creating Invoice table...")
        op.create_table(
            'invoice',
            sa.Column('id', sa.Uuid(), primary_key=True, default=uuid.uuid4),
            sa.Column('user_id', sa.Uuid(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('billing_period_id', sa.Uuid(), sa.ForeignKey('billingperiod.id'), nullable=False),
            sa.Column('amount', sa.Float(), nullable=False),
            sa.Column('status', sa.String(), nullable=False, default='pending'),
            sa.Column('created_at', sa.DateTime(), nullable=False, default=lambda: datetime.now(timezone.utc)),
            sa.Column('paid_at', sa.DateTime(), nullable=True),
        )
    
    # Check if user table already has the subscription_plan_id column
    user_columns = [column['name'] for column in inspector.get_columns('user')]
    
    # Add new columns to the user table if they don't exist
    # For SQLite compatibility, all columns must be nullable when added with ALTER TABLE
    if 'credits_balance' not in user_columns:
        print("Adding credits_balance column to User table...")
        op.add_column('user', sa.Column('credits_balance', sa.Float(), nullable=True))
    
    if 'billing_day' not in user_columns:
        print("Adding billing_day column to User table...")
        op.add_column('user', sa.Column('billing_day', sa.Integer(), nullable=True))
    
    if 'subscription_plan_id' not in user_columns:
        print("Adding subscription_plan_id column to User table...")
        op.add_column('user', sa.Column('subscription_plan_id', sa.Uuid(), 
                                       sa.ForeignKey('subscriptionplan.id'), 
                                       nullable=True, index=True))
    
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
