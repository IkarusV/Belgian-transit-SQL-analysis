import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests


# config

# This script is optional. It adds live iRail snapshots to the static database.
BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "data" / "railpulse.db"
LIVEBOARD_URL = "https://api.irail.be/v1/liveboard"
BRUSSELS_CENTRAL_ID = "BE.NMBS.008813003"
USER_AGENT = "RailPulse student project"


# Step 1 convert iRail time

def unix_to_text(timestamp):
    """Convert an iRail Unix timestamp to readable UTC text.

    Input:
        timestamp: seconds counted from 1 January 1970.
    Returns:
        ISO date and time string in UTC.
    """
    return datetime.fromtimestamp(int(timestamp), timezone.utc).isoformat(
        timespec="seconds"
    )


# Step 2 fetch and save one liveboard snapshot

def main():
    # live_departures is created by the main ingestion script.
    if not DATABASE_PATH.exists():
        raise SystemExit("database not found, run ingest.py first")

    # Ask iRail for current departures from Brussels-Central.
    response = requests.get(
        LIVEBOARD_URL,
        params={
            # Official iRail station ID for Brussels-Central.
            "id": BRUSSELS_CENTRAL_ID,

            # We want departures as JSON and do not need the alert details here.
            "arrdep": "departure",
            "format": "json",
            "lang": "en",
            "alerts": "false",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )

    # Raise an error for bad responses instead of inserting broken data.
    response.raise_for_status()
    data = response.json()

    # Every row from this API call gets the same collection time.
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Empty list is safer than crashing when there are no departures.
    departures = data.get("departures", {}).get("departure", [])

    rows = []
    for departure in departures:
        # Turn each JSON departure object into one SQLite row.
        rows.append(
            (
                BRUSSELS_CENTRAL_ID,
                data["station"],
                departure["vehicle"],
                departure["station"],
                unix_to_text(departure["time"]),
                # iRail returns delays in seconds, not minutes.
                int(departure.get("delay", 0)),
                departure.get("platform"),
                int(departure.get("canceled", 0)),
                collected_at,
            )
        )

    # Wait for a short SQLite lock instead of failing immediately.
    # This can happen when the dashboard or another script is reading the same file.
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    # Remember the count before insertion so we can report real inserted rows.
    changes_before = connection.total_changes

    # executemany inserts the full snapshot with one parameterized SQL query.
    connection.executemany(
        """
        -- Ignore a duplicate when exactly the same snapshot was already saved.
        INSERT OR IGNORE INTO live_departures (
            station_id,
            station_name,
            vehicle_id,
            destination,
            scheduled_time,
            delay_seconds,
            platform,
            canceled,
            collected_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    # total_changes includes successful inserts but not ignored duplicates.
    saved_rows = connection.total_changes - changes_before
    connection.commit()
    connection.close()

    print(f"saved {saved_rows} live departures collected at {collected_at}")


if __name__ == "__main__":
    main()
