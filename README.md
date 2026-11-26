# mentor-agent-fusion

Same schema, different meaning.

Two businesses can share an identical database schema, down to the column
names, and still use it in very different ways. A five-person shop leaves half
the fields empty and writes everything into a notes column. An enterprise runs
the status column as a strict state machine. A third tenant repurposes a field
for something its name never suggested. The columns match; the data does not
mean the same thing.

This repo tests whether agentic products can cope with that.

## Layout

| Folder | What it holds |
| --- | --- |
| [`datasets/`](datasets/README.md) | Synthetic ("faux") datasets. One fixed schema, many usage profiles that fill it differently. |
| [`agents/`](agents/README.md) | Agentic products that try to generalize across those profiles. |

## How the two halves fit

1. **One schema.** Tables and column names are identical for every dataset. The
   schema's column descriptions are the *nominal* meaning: what the column is
   officially for.
2. **Many profiles.** A profile describes how one kind of business actually
   fills the schema: which fields it skips, overloads, or repurposes, what
   values and units it uses, and how large and messy it is. Profiles change how
   columns are used, never which columns exist.
3. **Agents see the schema and the data, not the profile.** An agent has to work
   out from the rows how this tenant uses its columns.
4. **Ground truth stays with the dataset.** Each profile ships questions with
   expected answers, plus a machine-readable note of what each column really
   means for that tenant. Agents cannot read these; evaluation can.
5. **Held-out profiles.** Some profiles are kept away from agent development, so
   a score measures generalization and not tuning to known tenants.

## Status

Scaffold only. The business domain for the shared schema is not chosen yet, and
no generators or agents exist.
