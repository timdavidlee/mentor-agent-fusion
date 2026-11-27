# datasets

One synthetic database of machinery dealers. Every tenant shares the schema;
tenants differ in the rule they use to decide each business concept.

## Where things are

| Path | What it is |
| --- | --- |
| [`design/schema.sql`](design/schema.sql) | The 17 tables, with each column's nominal meaning as a comment. The source of truth for the schema. |
| [`design/concepts.md`](design/concepts.md) | The 17 concepts, their three rules each (as SQL), and the tenant population. |
| [`design/generator-spec.md`](design/generator-spec.md) | How the generator is built and how to tell it is right. |
| [`generator/`](generator/) | The generator package and the `dealer-gen` CLI. Fill rules so far: [`FILL_RULES.md`](generator/FILL_RULES.md). |
| [`query_engine/`](query_engine/) | DuckDB views over the visible output; what agents query through. |
| `generated/` | Output. Git-ignored. |
| [`tests/`](tests/) | Tests for the generator, schema and query engine. |

## The idea in brief

- **Concepts and rules.** For each concept (rental fleet unit, booked sale,
  sales region, ...) a tenant uses one of three rules: the nominal field, the
  field plus tenant-specific codes, or a combination across tables. One rule
  per concept, for every row, location and year.
- **Truth first.** The generator simulates what really happened, then writes
  the columns so the tenant's own rule reproduces that truth exactly and the
  other rules come out wrong by a measured amount.
- **Seen and held-out tenants.** Seen tenants may be used while building
  agents. Held-out tenants are only for scoring; don't inspect them.

## Output

```
generated/
  seen/      visible/  hidden/
  held_out/  visible/  hidden/
```

- `visible/` is one Parquet file per table, all tenants of that split, with
  `tenant_id`. This is everything an agent may read.
- `hidden/` holds the ground truth: tenant specs, each tenant's rule per
  concept as runnable SQL, column usage, per-row truth labels, and questions
  with answers. Details in
  [generator-spec.md section 8](design/generator-spec.md#8-output-and-ground-truth).

## Generating and checking

```bash
uv run dealer-gen generate
```

```bash
uv run dealer-gen check
```

`generate` takes `--seed` and `--out`; the same seed gives byte-identical
output. It runs the acceptance checks afterwards unless given `--no-check`.

## Querying

```python
from query_engine import QueryEngine

with QueryEngine("seen", tenant_id=7) as db:
    db.list_tables()
    db.describe("equipment")
    db.run_sql("SELECT count(*) FROM equipment")
```

`QueryEngine` is scoped to one tenant, runs only read-only statements, and
cannot reach `hidden/`. `query_engine.connect()` gives a raw DuckDB connection
for development, optionally tenant-scoped.

## Rules for the generator

- **Deterministic.** Same master seed, same bytes.
- **Output stays out of git.** Commit the code that makes the data, not the
  data.
- **Visible and hidden output are separate directories**, so the hidden part
  can never be handed over by accident.
