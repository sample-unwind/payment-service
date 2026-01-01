-- =============================================================================
-- Payment Service RLS (Row-Level Security) Setup
-- =============================================================================
-- This migration enables RLS on the payments table for multitenancy support.
-- 
-- GLOBAL RULE: app.tenant_id MUST be set before any database operation.
-- Default tenant ID: 00000000-0000-0000-0000-000000000001
--
-- RLS ensures that:
-- 1. Each tenant can only see/modify their own payments
-- 2. Operations without app.tenant_id set are BLOCKED (returns empty/fails)
-- 3. GDPR compliance through database-level isolation

-- =============================================================================
-- Enable RLS on payments table
-- =============================================================================

ALTER TABLE payments ENABLE ROW LEVEL SECURITY;

-- FORCE RLS for table owner (superuser bypass prevention)
-- This ensures even the table owner must comply with RLS policies
ALTER TABLE payments FORCE ROW LEVEL SECURITY;

-- =============================================================================
-- Drop existing policies (idempotent)
-- =============================================================================

DROP POLICY IF EXISTS tenant_isolation_policy ON payments;
DROP POLICY IF EXISTS tenant_insert_policy ON payments;

-- =============================================================================
-- RLS Policies
-- =============================================================================

-- Policy for SELECT, UPDATE, DELETE operations
-- Requires app.tenant_id to be set and match the row's tenant_id
CREATE POLICY tenant_isolation_policy ON payments
    FOR ALL
    USING (
        -- Block access if app.tenant_id is not set or empty
        CASE
            WHEN COALESCE(current_setting('app.tenant_id', true), '') = '' THEN false
            ELSE tenant_id = current_setting('app.tenant_id', true)::uuid
        END
    )
    WITH CHECK (
        -- Block writes if app.tenant_id is not set or empty
        CASE
            WHEN COALESCE(current_setting('app.tenant_id', true), '') = '' THEN false
            ELSE tenant_id = current_setting('app.tenant_id', true)::uuid
        END
    );

-- =============================================================================
-- Verification Query
-- =============================================================================
-- Run this to verify RLS is enabled:
-- SELECT relname, relrowsecurity, relforcerowsecurity 
-- FROM pg_class 
-- WHERE relname = 'payments';
--
-- Expected output:
--  relname  | relrowsecurity | relforcerowsecurity
-- ----------+----------------+---------------------
--  payments | t              | t
