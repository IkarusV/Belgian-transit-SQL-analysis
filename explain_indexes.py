import sqlite3
from pathlib import Path


# config

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "data" / "railpulse.db"


# This query joins the biggest table and filters on Brussels-Central platforms.
PLATFORM_QUERY = """
SELECT
    stops.platform_code,
    COUNT(*) AS departure_count
FROM stop_times
JOIN stops ON stops.stop_id = stop_times.stop_id
JOIN trips ON trips.trip_id = stop_times.trip_id
JOIN active_services ON active_services.service_id = trips.service_id
WHERE stops.parent_station = 'gs:nmbssncb:S8813003'
  AND stops.platform_code IS NOT NULL
  AND stops.platform_code <> ''
  AND stop_times.departure_time IS NOT NULL
  AND stop_times.pickup_type <> 1
GROUP BY stops.platform_code
ORDER BY departure_count DESC
LIMIT 3
"""


def main():
    """Show how SQLite plans the platform query and which indexes it uses."""
    if not DATABASE_PATH.exists():
        raise SystemExit("database not found, run ingest.py first")

    connection = sqlite3.connect(DATABASE_PATH)

    # EXPLAIN QUERY PLAN does not run the report. It shows SQLite's strategy.
    plan = connection.execute(f"EXPLAIN QUERY PLAN {PLATFORM_QUERY}").fetchall()

    print("SQLite query plan for the Brussels-Central platform report:\n")
    for row in plan:
        # The last value contains the useful message, including index names.
        print(row[3])

    connection.close()


if __name__ == "__main__":
    main()
