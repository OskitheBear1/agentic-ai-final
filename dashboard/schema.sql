-- Supabase Postgres schema for the dashboard. Loaded by `python -m pipeline.export_db --run full`.
-- Everything here is derived from saved pipeline outputs; the dashboard never calls a model.

drop table if exists extra_claims, claims, memo, reviews, issues, run_meta cascade;

-- Key/value run facts: coverage counts, totals, cost, verifier and golden-set agreement.
create table run_meta (
  key   text primary key,
  value jsonb not null
);

-- One row per issue (taxonomy subtopic), straight from artifacts/<run>/rank/aggregates.csv + group/issues.json.
create table issues (
  issue_id             text primary key,
  rank                 integer not null,
  topic                text not null,
  name                 text not null,
  description          text not null,
  complaint_count      integer not null,
  severity_sum         integer not null,
  mean_severity        numeric not null,
  priority_score       integer not null,
  share_of_complaints  numeric not null,
  cancellation_count   integer not null,
  severity_4plus_count integer not null,
  needs_review_count   integer not null,
  mean_sentiment       numeric not null,
  severity_histogram   jsonb not null,
  complaints_by_month  jsonb not null
);

-- One row per classified review (the 100,000-row declared scope), with source fields and labels.
create table reviews (
  review_id        text primary key,
  scope_rank       integer not null,
  review_text      text not null,
  review_rating    text,
  review_timestamp text,
  app_version      text,
  topic            text not null,
  intent           text not null,
  severity         integer not null,
  sentiment        numeric not null,
  evidence_quote   text not null,
  entities         jsonb not null,
  needs_review     boolean not null,
  cache_source_id  text,
  issue_id         text references issues(issue_id)
);
create index reviews_issue_idx on reviews (issue_id, severity desc);

-- The AI-generated memo (Claude Sonnet) and its machine-checked claims.
create table memo (
  id                   integer primary key,
  recommended_issue_id text not null references issues(issue_id),
  markdown             text not null,
  cited_reviews        jsonb not null,
  model                text not null
);

create table claims (
  claim_id text primary key,
  issue_id text not null references issues(issue_id),
  metric   text not null,
  value    text not null
);

-- Memo numbers outside the checker's four metrics (cancellation counts, shares, period shares), with the numerator
-- and denominator they were computed from (artifacts/<run>/memo/extra_claims.csv, validated by code against the pack).
create table extra_claims (
  claim_id    text primary key,
  issue_id    text not null references issues(issue_id),
  metric      text not null,
  period      text not null,
  value       text not null,
  numerator   text not null,
  denominator text not null,
  source      text not null
);

-- Row level security on, with no policies: Supabase's public REST API (anon key) can read nothing.
-- Only our backend, connecting server-side with the database URL, reads these tables.
alter table run_meta enable row level security;
alter table issues   enable row level security;
alter table reviews  enable row level security;
alter table memo     enable row level security;
alter table claims   enable row level security;
alter table extra_claims enable row level security;
