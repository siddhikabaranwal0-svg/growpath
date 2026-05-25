-- ============================================================================
-- Skill Mapping Engine Schema (Additive to schema.sql)
-- ============================================================================

-- 1. Topics Table: skill/knowledge areas that questions map to
create table if not exists public.topics (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text unique not null,
  description text,
  parent_id uuid references public.topics(id) on delete set null,
  created_at timestamp with time zone default now() not null
);

-- 2. Question-Topics Junction: many-to-many link
create table if not exists public.question_topics (
  question_id uuid references public.questions(id) on delete cascade not null,
  topic_id uuid references public.topics(id) on delete cascade not null,
  primary key (question_id, topic_id)
);

-- 3. Skill Profiles: persisted ML output per user per topic
create table if not exists public.skill_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete cascade not null,
  topic_id uuid references public.topics(id) on delete cascade not null,
  proficiency_score float default 0.0 not null check (proficiency_score >= 0 and proficiency_score <= 100),
  confidence text default 'low' not null check (confidence in ('low', 'medium', 'high')),
  trend text default 'stable' not null check (trend in ('improving', 'declining', 'stable')),
  responses_count integer default 0 not null,
  last_computed_at timestamp with time zone default now() not null,
  unique (user_id, topic_id)
);

-- ============================================================================
-- Row-Level Security (RLS)
-- ============================================================================
alter table public.topics enable row level security;
alter table public.question_topics enable row level security;
alter table public.skill_profiles enable row level security;

-- Topics: publicly readable
drop policy if exists "Topics are viewable by anyone" on public.topics;
create policy "Topics are viewable by anyone" on public.topics
  for select using (true);

drop policy if exists "Authenticated users can manage topics" on public.topics;
create policy "Authenticated users can manage topics" on public.topics
  for all using (auth.uid() is not null);

-- Question-Topics: publicly readable
drop policy if exists "Question topics are viewable by anyone" on public.question_topics;
create policy "Question topics are viewable by anyone" on public.question_topics
  for select using (true);

drop policy if exists "Authenticated users can manage question topics" on public.question_topics;
create policy "Authenticated users can manage question topics" on public.question_topics
  for all using (auth.uid() is not null);

-- Skill Profiles: users can only see their own
drop policy if exists "Users can view their own skill profiles" on public.skill_profiles;
create policy "Users can view their own skill profiles" on public.skill_profiles
  for select using (auth.uid() = user_id);

drop policy if exists "Users can manage their own skill profiles" on public.skill_profiles;
create policy "Users can manage their own skill profiles" on public.skill_profiles
  for all using (auth.uid() = user_id);

-- ============================================================================
-- Performance Indexes
-- ============================================================================
create index if not exists topics_slug_idx on public.topics(slug);
create index if not exists topics_parent_id_idx on public.topics(parent_id);
create index if not exists question_topics_topic_id_idx on public.question_topics(topic_id);
create index if not exists skill_profiles_user_id_idx on public.skill_profiles(user_id);
create index if not exists skill_profiles_topic_id_idx on public.skill_profiles(topic_id);
create index if not exists skill_profiles_user_topic_idx on public.skill_profiles(user_id, topic_id);
