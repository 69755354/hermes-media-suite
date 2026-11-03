-- Additive multi-device migration.
-- Run only through scripts/migrate_multidevice.py --apply on an approved copy.
-- No rows are deleted or rewritten. The single-active partial index is removed
-- because a customer may now own several concurrently active devices.
DROP INDEX IF EXISTS one_active_customer_device;

ALTER TABLE customer_devices ADD COLUMN label TEXT;
ALTER TABLE customer_devices ADD COLUMN machine_code TEXT;
ALTER TABLE customer_devices ADD COLUMN created REAL;
ALTER TABLE customer_devices ADD COLUMN updated REAL;
ALTER TABLE customer_devices ADD COLUMN token_issued_at REAL;
ALTER TABLE customer_devices ADD COLUMN activated_at REAL;
ALTER TABLE customer_devices ADD COLUMN isolated_at REAL;
ALTER TABLE customer_devices ADD COLUMN retired_at REAL;
ALTER TABLE customer_devices ADD COLUMN notes TEXT;

ALTER TABLE commands ADD COLUMN material_sha256 TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS customer_devices_token_hash_unique
  ON customer_devices(token_hash);
CREATE UNIQUE INDEX IF NOT EXISTS customer_devices_machine_code_unique
  ON customer_devices(customer_id, machine_code)
  WHERE machine_code IS NOT NULL AND machine_code != '';
CREATE INDEX IF NOT EXISTS customer_devices_customer_status
  ON customer_devices(customer_id, status, last_seen);
CREATE INDEX IF NOT EXISTS commands_device_status
  ON commands(customer_id, device_id, status, created);
CREATE INDEX IF NOT EXISTS remote_ops_device_status
  ON remote_ops(customer_id, device_id, status, created);

CREATE TABLE IF NOT EXISTS device_material_claims (
  customer_id TEXT NOT NULL,
  material_sha256 TEXT NOT NULL CHECK(length(material_sha256)=64),
  material_id TEXT,
  device_id TEXT NOT NULL,
  command_id TEXT,
  status TEXT NOT NULL DEFAULT 'claimed'
    CHECK(status IN ('claimed','published','released')),
  created REAL NOT NULL,
  updated REAL NOT NULL,
  PRIMARY KEY(customer_id, material_sha256),
  FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
  FOREIGN KEY(device_id) REFERENCES customer_devices(device_id)
);
CREATE INDEX IF NOT EXISTS device_material_claims_device
  ON device_material_claims(customer_id, device_id, status);

CREATE TABLE IF NOT EXISTS device_events (
  id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  device_id TEXT,
  event TEXT NOT NULL,
  detail TEXT,
  created REAL NOT NULL,
  FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
);
CREATE INDEX IF NOT EXISTS device_events_customer
  ON device_events(customer_id, created);
