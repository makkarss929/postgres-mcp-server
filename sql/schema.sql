-- Sample schema for a voice-AI call platform, used by the campaign_summary tool.
CREATE TABLE IF NOT EXISTS campaigns (
  id          SERIAL PRIMARY KEY,
  name        TEXT NOT NULL,
  client      TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS calls (
  id            BIGSERIAL PRIMARY KEY,
  campaign_id   INT REFERENCES campaigns(id),
  started_at    TIMESTAMPTZ NOT NULL,
  status        TEXT CHECK (status IN ('answered','no_answer','voicemail','failed')),
  outcome       TEXT CHECK (outcome IN ('booked','qualified','not_interested','callback','none')),
  duration_sec  INT,
  latency_ms    INT,          -- avg agent response latency
  cost_usd      NUMERIC(8,4),
  transcript    TEXT
);

-- Read-only role the MCP server should connect with
CREATE ROLE readonly_user LOGIN PASSWORD 'password';
GRANT CONNECT ON DATABASE nextdialog TO readonly_user;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;
