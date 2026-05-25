-- ============================================================================
-- Content Recommendation System Schema (Additive to skill_schema.sql + path_schema.sql)
-- ============================================================================

-- 1. Learning Resources: the content catalog
create table if not exists public.learning_resources (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  description text,
  resource_type text not null check (resource_type in ('article', 'video', 'exercise', 'external_link', 'quiz')),
  url text,
  difficulty_level integer not null check (difficulty_level >= 1 and difficulty_level <= 5),
  estimated_minutes integer check (estimated_minutes > 0),
  quality_score float default 0.5 not null check (quality_score >= 0.0 and quality_score <= 1.0),
  metadata jsonb default '{}'::jsonb not null,
  created_at timestamp with time zone default now() not null
);

-- 2. Resource-Topics Junction: many-to-many link between resources and topics
create table if not exists public.resource_topics (
  resource_id uuid references public.learning_resources(id) on delete cascade not null,
  topic_id uuid references public.topics(id) on delete cascade not null,
  primary key (resource_id, topic_id)
);

-- 3. User Resource Interactions: tracks what a user has viewed/completed/skipped
create table if not exists public.user_resource_interactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete cascade not null,
  resource_id uuid references public.learning_resources(id) on delete cascade not null,
  interaction_type text not null check (interaction_type in ('viewed', 'completed', 'skipped', 'bookmarked')),
  rating integer check (rating is null or (rating >= 1 and rating <= 5)),
  interacted_at timestamp with time zone default now() not null
);

-- 4. Recommendation Logs: audit trail for recommendations served
create table if not exists public.recommendation_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete cascade not null,
  resource_id uuid references public.learning_resources(id) on delete cascade not null,
  score float not null,
  rank integer not null check (rank >= 1),
  score_breakdown jsonb not null default '{}'::jsonb,
  context jsonb default '{}'::jsonb,
  created_at timestamp with time zone default now() not null
);

-- ============================================================================
-- Row-Level Security (RLS)
-- ============================================================================
alter table public.learning_resources enable row level security;
alter table public.resource_topics enable row level security;
alter table public.user_resource_interactions enable row level security;
alter table public.recommendation_logs enable row level security;

-- Learning Resources: publicly readable
drop policy if exists "Learning resources are viewable by anyone" on public.learning_resources;
create policy "Learning resources are viewable by anyone" on public.learning_resources
  for select using (true);

drop policy if exists "Authenticated users can manage learning resources" on public.learning_resources;
create policy "Authenticated users can manage learning resources" on public.learning_resources
  for all using (auth.uid() is not null);

-- Resource Topics: publicly readable
drop policy if exists "Resource topics are viewable by anyone" on public.resource_topics;
create policy "Resource topics are viewable by anyone" on public.resource_topics
  for select using (true);

drop policy if exists "Authenticated users can manage resource topics" on public.resource_topics;
create policy "Authenticated users can manage resource topics" on public.resource_topics
  for all using (auth.uid() is not null);

-- User Resource Interactions: users can only see/manage their own
drop policy if exists "Users can view their own resource interactions" on public.user_resource_interactions;
create policy "Users can view their own resource interactions" on public.user_resource_interactions
  for select using (auth.uid() = user_id);

drop policy if exists "Users can manage their own resource interactions" on public.user_resource_interactions;
create policy "Users can manage their own resource interactions" on public.user_resource_interactions
  for all using (auth.uid() = user_id);

-- Recommendation Logs: users can only view their own
drop policy if exists "Users can view their own recommendation logs" on public.recommendation_logs;
create policy "Users can view their own recommendation logs" on public.recommendation_logs
  for select using (auth.uid() = user_id);

drop policy if exists "Users can manage their own recommendation logs" on public.recommendation_logs;
create policy "Users can manage their own recommendation logs" on public.recommendation_logs
  for all using (auth.uid() = user_id);

-- ============================================================================
-- Performance Indexes
-- ============================================================================
create index if not exists learning_resources_type_idx on public.learning_resources(resource_type);
create index if not exists learning_resources_difficulty_idx on public.learning_resources(difficulty_level);
create index if not exists resource_topics_resource_id_idx on public.resource_topics(resource_id);
create index if not exists resource_topics_topic_id_idx on public.resource_topics(topic_id);
create index if not exists user_resource_interactions_user_id_idx on public.user_resource_interactions(user_id);
create index if not exists user_resource_interactions_resource_id_idx on public.user_resource_interactions(resource_id);
create index if not exists user_resource_interactions_type_idx on public.user_resource_interactions(interaction_type);
create index if not exists recommendation_logs_user_id_idx on public.recommendation_logs(user_id);
create index if not exists recommendation_logs_created_at_idx on public.recommendation_logs(created_at);
