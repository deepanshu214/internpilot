-- Run only on Postgres (Supabase). Row level security with no policies: Supabase's public REST API (anon /
-- authenticated keys) can't read or write these tables. The worker and dashboard connect directly as the
-- database owner, which bypasses RLS.
alter table jobs enable row level security;
alter table matches enable row level security;
alter table resumes enable row level security;
alter table contacts enable row level security;
alter table outreach enable row level security;
alter table tasks enable row level security;
alter table documents enable row level security;
alter table companies enable row level security;
alter table kv enable row level security;
alter table events enable row level security
