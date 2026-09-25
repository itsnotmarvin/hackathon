-- 1435 Capital — Founder Evidence Graph schema
-- Reference copy of the tables created in the Supabase SQL editor.
-- Safe to re-run: each statement is guarded with IF NOT EXISTS.

create extension if not exists pgcrypto;

create table if not exists public.startups (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    legal_name text,
    website text,
    city text,
    state text default 'NJ',
    description text,
    created_at timestamptz default now()
);

create table if not exists public.founders (
    id uuid primary key default gen_random_uuid(),
    startup_id uuid references public.startups(id) on delete cascade,
    name text not null,
    title text,
    linkedin_url text,
    github_url text,
    location text,
    identity_confidence numeric,
    birth_year integer,
    created_at timestamptz default now()
);

-- Run once if your `founders` table predates this column:
-- alter table public.founders add column if not exists birth_year integer;

create table if not exists public.education (
    id uuid primary key default gen_random_uuid(),
    founder_id uuid references public.founders(id) on delete cascade,
    institution text,
    degree text,
    field text,
    start_year integer,
    end_year integer,
    source_name text,
    source_url text,
    created_at timestamptz default now()
);

create table if not exists public.companies (
    id uuid primary key default gen_random_uuid(),
    founder_id uuid references public.founders(id) on delete cascade,
    company_name text,
    role text,
    start_date date,
    end_date date,
    status text,
    source_name text,
    source_url text,
    created_at timestamptz default now()
);

create table if not exists public.grants (
    id uuid primary key default gen_random_uuid(),
    startup_id uuid references public.startups(id) on delete cascade,
    founder_id uuid references public.founders(id) on delete cascade,
    program text,
    agency text,
    amount numeric,
    award_date date,
    source_name text,
    source_url text,
    created_at timestamptz default now()
);

create table if not exists public.trademarks (
    id uuid primary key default gen_random_uuid(),
    startup_id uuid references public.startups(id) on delete cascade,
    founder_id uuid references public.founders(id) on delete cascade,
    mark text,
    serial_number text,
    status text,
    filing_date date,
    owner text,
    source_url text,
    created_at timestamptz default now()
);

create table if not exists public.achievements (
    id uuid primary key default gen_random_uuid(),
    founder_id uuid references public.founders(id) on delete cascade,
    achievement text,
    issuer text,
    year integer,
    description text,
    source_name text,
    source_url text,
    created_at timestamptz default now()
);

create table if not exists public.evidence (
    id uuid primary key default gen_random_uuid(),
    entity_type text not null,      -- 'founder' | 'company' | 'grant' | 'trademark' | 'achievement' | 'education'
    entity_id uuid not null,
    claim text not null,
    source_name text,
    source_url text,
    source_date date,
    retrieved_at timestamptz default now(),
    confidence numeric
);

create index if not exists evidence_entity_idx on public.evidence (entity_type, entity_id);
