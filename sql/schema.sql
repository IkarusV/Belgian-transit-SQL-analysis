-- Make SQLite reject rows that point to missing parent rows.
PRAGMA foreign_keys = ON;

-- Rebuild from scratch so old rows never mix with a new GTFS feed.
-- Child tables are dropped before the parent tables they reference.
DROP VIEW IF EXISTS active_services;
DROP TABLE IF EXISTS live_departures;
DROP TABLE IF EXISTS calendar_dates;
DROP TABLE IF EXISTS stop_times;
DROP TABLE IF EXISTS trips;
DROP TABLE IF EXISTS calendar;
DROP TABLE IF EXISTS stops;
DROP TABLE IF EXISTS routes;
DROP TABLE IF EXISTS project_settings;

CREATE TABLE project_settings (
    -- This table always has one row, so the ID must be 1.
    id INTEGER PRIMARY KEY CHECK (id = 1),

    -- The reports use one selected date instead of mixing every season together.
    analysis_date TEXT NOT NULL,
    feed_version TEXT,
    feed_start_date TEXT NOT NULL,
    feed_end_date TEXT NOT NULL,
    downloaded_at TEXT NOT NULL
);

CREATE TABLE routes (
    -- GTFS IDs contain letters and punctuation, so they stay as TEXT.
    route_id TEXT PRIMARY KEY,
    agency_id TEXT,
    route_short_name TEXT,
    route_long_name TEXT NOT NULL,
    route_type INTEGER NOT NULL
);

CREATE TABLE stops (
    stop_id TEXT PRIMARY KEY,
    stop_name TEXT NOT NULL,
    location_type INTEGER NOT NULL DEFAULT 0,
    -- A platform points back to its main station in this same table.
    parent_station TEXT,
    platform_code TEXT,
    stop_lat REAL,
    stop_lon REAL,
    wheelchair_boarding INTEGER,
    -- Some platforms appear before their parent in stops.txt.
    -- SQLite checks this relation when the transaction finishes.
    FOREIGN KEY (parent_station) REFERENCES stops (stop_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE calendar (
    -- One service ID describes one normal weekly operating pattern.
    service_id TEXT PRIMARY KEY,
    monday INTEGER NOT NULL,
    tuesday INTEGER NOT NULL,
    wednesday INTEGER NOT NULL,
    thursday INTEGER NOT NULL,
    friday INTEGER NOT NULL,
    saturday INTEGER NOT NULL,
    sunday INTEGER NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL
);

CREATE TABLE trips (
    trip_id TEXT PRIMARY KEY,

    -- Every trip belongs to one route and one service calendar.
    route_id TEXT NOT NULL,
    service_id TEXT NOT NULL,
    trip_headsign TEXT,
    trip_short_name TEXT,
    direction_id INTEGER,
    wheelchair_accessible INTEGER,
    bikes_allowed INTEGER,
    FOREIGN KEY (route_id) REFERENCES routes (route_id),
    FOREIGN KEY (service_id) REFERENCES calendar (service_id)
);

CREATE TABLE stop_times (
    -- One trip has many ordered stops.
    trip_id TEXT NOT NULL,
    stop_sequence INTEGER NOT NULL,
    stop_id TEXT NOT NULL,
    arrival_time TEXT,
    departure_time TEXT,
    pickup_type INTEGER NOT NULL DEFAULT 0,
    drop_off_type INTEGER NOT NULL DEFAULT 0,
    -- The pair is unique: one sequence number can appear once in each trip.
    PRIMARY KEY (trip_id, stop_sequence),
    FOREIGN KEY (trip_id) REFERENCES trips (trip_id),
    FOREIGN KEY (stop_id) REFERENCES stops (stop_id)
);

CREATE TABLE calendar_dates (
    -- exception_type 1 adds a service. exception_type 2 removes it.
    service_id TEXT NOT NULL,
    date TEXT NOT NULL,
    exception_type INTEGER NOT NULL CHECK (exception_type IN (1, 2)),
    -- A service can have only one exception on the same date.
    PRIMARY KEY (service_id, date),
    FOREIGN KEY (service_id) REFERENCES calendar (service_id)
);

CREATE TABLE live_departures (
    -- This optional table stores snapshots from the real-time iRail API.
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id TEXT NOT NULL,
    station_name TEXT NOT NULL,
    vehicle_id TEXT NOT NULL,
    destination TEXT NOT NULL,
    scheduled_time TEXT NOT NULL,
    delay_seconds INTEGER NOT NULL,
    platform TEXT,
    canceled INTEGER NOT NULL,
    collected_at TEXT NOT NULL,
    -- Do not save the exact same train twice in one snapshot.
    UNIQUE (station_id, vehicle_id, scheduled_time, collected_at)
);

-- Indexes are like the index at the back of a book.
-- They help SQLite find join and filter values without reading every row.
CREATE INDEX idx_trips_service_id ON trips (service_id);
CREATE INDEX idx_trips_route_id ON trips (route_id);
CREATE INDEX idx_stop_times_stop_id ON stop_times (stop_id);
CREATE INDEX idx_stop_times_departure_time ON stop_times (departure_time);
CREATE INDEX idx_calendar_dates_date ON calendar_dates (date, exception_type);
CREATE INDEX idx_stops_parent_station ON stops (parent_station);

-- Regular services plus exceptions for the selected date.
CREATE VIEW active_services AS

-- Step 1 get the selected date and its weekday number.
-- SQLite uses 0 for Sunday and 6 for Saturday.
WITH settings AS (
    SELECT
        analysis_date,
        strftime('%w', analysis_date) AS weekday
    FROM project_settings
    WHERE id = 1
),

-- Step 2 keep services whose normal calendar says they run that day.
regular_services AS (
    SELECT calendar.service_id
    FROM calendar
    CROSS JOIN settings
    WHERE replace(settings.analysis_date, '-', '') BETWEEN calendar.start_date AND calendar.end_date
      -- Pick the matching weekday column for our selected date.
      AND CASE settings.weekday
            WHEN '0' THEN calendar.sunday
            WHEN '1' THEN calendar.monday
            WHEN '2' THEN calendar.tuesday
            WHEN '3' THEN calendar.wednesday
            WHEN '4' THEN calendar.thursday
            WHEN '5' THEN calendar.friday
            WHEN '6' THEN calendar.saturday
          END = 1
),

-- Step 3 add special services that were added only for this date.
added_services AS (
    SELECT calendar_dates.service_id
    FROM calendar_dates
    CROSS JOIN settings
    WHERE calendar_dates.date = replace(settings.analysis_date, '-', '')
      AND calendar_dates.exception_type = 1
),

-- Step 4 find normal services that were canceled for this date.
removed_services AS (
    SELECT calendar_dates.service_id
    FROM calendar_dates
    CROSS JOIN settings
    WHERE calendar_dates.date = replace(settings.analysis_date, '-', '')
      AND calendar_dates.exception_type = 2
)

-- UNION combines normal and added services without duplicate IDs.
SELECT service_id FROM regular_services
UNION
SELECT service_id FROM added_services

-- EXCEPT removes every canceled service from the final view.
EXCEPT
SELECT service_id FROM removed_services;
