-- Swiss Garden Jobs Observatory — PostgreSQL reference schema v0.1
-- Point-in-time observation model. A disappeared posting is NOT assumed filled.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE source (
    source_id text PRIMARY KEY,
    source_name text NOT NULL,
    source_family text NOT NULL,
    source_type text NOT NULL,
    priority text NOT NULL,
    canonicality text NOT NULL,
    platform_family text,
    automation_status text NOT NULL,
    legal_review_status text NOT NULL,
    official_url text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE source_endpoint (
    source_endpoint_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id text NOT NULL REFERENCES source(source_id),
    endpoint_url text NOT NULL,
    endpoint_kind text NOT NULL CHECK (endpoint_kind IN ('LIST','DETAIL','API','RSS','SITEMAP','SEARCH','OTHER')),
    platform_family text,
    expected_scan_interval_minutes integer CHECK (expected_scan_interval_minutes > 0),
    collector_status text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    UNIQUE(source_id, endpoint_url)
);

CREATE TABLE employer (
    employer_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name text NOT NULL,
    normalized_name text NOT NULL,
    employment_relationship text NOT NULL CHECK (employment_relationship IN (
        'PUBLIC_DIRECT','PUBLIC_INSTITUTION','PUBLIC_CONTRACTOR','PRIVATE_DIRECT','AGENCY'
    )),
    public_level text CHECK (public_level IN ('FEDERAL','CANTON','CITY','MUNICIPALITY','PUBLIC_INSTITUTION') OR public_level IS NULL),
    canton_code char(2),
    bfs_code integer,
    website_url text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_employer_normalized_name ON employer(normalized_name);
CREATE INDEX idx_employer_bfs_code ON employer(bfs_code);

CREATE TABLE location (
    location_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bfs_code integer,
    municipality_name text,
    canton_code char(2),
    postal_code text,
    latitude numeric(9,6),
    longitude numeric(9,6),
    language_region text,
    valid_from date,
    valid_to date
);
CREATE INDEX idx_location_bfs ON location(bfs_code);

CREATE TABLE posting (
    posting_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id text NOT NULL REFERENCES source(source_id),
    source_native_id text,
    canonical_url text NOT NULL,
    raw_title text NOT NULL,
    raw_employer text,
    raw_location text,
    raw_published_at text,
    raw_payload_sha256 char(64) NOT NULL,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    current_status text NOT NULL CHECK (current_status IN (
        'ACTIVE','NOT_FOUND_PENDING','CLOSED_OBSERVED','EXPIRED_EXPLICIT','REDIRECTED','BLOCKED','ERROR','SOURCE_OUTAGE'
    )),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(source_id, source_native_id),
    UNIQUE(source_id, canonical_url)
);
CREATE INDEX idx_posting_status ON posting(current_status);
CREATE INDEX idx_posting_seen ON posting(first_seen_at, last_seen_at);

CREATE TABLE posting_observation (
    posting_observation_id bigserial PRIMARY KEY,
    posting_id uuid NOT NULL REFERENCES posting(posting_id),
    collector_run_id text NOT NULL,
    observed_at timestamptz NOT NULL,
    observation_status text NOT NULL CHECK (observation_status IN (
        'ACTIVE','NOT_FOUND','EXPIRED_EXPLICIT','REDIRECTED','BLOCKED','ERROR','SOURCE_OUTAGE'
    )),
    source_health_status text NOT NULL CHECK (source_health_status IN ('HEALTHY','DEGRADED','OUTAGE','UNKNOWN')),
    http_status integer,
    redirect_url text,
    payload_sha256 char(64),
    error_code text,
    error_detail text,
    UNIQUE(posting_id, collector_run_id)
);
CREATE INDEX idx_observation_posting_time ON posting_observation(posting_id, observed_at DESC);
CREATE INDEX idx_observation_source_health ON posting_observation(source_health_status, observed_at DESC);

CREATE TABLE vacancy (
    vacancy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    employer_id uuid REFERENCES employer(employer_id),
    location_id uuid REFERENCES location(location_id),
    canonical_title text NOT NULL,
    role_family text NOT NULL,
    specialization text,
    access_level text,
    employment_type text,
    workload_min numeric(5,2),
    workload_max numeric(5,2),
    positions_count integer CHECK (positions_count IS NULL OR positions_count >= 1),
    positions_count_confidence numeric(5,4),
    qualification_required text,
    experience_required text,
    german_requirement text,
    driving_licence_requirement text,
    salary_min numeric(12,2),
    salary_max numeric(12,2),
    salary_period text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_vacancy_role_location ON vacancy(role_family, location_id);
CREATE INDEX idx_vacancy_employer ON vacancy(employer_id);

CREATE TABLE vacancy_posting_link (
    vacancy_id uuid NOT NULL REFERENCES vacancy(vacancy_id),
    posting_id uuid NOT NULL REFERENCES posting(posting_id),
    duplicate_confidence numeric(5,4) NOT NULL CHECK (duplicate_confidence BETWEEN 0 AND 1),
    duplicate_method text NOT NULL,
    review_status text NOT NULL CHECK (review_status IN ('AUTO_ACCEPTED','HUMAN_ACCEPTED','HUMAN_REJECTED','PENDING_REVIEW')),
    linked_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (vacancy_id, posting_id)
);
CREATE INDEX idx_vpl_posting ON vacancy_posting_link(posting_id);

CREATE TABLE vacancy_episode (
    vacancy_episode_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    vacancy_id uuid NOT NULL REFERENCES vacancy(vacancy_id),
    episode_number integer NOT NULL CHECK (episode_number >= 1),
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    closed_observed_at timestamptz,
    closure_reason text CHECK (closure_reason IN (
        'DISAPPEARED_CONFIRMED','EXPIRED_EXPLICIT','EMPLOYER_WITHDRAWN_EXPLICIT','MERGED','UNKNOWN'
    ) OR closure_reason IS NULL),
    reappearance_gap_days integer,
    UNIQUE(vacancy_id, episode_number)
);
CREATE INDEX idx_episode_active ON vacancy_episode(first_seen_at, last_seen_at, closed_observed_at);

CREATE TABLE dedup_review_queue (
    review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    posting_id_a uuid NOT NULL REFERENCES posting(posting_id),
    posting_id_b uuid NOT NULL REFERENCES posting(posting_id),
    score numeric(5,4) NOT NULL,
    feature_breakdown jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('PENDING','MERGE','SEPARATE','DEFERRED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    UNIQUE(posting_id_a, posting_id_b)
);

CREATE TABLE collector_run (
    collector_run_id text PRIMARY KEY,
    source_id text NOT NULL REFERENCES source(source_id),
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    run_status text NOT NULL CHECK (run_status IN ('RUNNING','SUCCESS','PARTIAL','FAILED','BLOCKED')),
    pages_fetched integer NOT NULL DEFAULT 0,
    postings_seen integer NOT NULL DEFAULT 0,
    errors_count integer NOT NULL DEFAULT 0,
    health_detail jsonb
);

CREATE TABLE daily_market_state (
    state_date date NOT NULL,
    geography_type text NOT NULL,
    geography_id text NOT NULL,
    role_family text NOT NULL,
    employment_relationship text NOT NULL,
    active_postings integer NOT NULL,
    active_unique_vacancies integer NOT NULL,
    estimated_positions numeric,
    new_vacancies integer NOT NULL,
    disappeared_vacancies integer NOT NULL,
    reappeared_vacancies integer NOT NULL,
    unique_employers integer NOT NULL,
    unique_agencies integer NOT NULL,
    public_direct_share numeric(7,6),
    agency_share numeric(7,6),
    entry_accessible_share numeric(7,6),
    apprenticeship_share numeric(7,6),
    median_days_online numeric,
    repost_rate numeric(7,6),
    source_coverage_ratio numeric(7,6) NOT NULL,
    collector_success_ratio numeric(7,6) NOT NULL,
    observed_hiring_pressure numeric,
    scarcity_evidence_status text NOT NULL DEFAULT 'NOT_COMPUTED',
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (state_date, geography_type, geography_id, role_family, employment_relationship)
);

-- Raw payloads should be stored immutably in object storage and referenced by SHA-256.
-- Do not delete observations when a posting closes; history is the point-in-time evidence.

-- v0.3: apply schema_v0_3_salary_patch.sql for append-only compensation observations.
