-- Populate seed data for manual verification and local development

-- 1. Create mock auth users
insert into auth.users (id, email, raw_user_meta_data)
values 
  ('00000000-0000-0000-0000-000000000001', 'alice@example.com', '{"username": "alice_db_queen", "full_name": "Alice Developer", "avatar_url": "https://api.dicebear.com/7.x/adventurer/svg?seed=alice"}'),
  ('00000000-0000-0000-0000-000000000002', 'bob@example.com', '{"username": "bob_builds", "full_name": "Bob Architect", "avatar_url": "https://api.dicebear.com/7.x/adventurer/svg?seed=bob"}')
on conflict (id) do nothing;

-- Ensure profiles exist (normally automatic via triggers, but safe-seeded here just in case)
insert into public.profiles (id, username, full_name, avatar_url)
values
  ('00000000-0000-0000-0000-000000000001', 'alice_db_queen', 'Alice Developer', 'https://api.dicebear.com/7.x/adventurer/svg?seed=alice'),
  ('00000000-0000-0000-0000-000000000002', 'bob_builds', 'Bob Architect', 'https://api.dicebear.com/7.x/adventurer/svg?seed=bob')
on conflict (id) do nothing;

-- 2. Create a high-quality sample Quiz
insert into public.quizzes (id, title, description, creator_id, is_published)
values (
  '10000000-0000-0000-0000-000000000001',
  'Mastering PostgreSQL Basics',
  'Test your basic knowledge of database design, indexing, and SQL queries in PostgreSQL.',
  '00000000-0000-0000-0000-000000000002', -- created by Bob
  true
)
on conflict (id) do nothing;

-- 3. Create Questions for the Quiz
-- Question 1: Multiple choice
insert into public.questions (id, quiz_id, question_text, question_type, points, order_no)
values (
  '20000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  'What is the primary function of Row Level Security (RLS) in PostgreSQL?',
  'multiple_choice',
  2,
  1
)
on conflict (id) do nothing;

-- Options for Question 1
insert into public.options (id, question_id, option_text, is_correct)
values 
  ('30000000-0000-0000-0000-000000000011', '20000000-0000-0000-0000-000000000001', 'To speed up query compilation and schema generation.', false),
  ('30000000-0000-0000-0000-000000000012', '20000000-0000-0000-0000-000000000001', 'To restrict the rows returned or modified based on the executing user context.', true),
  ('30000000-0000-0000-0000-000000000013', '20000000-0000-0000-0000-000000000001', 'To automatically compress large column datatypes to save disk space.', false),
  ('30000000-0000-0000-0000-000000000014', '20000000-0000-0000-0000-000000000001', 'To enforce unique constraints across distinct multi-tenant databases.', false)
on conflict (id) do nothing;

-- Question 2: True/False
insert into public.questions (id, quiz_id, question_text, question_type, points, order_no)
values (
  '20000000-0000-0000-0000-000000000002',
  '10000000-0000-0000-0000-000000000001',
  'PostgreSQL triggers can execute functions written in languages other than PL/pgSQL, such as Python or JavaScript (if appropriate extensions are loaded).',
  'true_false',
  1,
  2
)
on conflict (id) do nothing;

-- Options for Question 2
insert into public.options (id, question_id, option_text, is_correct)
values 
  ('30000000-0000-0000-0000-000000000021', '20000000-0000-0000-0000-000000000002', 'True', true),
  ('30000000-0000-0000-0000-000000000022', '20000000-0000-0000-0000-000000000002', 'False', false)
on conflict (id) do nothing;

-- Question 3: Multiple choice
insert into public.questions (id, quiz_id, question_text, question_type, points, order_no)
values (
  '20000000-0000-0000-0000-000000000003',
  '10000000-0000-0000-0000-000000000001',
  'Which of the following index types is the default in PostgreSQL when running "CREATE INDEX"?',
  'multiple_choice',
  1,
  3
)
on conflict (id) do nothing;

-- Options for Question 3
insert into public.options (id, question_id, option_text, is_correct)
values 
  ('30000000-0000-0000-0000-000000000031', '20000000-0000-0000-0000-000000000003', 'Hash Index', false),
  ('30000000-0000-0000-0000-000000000032', '20000000-0000-0000-0000-000000000003', 'GIN Index', false),
  ('30000000-0000-0000-0000-000000000033', '20000000-0000-0000-0000-000000000003', 'B-Tree Index', true),
  ('30000000-0000-0000-0000-000000000034', '20000000-0000-0000-0000-000000000003', 'BRIN Index', false)
on conflict (id) do nothing;
