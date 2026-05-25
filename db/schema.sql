-- Enable UUID extension
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- Mock schema for testing without Supabase fully connected (for local/testing reliability)
create schema if not exists auth;
create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text unique,
  raw_user_meta_data jsonb,
  created_at timestamp with time zone default now()
);

-- ============================================================================
-- 1. Profiles Table (public.profiles)
-- ============================================================================
create table if not exists public.profiles (
  id uuid references auth.users(id) on delete cascade primary key,
  username text unique not null,
  full_name text,
  avatar_url text,
  created_at timestamp with time zone default now() not null,
  updated_at timestamp with time zone default now() not null
);

-- ============================================================================
-- 2. Quizzes Table (public.quizzes)
-- ============================================================================
create table if not exists public.quizzes (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  description text,
  creator_id uuid references public.profiles(id) on delete set null,
  is_published boolean default false not null,
  created_at timestamp with time zone default now() not null,
  updated_at timestamp with time zone default now() not null
);

-- ============================================================================
-- 3. Questions Table (public.questions)
-- ============================================================================
create table if not exists public.questions (
  id uuid primary key default gen_random_uuid(),
  quiz_id uuid references public.quizzes(id) on delete cascade not null,
  question_text text not null,
  question_type text default 'multiple_choice' not null check (question_type in ('multiple_choice', 'true_false', 'short_answer')),
  points integer default 1 not null check (points >= 0),
  order_no integer default 0 not null,
  created_at timestamp with time zone default now() not null
);

-- ============================================================================
-- 4. Options Table (public.options)
-- ============================================================================
create table if not exists public.options (
  id uuid primary key default gen_random_uuid(),
  question_id uuid references public.questions(id) on delete cascade not null,
  option_text text not null,
  is_correct boolean default false not null,
  created_at timestamp with time zone default now() not null
);

-- ============================================================================
-- 5. Quiz Attempts Table (public.quiz_attempts)
-- ============================================================================
create table if not exists public.quiz_attempts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete cascade not null,
  quiz_id uuid references public.quizzes(id) on delete cascade not null,
  score integer default 0 not null,
  started_at timestamp with time zone default now() not null,
  completed_at timestamp with time zone
);

-- ============================================================================
-- 6. User Responses Table (public.user_responses)
-- ============================================================================
create table if not exists public.user_responses (
  id uuid primary key default gen_random_uuid(),
  attempt_id uuid references public.quiz_attempts(id) on delete cascade not null,
  question_id uuid references public.questions(id) on delete cascade not null,
  selected_option_id uuid references public.options(id) on delete cascade not null,
  is_correct boolean not null,
  created_at timestamp with time zone default now() not null
);

-- ============================================================================
-- Triggers for Profiles Setup
-- ============================================================================
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, username, full_name, avatar_url)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'username', 'user_' || substr(new.id::text, 1, 8)),
    new.raw_user_meta_data->>'full_name',
    new.raw_user_meta_data->>'avatar_url'
  );
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ============================================================================
-- Row-Level Security (RLS) Configuration
-- ============================================================================
alter table public.profiles enable row level security;
alter table public.quizzes enable row level security;
alter table public.questions enable row level security;
alter table public.options enable row level security;
alter table public.quiz_attempts enable row level security;
alter table public.user_responses enable row level security;

-- 1. Profiles Policies
drop policy if exists "Profiles are viewable by anyone" on public.profiles;
create policy "Profiles are viewable by anyone" on public.profiles
  for select using (true);

drop policy if exists "Users can update their own profile" on public.profiles;
create policy "Users can update their own profile" on public.profiles
  for update using (auth.uid() = id);

-- 2. Quizzes Policies
drop policy if exists "Quizzes are viewable by everyone if published" on public.quizzes;
create policy "Quizzes are viewable by everyone if published" on public.quizzes
  for select using (is_published = true);

drop policy if exists "Creators can manage their own quizzes" on public.quizzes;
create policy "Creators can manage their own quizzes" on public.quizzes
  for all using (auth.uid() = creator_id);

-- 3. Questions Policies
drop policy if exists "Questions are viewable if quiz is published" on public.questions;
create policy "Questions are viewable if quiz is published" on public.questions
  for select using (
    exists (
      select 1 from public.quizzes q
      where q.id = questions.quiz_id and q.is_published = true
    )
  );

drop policy if exists "Creators can manage questions for their quizzes" on public.questions;
create policy "Creators can manage questions for their quizzes" on public.questions
  for all using (
    exists (
      select 1 from public.quizzes q
      where q.id = questions.quiz_id and q.creator_id = auth.uid()
    )
  );

-- 4. Options Policies
drop policy if exists "Options are viewable if quiz is published" on public.options;
create policy "Options are viewable if quiz is published" on public.options
  for select using (
    exists (
      select 1 from public.questions q
      join public.quizzes quiz on q.quiz_id = quiz.id
      where q.id = options.question_id and quiz.is_published = true
    )
  );

drop policy if exists "Creators can manage options for their quizzes" on public.options;
create policy "Creators can manage options for their quizzes" on public.options
  for all using (
    exists (
      select 1 from public.questions q
      join public.quizzes quiz on q.quiz_id = quiz.id
      where q.id = options.question_id and quiz.creator_id = auth.uid()
    )
  );

-- 5. Quiz Attempts Policies
drop policy if exists "Users can view their own quiz attempts" on public.quiz_attempts;
create policy "Users can view their own quiz attempts" on public.quiz_attempts
  for select using (auth.uid() = user_id);

drop policy if exists "Users can create their own quiz attempts" on public.quiz_attempts;
create policy "Users can create their own quiz attempts" on public.quiz_attempts
  for insert with check (auth.uid() = user_id);

drop policy if exists "Users can update their own quiz attempts" on public.quiz_attempts;
create policy "Users can update their own quiz attempts" on public.quiz_attempts
  for update using (auth.uid() = user_id);

-- 6. User Responses Policies
drop policy if exists "Users can view their own quiz responses" on public.user_responses;
create policy "Users can view their own quiz responses" on public.user_responses
  for select using (
    exists (
      select 1 from public.quiz_attempts a
      where a.id = user_responses.attempt_id and a.user_id = auth.uid()
    )
  );

drop policy if exists "Users can create their own quiz responses" on public.user_responses;
create policy "Users can create their own quiz responses" on public.user_responses
  for insert with check (
    exists (
      select 1 from public.quiz_attempts a
      where a.id = user_responses.attempt_id and a.user_id = auth.uid()
    )
  );

-- ============================================================================
-- Helper Performance Indexes
-- ============================================================================
create index if not exists quizzes_creator_id_idx on public.quizzes(creator_id);
create index if not exists questions_quiz_id_idx on public.questions(quiz_id);
create index if not exists options_question_id_idx on public.options(question_id);
create index if not exists quiz_attempts_user_id_idx on public.quiz_attempts(user_id);
create index if not exists quiz_attempts_quiz_id_idx on public.quiz_attempts(quiz_id);
create index if not exists user_responses_attempt_id_idx on public.user_responses(attempt_id);
create index if not exists user_responses_question_id_idx on public.user_responses(question_id);
