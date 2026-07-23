# SQL and Database Theory

## 1. General database types

### SQL and NoSQL

An SQL database stores data in related tables with a fixed schema. We query it with SQL. Examples are SQLite, PostgreSQL, and MySQL.

A NoSQL database can store data as documents, key-value pairs, graphs, or wide columns. It is useful when the data changes shape often or has to be spread over many servers.

### Other database engines

- A graph database stores nodes and relationships. It is useful for social networks or route connections.
- A vector database stores numeric embeddings. It is useful for similarity searches.
- A time-series database is made for measurements collected over time.
- SQLite is a relational database stored in one local file. It is simple and good for this project.

### Why SQLite cannot handle 50 writers well

SQLite locks the database file during writes. Many scraper scripts writing at the same time would wait for the lock or fail with `database is locked`. PostgreSQL would be a better choice because it handles many connections and concurrent writes.

## 2. Relational schema and data modeling

### Data model

A data model describes what we store, the fields each object has, and how objects are related. In RailPulse, trips belong to routes and stop times connect trips to stops.

### Relationship types

- One-to-one: one vehicle has one current technical record.
- One-to-many: one route has many trips.
- Many-to-many: many trips visit many stops. `stop_times` is the table between them.

### Normalization

Normalization separates repeated data into related tables. It avoids storing the same route name in every stop time. RailPulse is normalized because routes, trips, stops, calendars, and stop times each have their own table and keys.

### Primary, foreign, and unique keys

- A primary key identifies one row. `trips.trip_id` is an example.
- A foreign key points to a row in another table. `trips.route_id` points to `routes.route_id`.
- A unique key prevents duplicate values but is not the table's main identifier.

Physically, an index is normally created for a primary or unique key. A foreign key is mainly an integrity rule, so indexing it separately can make joins faster.

## 3. Analytical modeling

### Fact and dimension tables

A fact table stores events or measurements. A dimension table describes the objects around those events. `stop_times` is close to a fact table. `routes` and `stops` are dimensions.

### Star and snowflake schemas

A star schema has one fact table connected directly to dimension tables. A snowflake schema normalizes dimensions into more related tables. A star is simpler for reporting. A snowflake reduces repeated data.

## 4. Guardrails

### ACID

- Atomicity: all changes in a transaction happen or none happen.
- Consistency: constraints keep the database valid.
- Isolation: unfinished transactions do not interfere with each other.
- Durability: committed data stays saved.

If the GTFS import fails halfway through a transaction, a rollback prevents a half-loaded table from being accepted.

### CAP theorem

CAP concerns distributed systems. During a network split, a distributed database has to favor consistency or availability. SQLite is one local file, so CAP does not directly describe it. If iRail is offline, the existing SQLite data stays consistent but no new live snapshot is available.

## 5. Database objects and queries

### View, window function, and subquery

- A view saves a query under a name. RailPulse uses `active_services` as a view.
- A window function calculates across related rows without combining them into one row. `ROW_NUMBER()` finds the first stop of each trip.
- A subquery is a query inside another query. It is useful for a temporary result needed in one place.

### Index scan and index seek

An index scan reads many or all entries in an index. An index seek jumps directly to matching entries. A seek is normally faster when the filter is selective.

### SARGable filters

A SARGable filter lets the database use an index directly. This can use an index on `scheduled_time`:

```sql
WHERE scheduled_time >= '2026-01-01'
  AND scheduled_time < '2027-01-01'
```

This makes SQLite calculate a function for every row and can stop it using the index well:

```sql
WHERE strftime('%Y', scheduled_time) = '2026'
```

## 6. Query performance

Joining to a grouped subquery can create a large temporary result in memory. A window function can mark the newest row while keeping the original rows:

```sql
WITH ranked_logs AS (
    SELECT
        logs.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY date DESC
        ) AS row_number
    FROM logs
)
SELECT *
FROM ranked_logs
WHERE row_number = 1;
```

For a very large reused result, a temporary table with an index can be clearer and faster. The right choice depends on the number of rows and how often the result is reused.
