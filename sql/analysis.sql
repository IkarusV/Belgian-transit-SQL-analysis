-- 1. Hour with the most scheduled departures on the selected date.
SELECT
    -- Keep the first two characters: 17:42:00 becomes 17.
    substr(stop_times.departure_time, 1, 2) AS departure_hour,
    COUNT(*) AS departure_count
FROM stop_times

-- stop_times gives the time, trips gives the service ID,
-- and active_services keeps only trips running on our selected date.
JOIN trips ON trips.trip_id = stop_times.trip_id
JOIN active_services ON active_services.service_id = trips.service_id
WHERE stop_times.departure_time IS NOT NULL
  AND stop_times.departure_time <> ''

  -- pickup_type 1 means passengers cannot board at this stop.
  AND stop_times.pickup_type <> 1

-- Put all departures from the same hour into one group and count them.
GROUP BY departure_hour
ORDER BY departure_count DESC

-- We only need the busiest hour.
LIMIT 1;

-- 2. Three busiest Brussels-Central platforms.
SELECT
    stops.platform_code,
    COUNT(*) AS departure_count
FROM stop_times

-- Join each departure to its platform and selected-date trip.
JOIN stops ON stops.stop_id = stop_times.stop_id
JOIN trips ON trips.trip_id = stop_times.trip_id
JOIN active_services ON active_services.service_id = trips.service_id
-- This is the official GTFS parent station ID for Brussels-Central.
WHERE stops.parent_station = 'gs:nmbssncb:S8813003'
  AND stops.platform_code IS NOT NULL
  AND stops.platform_code <> ''
  AND stop_times.departure_time IS NOT NULL
  AND stop_times.pickup_type <> 1
GROUP BY stops.platform_code

-- Highest platform counts first, then keep the requested top three.
ORDER BY departure_count DESC
LIMIT 3;

-- 3. Three most common destinations for trips starting before noon.
WITH trip_starts AS (
    SELECT
        stop_times.trip_id,
        stop_times.departure_time,
        -- Number the stops inside each trip from first to last.
        ROW_NUMBER() OVER (
            PARTITION BY stop_times.trip_id
            ORDER BY stop_times.stop_sequence
        ) AS stop_number
    FROM stop_times
)
SELECT
    trips.trip_headsign,
    COUNT(*) AS trip_count
FROM trip_starts
JOIN trips ON trips.trip_id = trip_starts.trip_id
JOIN active_services ON active_services.service_id = trips.service_id

-- Count each trip once by keeping only its first stop.
WHERE trip_starts.stop_number = 1

  -- GTFS times sort correctly here because they use HH:MM:SS.
  AND trip_starts.departure_time < '12:00:00'
  AND trips.trip_headsign IS NOT NULL
  AND trips.trip_headsign <> ''
GROUP BY trips.trip_headsign
ORDER BY trip_count DESC
LIMIT 3;

-- 4. Percentage of services in each frequency group for the selected week.
WITH RECURSIVE week_dates(service_date, day_number) AS (
    -- Step 1 find the Monday of the week containing our analysis date.
    SELECT
        date(
            analysis_date,
            '-' || ((CAST(strftime('%w', analysis_date) AS INTEGER) + 6) % 7) || ' days'
        ),
        1
    FROM project_settings
    WHERE id = 1

    UNION ALL

    -- Step 2 add one day until the temporary list contains seven days.
    SELECT date(service_date, '+1 day'), day_number + 1
    FROM week_dates
    WHERE day_number < 7
),
operating_services AS (
    -- Step 3 find normal calendar services for each day of that week.
    SELECT calendar.service_id, week_dates.service_date
    FROM calendar
    CROSS JOIN week_dates
    WHERE replace(week_dates.service_date, '-', '') BETWEEN calendar.start_date AND calendar.end_date
      -- Check the correct weekday flag for each date.
      AND CASE strftime('%w', week_dates.service_date)
            WHEN '0' THEN calendar.sunday
            WHEN '1' THEN calendar.monday
            WHEN '2' THEN calendar.tuesday
            WHEN '3' THEN calendar.wednesday
            WHEN '4' THEN calendar.thursday
            WHEN '5' THEN calendar.friday
            WHEN '6' THEN calendar.saturday
          END = 1
      -- Remove normal services canceled by a calendar exception.
      AND NOT EXISTS (
          SELECT 1
          FROM calendar_dates
          WHERE calendar_dates.service_id = calendar.service_id
            AND calendar_dates.date = replace(week_dates.service_date, '-', '')
            AND calendar_dates.exception_type = 2
      )

    UNION

    -- Step 4 add special services listed only in calendar_dates.
    SELECT calendar_dates.service_id, week_dates.service_date
    FROM calendar_dates
    JOIN week_dates
      ON calendar_dates.date = replace(week_dates.service_date, '-', '')
    WHERE calendar_dates.exception_type = 1
),
service_frequency AS (
    -- Step 5 count how many different days each service runs that week.
    SELECT service_id, COUNT(DISTINCT service_date) AS days_per_week
    FROM operating_services
    GROUP BY service_id
),
frequency_groups AS (
    SELECT
        service_id,

        -- Apply the exact categories requested by the assignment.
        CASE
            WHEN days_per_week >= 5 THEN 'High Frequency'
            WHEN days_per_week BETWEEN 2 AND 4 THEN 'Medium Frequency'
            ELSE 'Low Frequency/Special'
        END AS frequency_category
    FROM service_frequency
)
SELECT
    frequency_category,
    COUNT(*) AS service_count,

    -- 100.0 forces decimal division instead of integer division.
    -- SUM(COUNT(*)) OVER () gives the total across all three groups.
    ROUND(
        100.0 * COUNT(*) / SUM(COUNT(*)) OVER (),
        2
    ) AS percentage
FROM frequency_groups
GROUP BY frequency_category
ORDER BY service_count DESC;

-- 5. Exact wheelchair and bicycle information for each active train route.
WITH train_route_amenities AS (
    -- Step 1 count guarantees and known values for each train route.
    SELECT
        routes.route_id,
        routes.route_short_name,
        routes.route_long_name,
        COUNT(*) AS scheduled_trips,

        -- GTFS value 1 means the feature is explicitly available.
        SUM(CASE WHEN trips.wheelchair_accessible = 1 THEN 1 ELSE 0 END)
            AS wheelchair_guaranteed_trips,
        COUNT(trips.wheelchair_accessible) AS wheelchair_known_trips,

        SUM(CASE WHEN trips.bikes_allowed = 1 THEN 1 ELSE 0 END)
            AS bicycle_guaranteed_trips,
        COUNT(trips.bikes_allowed) AS bicycle_known_trips
    FROM trips
    JOIN routes ON routes.route_id = trips.route_id
    JOIN active_services ON active_services.service_id = trips.service_id

    -- GTFS route type 2 means rail. Replacement buses use route type 3.
    WHERE routes.route_type = 2
    GROUP BY routes.route_id, routes.route_short_name, routes.route_long_name
)
SELECT
    route_id,
    route_short_name,
    route_long_name,
    scheduled_trips,

    wheelchair_guaranteed_trips,
    ROUND(1.0 * wheelchair_guaranteed_trips / scheduled_trips, 4)
        AS wheelchair_explicit_ratio,
    ROUND(100.0 * wheelchair_guaranteed_trips / scheduled_trips, 2)
        AS wheelchair_explicit_percentage,
    ROUND(100.0 * wheelchair_known_trips / scheduled_trips, 2)
        AS wheelchair_data_coverage_percentage,

    bicycle_guaranteed_trips,
    ROUND(1.0 * bicycle_guaranteed_trips / scheduled_trips, 4)
        AS bicycle_explicit_ratio,
    ROUND(100.0 * bicycle_guaranteed_trips / scheduled_trips, 2)
        AS bicycle_explicit_percentage,
    ROUND(100.0 * bicycle_known_trips / scheduled_trips, 2)
        AS bicycle_data_coverage_percentage
FROM train_route_amenities

-- Keep route-level evidence even though the current feed gives every train route
-- the same result. This proves that no unique lowest route can be identified.
ORDER BY route_short_name, route_long_name, route_id;
