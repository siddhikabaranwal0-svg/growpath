-- ============================================================================
-- Adaptive Path Planner Schema (Additive to skill_schema.sql)
-- ============================================================================

-- 1. Topic Prerequisites: directed edges in the knowledge DAG
-- "prerequisite_topic_id must be learned before topic_id"
create table if not exists public.topic_prerequisites (
  topic_id uuid references public.topics(id) on delete cascade not null,
  prerequisite_topic_id uuid references public.topics(id) on delete cascade not null,
  created_at timestamp with time zone default now() not null,
  primary key (topic_id, prerequisite_topic_id),
  check (topic_id != prerequisite_topic_id)  -- no self-loops
);

-- 2. Learning Paths: persisted generated roadmaps per user
create table if not exists public.learning_paths (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete cascade not null,
  path_data jsonb not null,             -- ordered array of {topic_id, topic_name, proficiency, status, prerequisites_met}
  target_topics uuid[] not null,        -- the goal topics the path leads to
  mastery_threshold integer default 70 not null,
  total_steps integer not null,
  completed_steps integer default 0 not null,
  created_at timestamp with time zone default now() not null,
  updated_at timestamp with time zone default now() not null
);

-- ============================================================================
-- Row-Level Security (RLS)
-- ============================================================================
alter table public.topic_prerequisites enable row level security;
alter table public.learning_paths enable row level security;

-- Topic Prerequisites: publicly readable
drop policy if exists "Topic prerequisites are viewable by anyone" on public.topic_prerequisites;
create policy "Topic prerequisites are viewable by anyone" on public.topic_prerequisites
  for select using (true);

drop policy if exists "Authenticated users can manage topic prerequisites" on public.topic_prerequisites;
create policy "Authenticated users can manage topic prerequisites" on public.topic_prerequisites
  for all using (auth.uid() is not null);

-- Learning Paths: users can only see/manage their own
drop policy if exists "Users can view their own learning paths" on public.learning_paths;
create policy "Users can view their own learning paths" on public.learning_paths
  for select using (auth.uid() = user_id);

drop policy if exists "Users can manage their own learning paths" on public.learning_paths;
create policy "Users can manage their own learning paths" on public.learning_paths
  for all using (auth.uid() = user_id);

-- ============================================================================
-- Performance Indexes
-- ============================================================================
create index if not exists topic_prereqs_topic_id_idx on public.topic_prerequisites(topic_id);
create index if not exists topic_prereqs_prereq_id_idx on public.topic_prerequisites(prerequisite_topic_id);
create index if not exists learning_paths_user_id_idx on public.learning_paths(user_id);
