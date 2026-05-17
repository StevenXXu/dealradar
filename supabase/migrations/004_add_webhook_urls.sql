-- 004_add_webhook_urls.sql

-- Add webhook URL columns to tenants table for alerting
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS slack_webhook_url TEXT;
ALTER TABLE tenants ADD COLUMN IF NOT EXISTS custom_webhook_url TEXT;
