# mentor-agent-fusion

Same schema, different meaning.

Two businesses can share an identical database schema, down to the column
names, and still decide the same business question in different ways. One
dealer marks a rental unit with a single flag. Another uses the flag plus a
list of stock-number prefixes. A third ignores the flag and goes by which
location holds the unit. The columns match; the query that answers "how many
rental units do we have?" does not.

This repo tests whether agents can cope with that.

## Layout

| Folder | What it holds |
| --- | --- |
| [`datasets/`](datasets/README.md) | A synthetic multi-tenant database, its generator, and a query engine agents use to read it. |
| [`agents/`](agents/README.md) | Agents that try to generalize across tenants. |

## How the two halves fit

1. **One schema, one database.** The domain is a machinery sales and service
   dealer: 17 tables ([`schema.sql`](datasets/design/schema.sql)), each
   carrying `tenant_id`. About 250 tenants share the database. Each column's
   comment is its *nominal* meaning: what it is officially for.
2. **Concepts with three rules.** 17 business concepts (product line, rental
   fleet unit, warranty work, active customer, ...) can each be decided by one
   of three rules: one field; one field plus tenant codes; or a combination
   across tables. A tenant picks one rule per concept and uses it on every
   row and its whole history. See [`concepts.md`](datasets/design/concepts.md).
3. **Agents get a tenant id, not the rules.** An agent queries one tenant
   through the read-only query engine and has to work out from the rows which
   rule that tenant uses.
4. **Ground truth is hidden.** The generator also writes each tenant's rules,
   per-row truth labels, column usage, and questions with answers. Agents
   cannot read these; evaluation can.
5. **Held-out tenants.** Some tenants are kept away from agent development, so
   a score measures generalization and not tuning to known tenants.

## How to run

```bash
uv sync
```

```bash
uv run dealer-gen generate
```

```bash
uv run pytest
```

`generate` writes `datasets/generated/` (git-ignored) and runs the acceptance
checks. `uv run dealer-gen check` re-checks existing output.

## Status

Generator milestone 1 is done: two hand-written tenants and four concepts, end
to end with ground truth and checks. The other concepts, the drawn population
of about 250 tenants, and scale come next
([milestones](datasets/design/generator-spec.md#10-milestones)). No agents
exist yet.
