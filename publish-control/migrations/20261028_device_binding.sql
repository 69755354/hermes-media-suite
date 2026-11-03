-- Additive migration. Execute ONLY via verify_device_binding.py --apply on an approved DB.
ALTER TABLE customers ADD COLUMN default_title TEXT;
ALTER TABLE customers ADD COLUMN default_topics TEXT;
ALTER TABLE customers ADD COLUMN policy_version TEXT;
ALTER TABLE customers ADD COLUMN active_device_id TEXT;
ALTER TABLE customers ADD COLUMN binding_epoch INTEGER NOT NULL DEFAULT 0 CHECK(binding_epoch >= 0);
ALTER TABLE customers ADD COLUMN dispatch_paused INTEGER NOT NULL DEFAULT 0 CHECK(dispatch_paused IN (0,1));
ALTER TABLE customers ADD COLUMN device_binding_enabled INTEGER NOT NULL DEFAULT 0 CHECK(device_binding_enabled IN (0,1));
ALTER TABLE commands ADD COLUMN device_id TEXT;
ALTER TABLE commands ADD COLUMN binding_epoch INTEGER;
ALTER TABLE remote_ops ADD COLUMN device_id TEXT;
ALTER TABLE remote_ops ADD COLUMN binding_epoch INTEGER;
CREATE TABLE IF NOT EXISTS customer_devices (
 device_id TEXT PRIMARY KEY,
 customer_id TEXT NOT NULL REFERENCES customers(customer_id),
 token_hash TEXT NOT NULL CHECK(length(token_hash)=64),
 status TEXT NOT NULL CHECK(status IN ('active','isolated','retired')),
 binding_epoch INTEGER NOT NULL CHECK(binding_epoch >= 0),
 last_seen REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_customer_device ON customer_devices(customer_id) WHERE status='active';
