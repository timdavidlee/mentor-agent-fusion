# datasets

Synthetic datasets that all share one schema and differ only in how that schema
is used.

## The pieces

**Schema.** Defined once and shared by every dataset: the same tables, the same
column names, the same types. Each column carries a description of its nominal
meaning, the thing it is officially for. That description is what an agent is
told; it is not a promise about what any tenant actually stores there.

**Profiles.** A profile is one way of using the schema, modelled on a kind of
business. It may differ from another profile in:

- which columns are filled, left null, or filled with placeholders
- which columns are overloaded or repurposed (free text holding structured
  facts, a status field used as a tag, a date field meaning something else)
- vocabulary, units, and granularity of values
- volume, history length, and how consistent the data entry is

A profile never adds, removes, or renames a column.

**Ground truth.** Each profile also produces what evaluation needs:

- questions with expected answers, computed from the generator's own knowledge
  of the data
- a machine-readable record of what each column really means for that tenant

Ground truth is written separately from the data an agent is given, so an agent
run can be pointed at the data alone.

**Seen and held-out profiles.** Profiles are split into two groups. Seen
profiles may be used while building and tuning agents. Held-out profiles are
only used for scoring, and nobody working on an agent should inspect them.

## Rules for generators

- **Deterministic.** Every generator takes a seed, and the same seed and
  profile give the same data.
- **Output stays out of git.** Generated data goes to `datasets/generated/`,
  which is ignored. Commit the code that makes the data, not the data.
- **Agent-visible and hidden output are separate directories**, so the hidden
  part can never be handed over by accident.

## Status

Nothing is generated yet. The domain for the shared schema is still to be
chosen, so no schema or profile files exist.
