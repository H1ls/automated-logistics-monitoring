CREATE TABLE IF NOT EXISTS schema_migrations (
    version integer PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_users (
    id bigserial PRIMARY KEY,
    username text NOT NULL,
    display_name text NOT NULL DEFAULT '',
    password_hash text NOT NULL DEFAULT '',
    role text NOT NULL CHECK (role IN ('admin', 'dispatcher', 'viewer')),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (username)
);

CREATE TABLE IF NOT EXISTS api_keys (
    id bigserial PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES app_users(id) ON UPDATE CASCADE ON DELETE CASCADE,
    key_hash text NOT NULL,
    name text NOT NULL DEFAULT '',
    last_used_at timestamptz,
    expires_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (key_hash)
);

CREATE TABLE IF NOT EXISTS carriers (
    id bigserial PRIMARY KEY,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS vehicles (
    id bigserial PRIMARY KEY,
    plate_number text NOT NULL,
    monitoring_id integer,
    monitoring_name text NOT NULL DEFAULT '',
    monitoring_center text NOT NULL DEFAULT '',
    vehicle_full_name text NOT NULL DEFAULT '',
    carrier_id bigint REFERENCES carriers(id) ON UPDATE CASCADE ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'active',
    brand text NOT NULL DEFAULT '',
    model text NOT NULL DEFAULT '',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (plate_number),
    UNIQUE (monitoring_id)
);

CREATE TABLE IF NOT EXISTS drivers (
    id bigserial PRIMARY KEY,
    full_name text NOT NULL,
    phone text NOT NULL DEFAULT '',
    carrier_id bigint REFERENCES carriers(id) ON UPDATE CASCADE ON DELETE SET NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id bigserial PRIMARY KEY,
    trip_number integer NOT NULL,
    google_sheet_id text,
    google_worksheet_id text,
    google_worksheet_title text,
    google_sheet_row integer,
    vehicle_id bigint REFERENCES vehicles(id) ON UPDATE CASCADE ON DELETE SET NULL,
    driver_id bigint REFERENCES drivers(id) ON UPDATE CASCADE ON DELETE SET NULL,
    carrier_id bigint REFERENCES carriers(id) ON UPDATE CASCADE ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'new',
    planned_start_at text,
    planned_end_at text,
    actual_start_at text,
    actual_end_at text,
    completed_at text,
    completion_source text,
    raw_load text NOT NULL DEFAULT '',
    raw_unload text NOT NULL DEFAULT '',
    comm_load text NOT NULL DEFAULT '',
    comm_unload text NOT NULL DEFAULT '',
    highlight_until text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (trip_number)
);

CREATE TABLE IF NOT EXISTS route_points (
    id bigserial PRIMARY KEY,
    task_id bigint NOT NULL REFERENCES tasks(id) ON UPDATE CASCADE ON DELETE CASCADE,
    sequence integer NOT NULL,
    point_type text NOT NULL CHECK (point_type IN ('load', 'unload')),
    location text NOT NULL DEFAULT '',
    latitude double precision,
    longitude double precision,
    geo_accuracy_m double precision,
    geocoded_at text,
    geocoding_source text,
    scheduled_time text,
    actual_arrival_at text,
    actual_departure_at text,
    comment text NOT NULL DEFAULT '',
    is_processed boolean NOT NULL DEFAULT false,
    processed_at text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (task_id, point_type, sequence)
);

CREATE TABLE IF NOT EXISTS status_events (
    id bigserial PRIMARY KEY,
    task_id bigint NOT NULL REFERENCES tasks(id) ON UPDATE CASCADE ON DELETE CASCADE,
    route_point_id bigint REFERENCES route_points(id) ON UPDATE CASCADE ON DELETE SET NULL,
    user_id bigint REFERENCES app_users(id) ON UPDATE CASCADE ON DELETE SET NULL,
    event_type text NOT NULL,
    field_name text NOT NULL DEFAULT '',
    old_value text,
    new_value text,
    message text NOT NULL DEFAULT '',
    source text NOT NULL DEFAULT 'user',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS task_notes (
    id bigserial PRIMARY KEY,
    task_id bigint NOT NULL REFERENCES tasks(id) ON UPDATE CASCADE ON DELETE CASCADE,
    author_user_id bigint REFERENCES app_users(id) ON UPDATE CASCADE ON DELETE SET NULL,
    text text NOT NULL DEFAULT '',
    author text NOT NULL DEFAULT 'user',
    media_type text,
    media_path text,
    is_important boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS route_estimates (
    id bigserial PRIMARY KEY,
    task_id bigint NOT NULL REFERENCES tasks(id) ON UPDATE CASCADE ON DELETE CASCADE,
    target_route_point_id bigint REFERENCES route_points(id) ON UPDATE CASCADE ON DELETE SET NULL,
    target_sequence integer NOT NULL DEFAULT 0,
    distance_km double precision NOT NULL DEFAULT 0,
    duration_minutes integer NOT NULL DEFAULT 0,
    arrival_time text NOT NULL DEFAULT '',
    on_time boolean NOT NULL DEFAULT false,
    buffer_minutes integer NOT NULL DEFAULT 0,
    time_buffer_text text NOT NULL DEFAULT '',
    calculated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vehicle_navigation_history (
    id bigserial PRIMARY KEY,
    vehicle_id bigint NOT NULL REFERENCES vehicles(id) ON UPDATE CASCADE ON DELETE CASCADE,
    task_id bigint REFERENCES tasks(id) ON UPDATE CASCADE ON DELETE SET NULL,
    latitude double precision,
    longitude double precision,
    coordinates text NOT NULL DEFAULT '',
    geo_text text NOT NULL DEFAULT '',
    geo_zona text NOT NULL DEFAULT '',
    speed_kmh double precision,
    gps_fix_text text NOT NULL DEFAULT '',
    gps_fix_age_seconds integer,
    has_fresh_coordinates boolean NOT NULL DEFAULT false,
    is_navigation_stale boolean NOT NULL DEFAULT false,
    collected_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id bigserial PRIMARY KEY,
    user_id bigint REFERENCES app_users(id) ON UPDATE CASCADE ON DELETE SET NULL,
    username text NOT NULL DEFAULT '',
    role text NOT NULL DEFAULT '',
    entity_type text NOT NULL,
    entity_id bigint,
    action text NOT NULL,
    before_data jsonb,
    after_data jsonb,
    changed_fields jsonb,
    source text NOT NULL DEFAULT 'api',
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE status_events
    ADD COLUMN IF NOT EXISTS user_id bigint REFERENCES app_users(id) ON UPDATE CASCADE ON DELETE SET NULL;

ALTER TABLE task_notes
    ADD COLUMN IF NOT EXISTS author_user_id bigint REFERENCES app_users(id) ON UPDATE CASCADE ON DELETE SET NULL;

ALTER TABLE app_users
    ADD COLUMN IF NOT EXISTS password_hash text NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_vehicles_carrier_id
    ON vehicles(carrier_id);

CREATE INDEX IF NOT EXISTS idx_vehicles_monitoring_name
    ON vehicles(monitoring_name);

CREATE INDEX IF NOT EXISTS idx_drivers_carrier_id
    ON drivers(carrier_id);

CREATE INDEX IF NOT EXISTS idx_drivers_name_phone
    ON drivers(full_name, phone);

CREATE INDEX IF NOT EXISTS idx_tasks_vehicle_status
    ON tasks(vehicle_id, status);

CREATE INDEX IF NOT EXISTS idx_tasks_status_source
    ON tasks(status, google_worksheet_title);

CREATE INDEX IF NOT EXISTS idx_tasks_planned_start_at
    ON tasks(planned_start_at);

CREATE INDEX IF NOT EXISTS idx_tasks_google_source
    ON tasks(google_sheet_id, google_worksheet_id, google_sheet_row);

CREATE INDEX IF NOT EXISTS idx_tasks_google_worksheet_row
    ON tasks(google_worksheet_title, google_sheet_row);

CREATE INDEX IF NOT EXISTS idx_tasks_active_source_order
    ON tasks(google_worksheet_title, (COALESCE(google_sheet_row, trip_number)), id)
    WHERE status NOT IN ('completed', 'archived', 'cancelled');

CREATE INDEX IF NOT EXISTS idx_tasks_active_source_updated
    ON tasks(google_worksheet_title, updated_at, id)
    WHERE status NOT IN ('completed', 'archived', 'cancelled');

CREATE INDEX IF NOT EXISTS idx_route_points_task_sequence
    ON route_points(task_id, sequence);

CREATE INDEX IF NOT EXISTS idx_route_points_task_type
    ON route_points(task_id, point_type);

CREATE INDEX IF NOT EXISTS idx_status_events_task_created
    ON status_events(task_id, created_at);

CREATE INDEX IF NOT EXISTS idx_status_events_user_created
    ON status_events(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_status_events_dedupe
    ON status_events(task_id, event_type, field_name, created_at);

CREATE INDEX IF NOT EXISTS idx_task_notes_task_created
    ON task_notes(task_id, created_at);

CREATE INDEX IF NOT EXISTS idx_task_notes_author_created
    ON task_notes(author_user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_route_estimates_task_calculated
    ON route_estimates(task_id, calculated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_route_estimates_dedupe
    ON route_estimates(task_id, target_sequence, calculated_at);

CREATE INDEX IF NOT EXISTS idx_vehicle_navigation_vehicle_collected
    ON vehicle_navigation_history(vehicle_id, collected_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_vehicle_navigation_task_collected
    ON vehicle_navigation_history(task_id, collected_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_vehicle_navigation_dedupe
    ON vehicle_navigation_history(vehicle_id, task_id, collected_at);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_id
    ON api_keys(user_id);

CREATE INDEX IF NOT EXISTS idx_api_keys_active_lookup
    ON api_keys(key_hash)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_audit_log_entity_created
    ON audit_log(entity_type, entity_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_user_created
    ON audit_log(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_created
    ON audit_log(created_at DESC, id DESC);

INSERT INTO schema_migrations(version)
VALUES (1)
ON CONFLICT (version) DO NOTHING;
