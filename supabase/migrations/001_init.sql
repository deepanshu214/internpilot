-- Portable between Supabase Postgres and local SQLite (the worker and dashboard run it on startup).
-- JSON fields are stored as text, embeddings are JSON arrays (cosine is computed in Python).
-- Timestamps are ISO-8601 UTC strings.
create table if not exists jobs (
  id              text primary key,
  source          text not null,
  company         text not null,
  title           text not null,
  location        text,
  remote          integer default 0,
  url             text,
  jd_text         text,
  posted_at       text,
  first_seen      text not null,
  embedding       text,
  extra           text,              -- json: deadline, stipend, ...
  company_domain  text
);

create table if not exists matches (
  job_id          text primary key references jobs(id) on delete cascade,
  score           integer not null,
  reasons         text,              -- json list
  missing_skills  text,              -- json list
  method          text,              -- heuristic | ollama | groq
  status          text not null default 'new',  -- new|shortlisted|tailored|applied|oa|interview|offer|rejected|skipped
  notified        integer not null default 0,
  notes           text,
  applied_at      text,
  deadline        text,
  updated_at      text
);

create table if not exists resumes (
  id            text primary key,
  job_id        text references jobs(id) on delete cascade,
  version       integer default 1,
  pdf_b64       text,                -- the rendered PDF (small, ~50 KB) so the cloud dashboard can serve it
  source_typ    text,                -- typst source, for debugging
  selection     text,                -- json: chosen projects/bullets/skills
  keywords      text,                -- json: JD keywords mirrored
  diff_summary  text,
  created_at    text
);

create table if not exists contacts (
  id                   text primary key,
  company              text not null,
  domain               text,
  job_id               text,
  name                 text,
  title                text,
  email                text,
  source               text,         -- hunter | pattern | manual
  confidence           integer,
  linkedin_search_url  text,
  created_at           text
);

create table if not exists outreach (
  id                text primary key,
  contact_id        text references contacts(id),
  job_id            text references jobs(id),
  kind              text default 'cold',     -- cold | followup | referral
  parent_id         text,                    -- followup → original outreach
  variant           text,                    -- A/B template label
  project_pitched   text,
  subject           text,
  body              text,
  to_email          text,
  resume_id         text,
  status            text default 'draft',    -- draft|approved|sent|replied|bounced|skipped
  gmail_message_id  text,
  gmail_thread_id   text,
  sent_at           text,
  followup_due      text,
  created_at        text,
  updated_at        text
);

-- Work requested by the dashboard / Telegram, executed by the worker on the Mac.
create table if not exists tasks (
  id           text primary key,
  kind         text not null,       -- discover|tailor|find_contacts|draft_outreach|send_outreach|autofill|prep|cover_letter|referral
  job_id       text,
  payload      text,                -- json
  status       text not null default 'queued',  -- queued|running|done|failed
  result       text,                -- json
  error        text,
  created_at   text not null,
  started_at   text,
  finished_at  text
);

-- Generated text: interview prep packs, cover letters, "why us" answers, referral messages, weekly reports.
create table if not exists documents (
  id          text primary key,
  job_id      text,
  kind        text not null,        -- prep | cover_letter | referral | weekly_report
  title       text,
  content     text,                 -- markdown
  created_at  text
);

create table if not exists companies (
  name        text primary key,     -- normalized company name
  domain      text,
  brief       text,                 -- what they build, from their site
  fetched_at  text
);

create table if not exists kv (
  key    text primary key,
  value  text
);

create table if not exists events (
  id      text primary key,
  ts      text not null,
  kind    text not null,
  job_id  text,
  detail  text
);

create index if not exists matches_score_idx on matches (score desc);
create index if not exists matches_status_idx on matches (status);
create index if not exists tasks_status_idx on tasks (status, created_at);
create index if not exists outreach_status_idx on outreach (status);
create index if not exists events_ts_idx on events (ts desc)
