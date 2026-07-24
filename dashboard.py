import csv
import html
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import streamlit as st


# config

# The dashboard uses project-relative paths, so it works from any cloned folder.
BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "data" / "railpulse.db"
SQL_PATH = BASE_DIR / "sql" / "analysis.sql"
RESULTS_DIR = BASE_DIR / "results"
METADATA_PATH = RESULTS_DIR / "report_metadata.json"
GITHUB_URL = "https://github.com/IkarusV/Belgian-transit-SQL-analysis"

REPORT_FILES = [
    "peak_hour.csv",
    "busiest_platforms.csv",
    "morning_destinations.csv",
    "service_frequency.csv",
    "route_accessibility.csv",
]


# Step 1 load data from SQLite

def read_queries():
    """Read the five analysis queries in their original order."""
    sql = SQL_PATH.read_text(encoding="utf-8")
    return [query.strip() for query in sql.split(";") if query.strip()]


def run_query(connection, query):
    """Run one SQL query and return dictionaries with column names."""
    cursor = connection.execute(query)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def parse_csv_value(value):
    """Turn CSV numbers back into int or float values when possible."""
    if value == "":
        return None

    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def load_csv_report(filename):
    """Load one committed SQL result for the hosted dashboard."""
    with (RESULTS_DIR / filename).open(encoding="utf-8-sig", newline="") as file:
        return [
            {key: parse_csv_value(value) for key, value in row.items()}
            for row in csv.DictReader(file)
        ]


def load_dashboard_data():
    """Prefer SQLite locally and use committed SQL outputs in the cloud."""
    if DATABASE_PATH.exists():
        connection = sqlite3.connect(DATABASE_PATH)
        connection.execute("PRAGMA foreign_keys = ON")

        settings = connection.execute(
            """
            SELECT analysis_date, feed_version
            FROM project_settings
            WHERE id = 1
            """
        ).fetchone()
        reports = [run_query(connection, query) for query in read_queries()]
        return settings, reports, connection, "Local SQLite database"

    missing_files = [
        filename for filename in REPORT_FILES if not (RESULTS_DIR / filename).exists()
    ]
    if missing_files or not METADATA_PATH.exists():
        missing = ", ".join(missing_files or [METADATA_PATH.name])
        raise FileNotFoundError(f"Missing hosted report files: {missing}")

    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    reports = [load_csv_report(filename) for filename in REPORT_FILES]
    settings = (metadata["analysis_date"], metadata["feed_version"])
    return settings, reports, None, "Published SQL report snapshot"


def format_date(value):
    """Turn an ISO date into a readable dashboard date."""
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d %B %Y")


def safe(value):
    """Escape database text before placing it inside custom HTML."""
    return html.escape(str(value))


def compact_html(markup):
    """Remove line indentation that Streamlit Markdown can mistake for code."""
    return " ".join(line.strip() for line in markup.splitlines() if line.strip())


# Step 2 reusable visual blocks

def section_title(kicker, title, description):
    """Display a consistent heading for each dashboard section."""
    st.markdown(
        f"""
        <div class="section-heading">
            <p class="kicker">{safe(kicker)}</p>
            <h2>{safe(title)}</h2>
            <p>{safe(description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ranking_bars(rows, label_key, value_key, label_prefix=""):
    """Create simple HTML bars without doing any data calculation."""
    highest = max(row[value_key] for row in rows) if rows else 1
    colors = ["#f6c945", "#4ca6e8", "#7b8ba6"]
    blocks = []

    for position, row in enumerate(rows, start=1):
        width = 100 * row[value_key] / highest
        color = colors[min(position - 1, len(colors) - 1)]
        blocks.append(
            compact_html(
                f"""
            <div class="ranking-row">
                <div class="rank-number">0{position}</div>
                <div class="ranking-main">
                    <div class="ranking-labels">
                        <span>{safe(label_prefix)}{safe(row[label_key])}</span>
                        <strong>{row[value_key]:,}</strong>
                    </div>
                    <div class="bar-track">
                        <div class="bar-fill" style="width:{width:.1f}%;background:{color};"></div>
                    </div>
                </div>
            </div>
            """
            )
        )

    st.markdown(
        f'<div class="ranking-card">{"".join(blocks)}</div>',
        unsafe_allow_html=True,
    )


# Step 3 page setup and styling

st.set_page_config(
    page_title="RailPulse | Belgian rail analysis",
    page_icon=":train:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

        :root {
            --ink: #eef4fb;
            --muted: #91a2b8;
            --panel: #111d2c;
            --panel-soft: #152437;
            --line: #26384e;
            --yellow: #f6c945;
            --blue: #4ca6e8;
            --red: #ff7d73;
        }

        *, *::before, *::after {
            box-sizing: border-box;
        }

        .stApp {
            background:
                radial-gradient(circle at 88% 3%, rgba(76, 166, 232, 0.14), transparent 24rem),
                linear-gradient(180deg, #09131f 0%, #0b1624 100%);
            color: var(--ink);
        }

        .block-container {
            max-width: 1220px;
            padding-top: 2.25rem;
            padding-bottom: 5rem;
        }

        header[data-testid="stHeader"] {
            background: transparent;
        }

        #MainMenu, footer, .stDeployButton {
            visibility: hidden;
        }

        h1, h2, h3, .hero-title, .metric-value {
            font-family: "Space Grotesk", sans-serif;
        }

        p, span, div, button, table {
            font-family: "DM Sans", sans-serif;
        }

        .hero {
            position: relative;
            overflow: hidden;
            border: 1px solid var(--line);
            border-radius: 24px;
            padding: 2.4rem 2.6rem;
            background: linear-gradient(115deg, #12243a 0%, #101c2b 68%, #172538 100%);
            box-shadow: 0 24px 70px rgba(0, 0, 0, 0.25);
        }

        .hero::after {
            content: "";
            position: absolute;
            right: -4rem;
            bottom: -8rem;
            width: 24rem;
            height: 24rem;
            border: 3.5rem solid rgba(246, 201, 69, 0.08);
            border-radius: 50%;
        }

        .brand-line {
            display: flex;
            align-items: center;
            gap: 0.7rem;
            color: var(--yellow);
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }

        .brand-mark {
            width: 2.2rem;
            height: 0.42rem;
            border-radius: 1rem;
            background: var(--yellow);
        }

        .hero-title {
            position: relative;
            z-index: 1;
            max-width: 760px;
            margin: 1.1rem 0 0.7rem;
            color: var(--ink);
            font-size: clamp(2.35rem, 5vw, 4.5rem);
            line-height: 0.98;
            letter-spacing: -0.055em;
        }

        .hero-copy {
            position: relative;
            z-index: 1;
            max-width: 660px;
            margin: 0;
            color: #b6c4d5;
            font-size: 1.02rem;
            line-height: 1.65;
        }

        .meta-strip {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.8rem;
            margin-top: 1.2rem;
        }

        .meta-item, .metric-card, .ranking-card, .frequency-card, .route-card, .live-card {
            border: 1px solid var(--line);
            background: rgba(17, 29, 44, 0.92);
            border-radius: 16px;
        }

        .meta-item {
            padding: 1rem 1.1rem;
        }

        .meta-label, .metric-label {
            color: var(--muted);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.09em;
            text-transform: uppercase;
        }

        .meta-value {
            display: block;
            margin-top: 0.3rem;
            color: var(--ink);
            font-weight: 600;
        }

        .metric-card {
            min-height: 150px;
            padding: 1.35rem 1.4rem;
            box-shadow: inset 0 3px 0 var(--accent, var(--yellow));
        }

        .metric-value {
            margin: 0.7rem 0 0.35rem;
            color: var(--ink);
            font-size: 2.35rem;
            font-weight: 700;
            letter-spacing: -0.04em;
        }

        .metric-note {
            color: var(--muted);
            font-size: 0.86rem;
            line-height: 1.45;
        }

        .section-heading {
            margin: 3.6rem 0 1.2rem;
        }

        .section-heading .kicker {
            margin: 0 0 0.35rem;
            color: var(--yellow);
            font-size: 0.73rem;
            font-weight: 700;
            letter-spacing: 0.13em;
            text-transform: uppercase;
        }

        .section-heading h2 {
            margin: 0;
            color: var(--ink);
            font-size: 1.75rem;
            letter-spacing: -0.035em;
        }

        .section-heading p {
            max-width: 720px;
            margin: 0.45rem 0 0;
            color: var(--muted);
            line-height: 1.55;
        }

        .ranking-card {
            padding: 0.45rem 1.2rem;
        }

        .ranking-row {
            display: flex;
            align-items: center;
            gap: 1rem;
            padding: 1rem 0;
            border-bottom: 1px solid rgba(38, 56, 78, 0.75);
        }

        .ranking-row:last-child {
            border-bottom: 0;
        }

        .rank-number {
            width: 2rem;
            color: #5e728c;
            font-family: "Space Grotesk", sans-serif;
            font-weight: 700;
        }

        .ranking-main {
            flex: 1;
        }

        .ranking-labels {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.55rem;
            color: var(--ink);
        }

        .ranking-labels strong {
            color: var(--yellow);
        }

        .bar-track {
            height: 0.42rem;
            overflow: hidden;
            border-radius: 1rem;
            background: #223249;
        }

        .bar-fill {
            height: 100%;
            min-width: 0.4rem;
            border-radius: 1rem;
        }

        .frequency-card {
            height: 100%;
            padding: 1.25rem;
        }

        .frequency-top {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            gap: 0.8rem;
        }

        .frequency-name {
            color: var(--ink);
            font-weight: 600;
        }

        .frequency-percent {
            color: var(--yellow);
            font-family: "Space Grotesk", sans-serif;
            font-size: 1.55rem;
            font-weight: 700;
        }

        .frequency-count {
            margin-top: 0.75rem;
            color: var(--muted);
            font-size: 0.83rem;
        }

        .notice {
            border-left: 3px solid var(--yellow);
            border-radius: 0 12px 12px 0;
            padding: 1rem 1.2rem;
            background: rgba(246, 201, 69, 0.08);
            color: #c8d3e0;
            line-height: 1.55;
        }

        .notice strong {
            color: var(--yellow);
        }

        .amenity-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.7rem;
            margin-top: 1rem;
        }

        .amenity-card {
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 1.2rem;
            background: rgba(17, 29, 44, 0.92);
        }

        .amenity-status {
            display: inline-block;
            border-radius: 999px;
            padding: 0.32rem 0.62rem;
            font-size: 0.73rem;
            font-weight: 700;
        }

        .amenity-confirmed {
            background: rgba(82, 196, 137, 0.12);
            color: #79d8a8;
        }

        .amenity-unknown {
            background: rgba(127, 143, 172, 0.14);
            color: #b7c3d4;
        }

        .amenity-card h3 {
            margin: 0.9rem 0 0.35rem;
            color: var(--ink);
            font-size: 1.25rem;
        }

        .amenity-card p {
            margin: 0;
            color: var(--muted);
            line-height: 1.55;
        }

        .live-card {
            display: grid;
            grid-template-columns: minmax(170px, 1.8fr) 0.8fr 0.7fr 0.7fr;
            align-items: center;
            gap: 0.8rem;
            margin-bottom: 0.55rem;
            padding: 0.85rem 1rem;
        }

        .live-destination {
            color: var(--ink);
            font-weight: 600;
        }

        .live-cell {
            color: #b9c7d7;
            font-size: 0.86rem;
        }

        .status {
            justify-self: end;
            border-radius: 999px;
            padding: 0.3rem 0.55rem;
            font-size: 0.72rem;
            font-weight: 700;
        }

        .status-on-time {
            background: rgba(82, 196, 137, 0.12);
            color: #79d8a8;
        }

        .status-delayed, .status-canceled {
            background: rgba(255, 125, 115, 0.12);
            color: #ff9d95;
        }

        div[data-testid="stExpander"] {
            border: 1px solid var(--line);
            border-radius: 14px;
            background: rgba(17, 29, 44, 0.7);
        }

        div[data-testid="stExpander"] a {
            color: var(--yellow);
            font-weight: 600;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 12px;
            overflow: hidden;
        }

        @media (max-width: 760px) {
            .block-container {
                padding: 1rem 0.85rem 3rem;
            }

            .hero {
                padding: 1.6rem 1.35rem;
                border-radius: 18px;
            }

            .hero-title {
                font-size: 2.75rem;
            }

            .metric-value {
                font-size: 2rem;
            }

            .meta-strip, .amenity-grid {
                grid-template-columns: 1fr;
            }

            .live-card {
                grid-template-columns: 1fr 1fr;
            }

            .status {
                justify-self: start;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)


try:
    settings, reports, connection, data_mode = load_dashboard_data()
except (FileNotFoundError, KeyError, json.JSONDecodeError) as error:
    st.error(str(error))
    st.stop()

# SQL calculates every report. In hosted mode, the committed SQL outputs are read.
peak_hour, platforms, destinations, frequencies, accessibility = reports


# Step 4 hero and headline findings

st.markdown(
    f"""
    <div class="hero">
        <div class="brand-line"><span class="brand-mark"></span> Belgian rail intelligence</div>
        <h1 class="hero-title">RailPulse</h1>
        <p class="hero-copy">
            A network-level view of scheduled SNCB/NMBS activity, built from the
            official GTFS feed and analyzed with SQLite.
        </p>
    </div>
    <div class="meta-strip">
        <div class="meta-item">
            <span class="meta-label">Schedule date</span>
            <span class="meta-value">{safe(format_date(settings[0]))}</span>
        </div>
        <div class="meta-item">
            <span class="meta-label">Feed release</span>
            <span class="meta-value">{safe(format_date(settings[1]))}</span>
        </div>
        <div class="meta-item">
            <span class="meta-label">Dashboard mode</span>
            <span class="meta-value">{safe(data_mode)}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

top_destination = destinations[0]
top_platform = platforms[0]
frequency_total = sum(row["service_count"] for row in frequencies)

metric_columns = st.columns(4)
metric_values = [
    (
        "Network peak",
        f'{int(peak_hour[0]["departure_hour"]):02d}:00',
        f'{peak_hour[0]["departure_count"]:,} scheduled departures',
        "#f6c945",
    ),
    (
        "Leading platform",
        f'Platform {top_platform["platform_code"]}',
        f'{top_platform["departure_count"]:,} departures at Brussels-Central',
        "#4ca6e8",
    ),
    (
        "Top morning destination",
        top_destination["trip_headsign"],
        f'{top_destination["trip_count"]:,} trips starting before noon',
        "#7f8fac",
    ),
    (
        "Weekly services",
        f"{frequency_total:,}",
        "Unique service IDs across the selected week",
        "#52c489",
    ),
]

for column, (label, value, note, color) in zip(metric_columns, metric_values):
    with column:
        st.markdown(
            f"""
            <div class="metric-card" style="--accent:{color};">
                <div class="metric-label">{safe(label)}</div>
                <div class="metric-value">{safe(value)}</div>
                <div class="metric-note">{safe(note)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# Step 5 ranked network findings

left_column, right_column = st.columns(2, gap="large")

with left_column:
    section_title(
        "Station pressure",
        "Brussels-Central platforms",
        "Scheduled departures from the three most active platforms.",
    )
    ranking_bars(platforms, "platform_code", "departure_count", "Platform ")

with right_column:
    section_title(
        "Morning movement",
        "Leading destinations",
        "Terminal destinations appearing most often on trips beginning before noon.",
    )
    ranking_bars(destinations, "trip_headsign", "trip_count")


# Step 6 frequency mix

section_title(
    "Service pattern",
    "How often services run",
    "Each service ID is classified by the number of operating days in the selected week.",
)

frequency_columns = st.columns(3)
frequency_colors = {
    "High Frequency": "#52c489",
    "Medium Frequency": "#f6c945",
    "Low Frequency/Special": "#7f8fac",
}

for column, row in zip(frequency_columns, frequencies):
    color = frequency_colors[row["frequency_category"]]
    with column:
        st.markdown(
            f"""
            <div class="frequency-card">
                <div class="frequency-top">
                    <span class="frequency-name">{safe(row["frequency_category"])}</span>
                    <span class="frequency-percent">{row["percentage"]:.2f}%</span>
                </div>
                <div class="bar-track" style="margin-top:1rem;">
                    <div class="bar-fill" style="width:{row["percentage"]}%;background:{color};"></div>
                </div>
                <div class="frequency-count">{row["service_count"]:,} service IDs</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# Step 7 focused amenity warning

section_title(
    "Passenger amenities",
    "What the train data can actually prove",
    "Route-level guarantees are separated from missing information so unknown values are not presented as failures.",
)

st.markdown(
    """
    <div class="notice">
        <strong>No weakest train route can be identified.</strong>
        Every active train route has the same feed-level result, so ranking routes
        would create a difference that the source data does not contain.
    </div>
    """,
    unsafe_allow_html=True,
)

train_trip_total = sum(row["scheduled_trips"] for row in accessibility)
train_route_total = len(accessibility)

st.markdown(
    f"""
    <div class="amenity-grid">
        <div class="amenity-card">
            <span class="amenity-status amenity-confirmed">Confirmed throughout feed</span>
            <h3>Bicycle storage</h3>
            <p>
                Marked as available on all {train_trip_total:,} scheduled train trips
                across {train_route_total:,} active route IDs.
            </p>
        </div>
        <div class="amenity-card">
            <span class="amenity-status amenity-unknown">Not reported in GTFS</span>
            <h3>Wheelchair accessibility</h3>
            <p>
                The field is unspecified on every scheduled train trip. This is
                missing information, not evidence that trains are inaccessible.
            </p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("View route-level evidence"):
    st.dataframe(
        accessibility,
        column_order=(
            "route_short_name",
            "route_long_name",
            "scheduled_trips",
            "wheelchair_data_coverage_percentage",
            "bicycle_explicit_percentage",
            "bicycle_data_coverage_percentage",
        ),
        column_config={
            "route_short_name": "Service",
            "route_long_name": "Route",
            "scheduled_trips": "Trips",
            "wheelchair_data_coverage_percentage": "Wheelchair data coverage (%)",
            "bicycle_explicit_percentage": "Bicycle availability (%)",
            "bicycle_data_coverage_percentage": "Bicycle data coverage (%)",
        },
        hide_index=True,
        use_container_width=True,
    )


# Step 8 latest local liveboard snapshot

latest_collection = None
if connection is not None:
    latest_collection = connection.execute(
        "SELECT MAX(collected_at) FROM live_departures"
    ).fetchone()[0]

if latest_collection:
    live_rows = connection.execute(
        """
        SELECT
            destination,
            scheduled_time,
            ROUND(delay_seconds / 60.0, 1) AS delay_minutes,
            platform,
            canceled
        FROM live_departures
        WHERE collected_at = ?
        ORDER BY scheduled_time
        LIMIT 12
        """,
        (latest_collection,),
    ).fetchall()

    section_title(
        "Live operations",
        "Latest Brussels-Central snapshot",
        f"Current departure information collected at {latest_collection[11:16]} UTC.",
    )

    live_cards = []
    for destination, scheduled_time, delay_minutes, platform, canceled in live_rows:
        departure_time = datetime.fromisoformat(scheduled_time).strftime("%H:%M")

        if canceled:
            status_label = "Canceled"
            status_class = "status-canceled"
        elif delay_minutes > 0:
            status_label = f"+{delay_minutes:g} min"
            status_class = "status-delayed"
        else:
            status_label = "On time"
            status_class = "status-on-time"

        live_cards.append(
            compact_html(
                f"""
            <div class="live-card">
                <div class="live-destination">{safe(destination)}</div>
                <div class="live-cell">Departure {departure_time}</div>
                <div class="live-cell">Platform {safe(platform or "TBC")}</div>
                <div class="status {status_class}">{safe(status_label)}</div>
            </div>
            """
            )
        )

    st.markdown("".join(live_cards), unsafe_allow_html=True)

if connection is not None:
    connection.close()


# Step 9 project and data notes

with st.expander("About this dashboard"):
    st.markdown(
        f"""
        ### About RailPulse

        This dashboard presents Belgian railway schedule analysis for
        **{format_date(settings[0])}**, based on the SNCB/NMBS GTFS feed released on
        **{format_date(settings[1])}**.

        The hosted version reads the SQL result files committed with the project.
        This keeps the portfolio dashboard fast and reproducible without uploading
        the large GTFS ZIP or local SQLite database.

        To update the analysis, clone the project and run:

        ```powershell
        python ingest.py --date YYYY-MM-DD --download
        python run_analysis.py
        streamlit run dashboard.py
        ```

        The ingestion pipeline, normalized schema, analytical SQL, generated reports,
        setup instructions, and limitations are available in the
        [GitHub repository]({GITHUB_URL}).

        Data is provided through the public SNCB/NMBS developer portal and open-data
        services. Thanks to SNCB/NMBS for making the GTFS feed available. Developers
        can consult the [Belgian Mobility data portal](https://data.belgianmobility.io/en/data.html)
        for documentation and access. The optional local liveboard uses the public
        [iRail API](https://docs.irail.be/).

        **Important:** the hosted report is a dated schedule snapshot. It does not
        refresh automatically. Running the pipeline locally downloads the current
        feed and recreates the reports for a covered date.
        """
    )

st.markdown(
    """
    <div style="margin-top:4rem;padding-top:1.2rem;border-top:1px solid #26384e;color:#71839a;font-size:.78rem;">
        RailPulse · Schedule analysis powered by SQLite ·
        <a href="https://github.com/IkarusV/Belgian-transit-SQL-analysis" target="_blank" style="color:#91a2b8;">View source on GitHub</a>
    </div>
    """,
    unsafe_allow_html=True,
)
