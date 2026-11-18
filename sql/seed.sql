INSERT INTO campaigns (name, client) VALUES
  ('HVAC Winter Tune-up', 'ComfortAir Ltd'),
  ('Dental Recall Q4', 'BrightSmile Clinic');

INSERT INTO calls (campaign_id, started_at, status, outcome, duration_sec, latency_ms, cost_usd)
SELECT
  1 + (g % 2),
  NOW() - (g || ' hours')::interval,
  (ARRAY['answered','answered','no_answer','voicemail'])[1 + g % 4],
  (ARRAY['booked','qualified','not_interested','none'])[1 + g % 4],
  30 + (g * 7) % 240,
  600 + (g * 13) % 900,
  0.02 + ((g * 3) % 10) / 100.0
FROM generate_series(1, 120) AS g;
