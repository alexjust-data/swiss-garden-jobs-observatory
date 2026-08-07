-- Swiss Garden Jobs Observatory — salary and total compensation patch v0.3
-- Apply after schema.sql. Salary observations are append-only and provenance-bearing.

DO $$ BEGIN
    CREATE TYPE salary_disclosure_status AS ENUM (
        'NOT_DISCLOSED','QUALITATIVE_ONLY','EXPLICIT_FIXED','EXPLICIT_MINIMUM',
        'EXPLICIT_MAXIMUM','EXPLICIT_RANGE','PUBLIC_GRADE_ONLY','COLLECTIVE_AGREEMENT_ONLY'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE salary_origin AS ENUM (
        'EMPLOYER_DECLARED','EMPLOYER_DECLARED_VIA_JOB_BOARD','RECRUITER_DECLARED',
        'JOB_BOARD_DISPLAYED','JOB_BOARD_SEARCH_RESULT','PUBLIC_PAY_SCALE_DERIVED',
        'GAV_MINIMUM','MARKET_BENCHMARK'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS compensation_observation (
    compensation_observation_id bigserial PRIMARY KEY,
    posting_observation_id bigint REFERENCES posting_observation(posting_observation_id),
    posting_id uuid REFERENCES posting(posting_id),
    vacancy_id uuid REFERENCES vacancy(vacancy_id),
    disclosure_status salary_disclosure_status NOT NULL,
    origin salary_origin NOT NULL,
    observation_scope text NOT NULL CHECK (observation_scope IN ('POSTING','VACANCY','EMPLOYER','AGREEMENT','MARKET')),
    currency char(3) NOT NULL,
    gross_net text NOT NULL CHECK (gross_net IN ('GROSS','NET','UNKNOWN')),
    amount_min numeric(14,2),
    amount_max numeric(14,2),
    period text NOT NULL CHECK (period IN ('HOUR','MONTH','YEAR','UNKNOWN')),
    payments_per_year smallint CHECK (payments_per_year BETWEEN 1 AND 24),
    workload_basis text NOT NULL CHECK (workload_basis IN ('ACTUAL_PENSUM','FTE_100','UNKNOWN')),
    annual_gross_fte_min numeric(14,2),
    annual_gross_fte_max numeric(14,2),
    normalization_status text NOT NULL,
    raw_text text,
    source_url text NOT NULL,
    observed_at timestamptz NOT NULL,
    confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    linkage_confidence numeric(5,4) CHECK (linkage_confidence BETWEEN 0 AND 1),
    public_pay_system text,
    public_pay_grade text,
    gav_code text,
    gav_applicability_status text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (amount_min IS NULL OR amount_min >= 0),
    CHECK (amount_max IS NULL OR amount_max >= 0),
    CHECK (amount_min IS NULL OR amount_max IS NULL OR amount_max >= amount_min),
    CHECK (annual_gross_fte_min IS NULL OR annual_gross_fte_min >= 0),
    CHECK (annual_gross_fte_max IS NULL OR annual_gross_fte_max >= 0),
    CHECK (annual_gross_fte_min IS NULL OR annual_gross_fte_max IS NULL OR annual_gross_fte_max >= annual_gross_fte_min)
);
CREATE INDEX IF NOT EXISTS idx_compensation_posting_time ON compensation_observation(posting_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_compensation_vacancy_time ON compensation_observation(vacancy_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_compensation_normalized ON compensation_observation(annual_gross_fte_min, annual_gross_fte_max) WHERE annual_gross_fte_min IS NOT NULL OR annual_gross_fte_max IS NOT NULL;

CREATE TABLE IF NOT EXISTS salary_reference (
    salary_reference_id text PRIMARY KEY,
    reference_type text NOT NULL CHECK (reference_type IN ('GAV_MINIMUM','PUBLIC_PAY_SCALE','MARKET_BENCHMARK','ADVERTISED_SALARY_EXAMPLE')),
    reference_scope text NOT NULL,
    qualification_level text,
    geography_scope text,
    currency char(3) NOT NULL,
    gross_net text NOT NULL CHECK (gross_net IN ('GROSS','NET','UNKNOWN')),
    amount_min numeric(14,2),
    amount_max numeric(14,2),
    period text NOT NULL CHECK (period IN ('HOUR','MONTH','YEAR','UNKNOWN')),
    payments_per_year smallint CHECK (payments_per_year BETWEEN 1 AND 24),
    valid_from date,
    valid_to date,
    applicability text NOT NULL,
    source_url text NOT NULL,
    source_tier text NOT NULL,
    evidence_payload_sha256 char(64),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS compensation_component (
    compensation_component_id bigserial PRIMARY KEY,
    compensation_observation_id bigint NOT NULL REFERENCES compensation_observation(compensation_observation_id),
    component_code text NOT NULL,
    mention_status text NOT NULL CHECK (mention_status IN ('INCLUDED','OFFERED','POSSIBLE','NOT_MENTIONED','UNKNOWN')),
    currency char(3),
    amount numeric(14,2),
    period text,
    raw_text text
);

ALTER TABLE daily_market_state
    ADD COLUMN IF NOT EXISTS salary_disclosure_coverage_ratio numeric(7,6),
    ADD COLUMN IF NOT EXISTS numeric_salary_coverage_ratio numeric(7,6),
    ADD COLUMN IF NOT EXISTS annual_fte_normalization_coverage_ratio numeric(7,6),
    ADD COLUMN IF NOT EXISTS advertised_salary_sample_n integer,
    ADD COLUMN IF NOT EXISTS advertised_annual_gross_fte_p25 numeric,
    ADD COLUMN IF NOT EXISTS advertised_annual_gross_fte_median numeric,
    ADD COLUMN IF NOT EXISTS advertised_annual_gross_fte_p75 numeric,
    ADD COLUMN IF NOT EXISTS salary_above_verified_floor_share numeric(7,6),
    ADD COLUMN IF NOT EXISTS public_salary_range_coverage_ratio numeric(7,6),
    ADD COLUMN IF NOT EXISTS benefits_disclosure_ratio numeric(7,6);

COMMENT ON COLUMN vacancy.salary_min IS 'DEPRECATED v0.3: do not write new observations here; use compensation_observation.';
COMMENT ON COLUMN vacancy.salary_max IS 'DEPRECATED v0.3: do not write new observations here; use compensation_observation.';
COMMENT ON COLUMN vacancy.salary_period IS 'DEPRECATED v0.3: do not write new observations here; use compensation_observation.';
