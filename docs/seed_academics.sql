-- BioSecure AI — seed default academic structure (COER University, Roorkee)
-- Run once in Supabase SQL Editor. Safe to re-run (upserts only).
--
-- Required table shape (created automatically by the app on first use,
-- or create explicitly):
--   CREATE TABLE IF NOT EXISTS public.academic_structure (
--     id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
--     type TEXT NOT NULL CHECK (type IN ('program','branch','lecture','batch')),
--     value TEXT NOT NULL,
--     created_at TIMESTAMPTZ DEFAULT now(),
--     UNIQUE (type, value)
--   );
--
-- If your table already exists with the old constraint, run:
--   ALTER TABLE public.academic_structure DROP CONSTRAINT IF EXISTS academic_structure_type_check;
--   ALTER TABLE public.academic_structure ADD CONSTRAINT academic_structure_type_check CHECK (type IN ('program','branch','lecture','batch'));

-- Programs
INSERT INTO public.academic_structure (type, value) VALUES
  ('program','B.Tech'),('program','M.Tech'),('program','BCA'),('program','MCA'),
  ('program','B.Sc'),('program','M.Sc'),('program','BBA'),('program','MBA'),
  ('program','Diploma'),('program','Ph.D')
ON CONFLICT (type, value) DO NOTHING;

-- Branches
INSERT INTO public.academic_structure (type, value) VALUES
  ('branch','CSE'),('branch','IT'),('branch','ECE'),('branch','EEE'),
  ('branch','ME'),('branch','CE'),('branch','AI & ML'),('branch','Data Science'),
  ('branch','Cyber Security'),('branch','Biotechnology')
ON CONFLICT (type, value) DO NOTHING;

-- Starter Batches
INSERT INTO public.academic_structure (type, value) VALUES
  ('batch','2026'),('batch','2025'),('batch','2024'),('batch','2023'),
  ('batch','2022'),('batch','2021'),('batch','2020')
ON CONFLICT (type, value) DO NOTHING;

-- Starter lectures / subjects
INSERT INTO public.academic_structure (type, value) VALUES
  ('lecture','Mathematics'),('lecture','Physics'),('lecture','Programming in C'),
  ('lecture','Data Structures'),('lecture','DBMS'),('lecture','Operating Systems'),
  ('lecture','Computer Networks'),('lecture','Machine Learning'),
  ('lecture','General Session')
ON CONFLICT (type, value) DO NOTHING;
