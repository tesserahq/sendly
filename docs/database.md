# Database Design

Sendly stores a large amount of structured and semi-structured data coming from different sources such as Jira, GitHub, and other services. This data is written frequently and queried for summaries, project updates, and dashboards.

## Choice of Database

We use **PostgreSQL** as the primary database. PostgreSQL is a mature, reliable, and flexible relational database that provides strong consistency guarantees, rich indexing options, and support for JSONB when storing unstructured payloads.

The development team is highly experienced with PostgreSQL, which lowers the operational and learning curve. We prioritize data-driven decision making: instead of choosing technology only for potential future needs, we **select the tools that fit today’s requirements while keeping the system flexible enough to evolve if conditions change**.

Advantages of PostgreSQL for Sendly:
- Native partitioning to handle growing data volumes.
- BRIN and GIN indexes for efficient time-based and text-based queries.
- Materialized views to support aggregated reporting.
- Broad ecosystem support, easy integration with application frameworks, and strong operational tooling.

## Future Alternatives

If Sendly’s data volume or query patterns grow beyond what vanilla PostgreSQL can efficiently handle, we will consider **TimescaleDB**, a PostgreSQL extension optimized for time-series workloads. 

Advantages of TimescaleDB:
- Hypertables for automatic time-based partitioning and chunk management.
- Compression to reduce storage requirements for historical data.
- Continuous aggregates for incrementally maintained rollups.
- Native retention and reordering policies for lifecycle management.

### Migration Path

Since TimescaleDB builds on top of PostgreSQL, migration is straightforward:
1. Convert the `entries` table into a hypertable partitioned by time.
2. Define retention and compression policies.
3. Replace materialized views with continuous aggregates where needed.

This approach allows Sendly to start simple with PostgreSQL, while leaving open a clear upgrade path if scale demands it.