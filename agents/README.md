# agents

Agents that work over the dealer database in [`../datasets/`](../datasets/README.md)
and are judged on how well they hold up across tenants.

## Contract

An agent is given:

- a tenant id, and read-only SQL access to that tenant through
  [`QueryEngine`](../datasets/README.md#querying)
- the shared schema, including each column's nominal description (as column
  comments)
- a question about that tenant, worded the same for every tenant

An agent is never given:

- anything under `datasets/generated/*/hidden/`: the tenant's rules, truth
  labels, column usage, or expected answers
- the tenant's archetype or spec
- anything from a held-out tenant during development

So an agent cannot trust a column name or its description. It has to look at
the rows, work out which rule this tenant uses for each concept the question
needs, and answer on that basis. Agents are not expected to recover every
rule.

## What "generalizes" means here

One agent, unchanged, is run against every tenant. It is scored per tenant,
with seen and held-out tenants reported separately. An agent that does well on
seen tenants and badly on held-out ones has learned the tenants, not the
problem. No per-tenant branches, prompts, or configuration.

## Status

No agents yet. Each agent will get its own subfolder here.
