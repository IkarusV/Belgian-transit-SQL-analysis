import csv
import sqlite3
from pathlib import Path


# config

# Keep paths based on this file so the script works from any terminal folder.
BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "data" / "railpulse.db"
SQL_PATH = BASE_DIR / "sql" / "analysis.sql"
RESULTS_DIR = BASE_DIR / "results"

REPORT_NAMES = [
    "peak_hour",
    "busiest_platforms",
    "morning_destinations",
    "service_frequency",
    "route_accessibility",
]


# Step 1 load the five SQL queries

def read_queries():
    """Split the analysis file into its five queries.

    Returns:
        List containing the five SQL query strings.
    """
    sql = SQL_PATH.read_text(encoding="utf-8")

    # Every report query ends with a semicolon in analysis.sql.
    return [query.strip() for query in sql.split(";") if query.strip()]


# Step 2 save one report

def save_csv(name, columns, rows):
    """Save one query result as a CSV file.

    Input:
        name: output filename without .csv.
        columns: column names returned by SQLite.
        rows: result rows returned by SQLite.
    """
    # Create results/ on the first run.
    RESULTS_DIR.mkdir(exist_ok=True)
    output_path = RESULTS_DIR / f"{name}.csv"

    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file)

        # First write the header, then write all SQL result rows.
        writer.writerow(columns)
        writer.writerows(rows)

    print(f"saved {output_path}")


# Step 3 run every analysis query

def main():
    # The analysis needs the database created by ingest.py.
    if not DATABASE_PATH.exists():
        raise SystemExit("database not found, run ingest.py first")

    queries = read_queries()

    # Avoid silently pairing the wrong query with the wrong report filename.
    if len(queries) != len(REPORT_NAMES):
        raise SystemExit("analysis.sql must contain five queries")

    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute("PRAGMA foreign_keys = ON")

    # Show the date so the user knows which schedule is being analyzed.
    analysis_date = connection.execute(
        "SELECT analysis_date FROM project_settings WHERE id = 1"
    ).fetchone()[0]
    print(f"analysis date: {analysis_date}")

    # zip pairs each readable report name with its SQL query.
    for name, query in zip(REPORT_NAMES, queries):
        # Python executes SQL, but SQL does every calculation.
        cursor = connection.execute(query)

        # cursor.description contains the column names returned by SELECT.
        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

        # Print the result so it can be checked quickly in the terminal.
        print(f"\n{name}")
        print(columns)
        # Keep the terminal readable when a report contains hundreds of rows.
        preview_rows = rows[:10]
        for row in preview_rows:
            print(row)

        if len(rows) > len(preview_rows):
            print(f"... {len(rows) - len(preview_rows):,} more rows saved to CSV")

        # Save the same untouched SQL result for the report/dashboard workflow.
        save_csv(name, columns, rows)

    connection.close()


if __name__ == "__main__":
    main()
