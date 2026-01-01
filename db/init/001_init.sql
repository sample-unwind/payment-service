-- =============================================================================
-- Payment Service Database Schema
-- =============================================================================
-- This script initializes the database schema for the payment service.
-- No RLS needed - payments are service-internal, accessed only by payment-service.

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- Enum Types
-- =============================================================================

-- Payment status enum
DO $$ BEGIN
    CREATE TYPE payment_status AS ENUM (
        'PENDING',
        'COMPLETED',
        'FAILED',
        'REFUNDED'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- =============================================================================
-- Payments Table
-- =============================================================================
-- Stores all payment transactions.

CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id UUID NOT NULL,
    user_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    amount DECIMAL(10, 2) NOT NULL CHECK (amount > 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    transaction_id UUID UNIQUE DEFAULT gen_random_uuid(),
    error_message TEXT,
    refund_id UUID,
    refund_amount DECIMAL(10, 2),
    refund_reason TEXT,
    refunded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_payments_reservation_id ON payments(reservation_id);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_tenant_id ON payments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_payments_transaction_id ON payments(transaction_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments(created_at);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_payments_reservation_status ON payments(reservation_id, status);
CREATE INDEX IF NOT EXISTS idx_payments_user_status ON payments(user_id, status);

-- =============================================================================
-- Helper Functions
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at on payments
DROP TRIGGER IF EXISTS update_payments_updated_at ON payments;
CREATE TRIGGER update_payments_updated_at
    BEFORE UPDATE ON payments
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- Permissions
-- =============================================================================
-- Grant permissions to payment_service_user (run as superuser)

-- Note: Run these commands after creating the user:
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO payment_service_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO payment_service_user;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO payment_service_user;
