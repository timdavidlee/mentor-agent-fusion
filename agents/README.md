# agents

Agentic products that work over the datasets in [`../datasets/`](../datasets/README.md)
and are judged on how well they hold up across usage profiles.

## Contract

An agent is given:

- the shared schema, including each column's nominal description
- the data for one tenant
- a task or question about that tenant

An agent is never given:

- the profile that generated the data, or its generation rules
- the per-tenant record of what each column really means
- the expected answers
- anything from a held-out profile during development

So an agent cannot trust a column name or its description. It has to look at
the rows, work out how this tenant uses each column, and answer on that basis.

## What "generalizes" means here

One agent, unchanged, is run against every profile. It is scored per profile,
with seen and held-out profiles reported separately. An agent that does well on
seen profiles and badly on held-out ones has learned the tenants, not the
problem. No per-profile branches, prompts, or configuration.

## Status

No agents yet. Each agent will get its own subfolder here.
