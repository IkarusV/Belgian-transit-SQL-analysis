import argparse
import csv
import io
import sqlite3
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import requests


# config

# __file__ is this script. parent gives us the project folder.
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# Build in a temporary file first so a failed import cannot break the old database.
DATABASE_PATH = DATA_DIR / "railpulse.db"
TEMP_DATABASE_PATH = DATA_DIR / "railpulse_build.db"

# The downloaded GTFS zip is cached so we do not call the API on every run.
ZIP_PATH = DATA_DIR / "nmbssncb.zip"
TEMP_ZIP_PATH = DATA_DIR / "nmbssncb_download.zip"
SCHEMA_PATH = BASE_DIR / "sql" / "schema.sql"

# Official SNCB/NMBS static schedule endpoint. It does not need an API key.
GTFS_URL = (
    "https://opendata-discovery-gtfs-static.api.production.belgianmobility.io/"
    "api/gtfs/feed/nmbssncb/static"
)

USER_AGENT = "RailPulse student project"

# stop_times has millions of rows. Insert chunks instead of loading all of it at once.
BATCH_SIZE = 20_000


# Step 1 download the GTFS data

def download_feed(force_download=False):
    """Download the official SNCB/NMBS GTFS zip.

    Input:
        force_download: True downloads a fresh zip even when one is cached.
    """
    # Create data/ on the first run.
    DATA_DIR.mkdir(exist_ok=True)

    # Reuse the local zip to save time and respect the API request limit.
    if ZIP_PATH.exists() and not force_download:
        print(f"using cached feed: {ZIP_PATH}")
        return

    print("downloading the SNCB/NMBS GTFS feed...")

    # stream=True downloads the file piece by piece instead of holding 26 MB in RAM.
    with requests.get(
        GTFS_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=120,
        stream=True,
    ) as response:
        # Stop here if the server returns an HTTP error like 404 or 429.
        response.raise_for_status()

        # Write to a temporary filename until the download is complete.
        with TEMP_ZIP_PATH.open("wb") as zip_file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                # Each loop writes the next 1 MB piece of the response.
                zip_file.write(chunk)

    # Reject an error page or interrupted download pretending to be a zip.
    if not zipfile.is_zipfile(TEMP_ZIP_PATH):
        TEMP_ZIP_PATH.unlink(missing_ok=True)
        raise SystemExit("downloaded file is not a valid GTFS zip")

    # Only replace the good cached file after the new zip passed validation.
    TEMP_ZIP_PATH.replace(ZIP_PATH)
    print(f"saved feed: {ZIP_PATH}")


def clean_value(value):
    """Turn empty GTFS text into database NULL values.

    Input:
        value: one value read from a GTFS CSV file.
    Returns:
        Clean text, or None when the field is empty.
    """
    # GTFS files sometimes contain extra spaces around values.
    value = value.strip()

    # Python None becomes SQL NULL when sqlite3 inserts it.
    return value if value else None


def read_gtfs_rows(feed, filename, columns):
    """Read selected columns from one file inside the GTFS zip.

    Input:
        feed: the opened GTFS zip file.
        filename: CSV filename inside the zip.
        columns: fields we want to keep for our database.
    Yields:
        One clean tuple at a time so memory stays low.
    """
    # Read directly from the zip. We do not need to extract every file to disk.
    with feed.open(filename) as raw_file:
        # Convert the binary zip content into normal UTF-8 text.
        text_file = io.TextIOWrapper(raw_file, encoding="utf-8-sig", newline="")

        # DictReader uses the first CSV row as column names.
        reader = csv.DictReader(text_file)

        for row in reader:
            # Keep the columns in the same order as the INSERT statement.
            yield tuple(clean_value(row[column]) for column in columns)


def insert_in_batches(connection, sql, rows, table_name):
    """Insert many rows without keeping the full file in memory.

    Input:
        connection: open SQLite connection.
        sql: parameterized INSERT query.
        rows: row generator from read_gtfs_rows().
        table_name: table name used in the progress message.
    """
    batch = []
    total = 0

    for row in rows:
        # Add each CSV row to the current chunk.
        batch.append(row)

        # Insert when the chunk reaches the chosen batch size.
        if len(batch) == BATCH_SIZE:
            # executemany runs the same safe parameterized query for every row.
            connection.executemany(sql, batch)
            total += len(batch)

            # Empty the list before filling the next chunk.
            batch.clear()

    # Insert the last chunk when it contains fewer than BATCH_SIZE rows.
    if batch:
        connection.executemany(sql, batch)
        total += len(batch)

    # Save this table before moving to the next large GTFS file.
    # We are still writing to a temporary database, not the final database.
    connection.commit()
    print(f"loaded {total:,} rows into {table_name}")


def create_database(analysis_date):
    """Create a clean SQLite database and load the GTFS files.

    Input:
        analysis_date: date used by the SQL reports in YYYY-MM-DD format.
    """
    # Remove a leftover temporary database from an interrupted old run.
    TEMP_DATABASE_PATH.unlink(missing_ok=True)
    connection = sqlite3.connect(TEMP_DATABASE_PATH)

    # SQLite needs this setting on every connection to enforce foreign keys.
    connection.execute("PRAGMA foreign_keys = ON")

    # NORMAL is faster for this rebuild while still being safe for normal use.
    connection.execute("PRAGMA synchronous = NORMAL")

    # Keep table definitions in a separate SQL file as required by the assignment.
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    connection.executescript(schema)

    # Open the zip once and read every needed GTFS file from it.
    with zipfile.ZipFile(ZIP_PATH) as feed:
        # feed_info has the version and date range of this schedule download.
        feed_info = next(
            read_gtfs_rows(
                feed,
                "feed_info.txt",
                ["feed_version", "feed_start_date", "feed_end_date"],
            ),
            (None,),
        )

        # GTFS uses YYYYMMDD while our project uses the readable YYYY-MM-DD form.
        compact_date = analysis_date.replace("-", "")

        # An uncovered date would give empty and misleading analysis results.
        if not feed_info[1] <= compact_date <= feed_info[2]:
            connection.close()
            TEMP_DATABASE_PATH.unlink(missing_ok=True)
            raise SystemExit(
                f"date must be between {feed_info[1]} and {feed_info[2]} for this feed"
            )

        # Save project metadata so reports always show which date and feed they use.
        connection.execute(
            """
            INSERT INTO project_settings (
                id,
                analysis_date,
                feed_version,
                feed_start_date,
                feed_end_date,
                downloaded_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                analysis_date,
                feed_info[0],
                feed_info[1],
                feed_info[2],
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        connection.commit()

        # For each GTFS file: source filename, target table, and columns to keep.
        # The order matters because parent tables must load before child tables.
        tables = [
            (
                "routes.txt",
                "routes",
                [
                    "route_id",
                    "agency_id",
                    "route_short_name",
                    "route_long_name",
                    "route_type",
                ],
            ),
            (
                "stops.txt",
                "stops",
                [
                    "stop_id",
                    "stop_name",
                    "location_type",
                    "parent_station",
                    "platform_code",
                    "stop_lat",
                    "stop_lon",
                    "wheelchair_boarding",
                ],
            ),
            (
                "calendar.txt",
                "calendar",
                [
                    "service_id",
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                    "saturday",
                    "sunday",
                    "start_date",
                    "end_date",
                ],
            ),
            (
                "trips.txt",
                "trips",
                [
                    "trip_id",
                    "route_id",
                    "service_id",
                    "trip_headsign",
                    "trip_short_name",
                    "direction_id",
                    "wheelchair_accessible",
                    "bikes_allowed",
                ],
            ),
            (
                "stop_times.txt",
                "stop_times",
                [
                    "trip_id",
                    "stop_sequence",
                    "stop_id",
                    "arrival_time",
                    "departure_time",
                    "pickup_type",
                    "drop_off_type",
                ],
            ),
            (
                "calendar_dates.txt",
                "calendar_dates",
                ["service_id", "date", "exception_type"],
            ),
        ]

        # Load each GTFS CSV into its matching normalized SQLite table.
        for filename, table_name, columns in tables:
            # Build one ? placeholder per column: (?, ?, ?, ...).
            placeholders = ", ".join("?" for _ in columns)
            column_names = ", ".join(columns)

            # Only table and column names are built here. All row values use ? safely.
            sql = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"

            # This is a generator, so rows are read only when the batch loop needs them.
            rows = read_gtfs_rows(feed, filename, columns)
            insert_in_batches(connection, sql, rows, table_name)

    # Update SQLite's internal statistics after millions of inserted rows.
    connection.execute("PRAGMA optimize")

    # Check that every foreign key points to a real parent row.
    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

    # Check that the SQLite file itself is not corrupted.
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    # Never publish the temporary database when one of the checks fails.
    if foreign_key_errors or integrity != "ok":
        connection.close()
        TEMP_DATABASE_PATH.unlink(missing_ok=True)
        raise SystemExit("database integrity check failed")

    connection.close()

    # Replace the old database only after the complete new one passed every check.
    TEMP_DATABASE_PATH.replace(DATABASE_PATH)
    print(f"database ready: {DATABASE_PATH}")


# Step 2 read command-line options

def parse_args():
    """Read --date and --download from the terminal command."""
    parser = argparse.ArgumentParser(description="Build the RailPulse SQLite database.")
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Analysis date in YYYY-MM-DD format. Default: today.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Download a fresh copy instead of using the cached zip.",
    )
    return parser.parse_args()


# main

def main():
    args = parse_args()

    # Give a clear error before downloading data when the date format is wrong.
    try:
        date.fromisoformat(args.date)
    except ValueError as error:
        raise SystemExit("date must use YYYY-MM-DD") from error

    # First get the source file, then turn it into a relational database.
    download_feed(args.download)
    create_database(args.date)


if __name__ == "__main__":
    main()
