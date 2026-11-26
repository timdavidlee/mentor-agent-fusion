# Generator build spec (draft)

Status: **proposed.** Items marked _(default)_ are choices made on the user's
behalf that the user has not confirmed; see "Open decisions" at the end.

Read first: [`schema.sql`](schema.sql) (17 tables, every one carrying
`tenant_id`) and [`concepts.md`](concepts.md) (17 concepts, three rules each,
the tenant population). This file says how to build the generators and how to
tell they are right. It does not repeat those two files.

## 1. What is being built

A deterministic generator that produces one database of about 250 tenants. All
tenants share the schema exactly. Each tenant decides each of the 17 business
concepts by its own rule, and uses that one rule for all its rows and its whole
history. Alongside the data, the generator emits hidden ground truth: each
tenant's rules, per-row truth labels, and questions with answers.

Out of scope: agents, anything under `agents/`, and loading into a live
Postgres server.

## 2. Stack and layout

_(default)_ Follow the conventions of the user's existing generator repo
(`adorable-thunder-data-generators`), as standalone code here, with no
dependency on that repo:

- Python >= 3.13, `uv`, `hatchling`, `pydantic` v2, `pandas`, `pyarrow`,
  `typer` for the CLI, `pytest`, `ruff` (line length 100), `pyright`.
- Top-level entry point is a Pydantic `GeneratorConfig` with
  `.make() -> dict[str, pd.DataFrame]` (one frame per table) and
  `.make_in_dir()` writing parquet.
- Each table has a `create_pg_sql_table_schema()` returning a
  `CreatePgTableSql`-style object whose columns carry the nominal description
  (`llm_description`). `schema.sql` is the source of truth; a test must fail
  if the Python definitions and `schema.sql` drift apart.
- _(default)_ `duckdb` as a dev dependency, used only to run rule SQL over the
  parquet output in the checks.

Proposed layout:

```
datasets/
  design/                 these specs
  generator/              the Python package
    schema/               table definitions
    population.py         archetypes, tenant specs, seen / held-out split
    simulate/             the business simulation (hidden truth)
    concepts/             one module per concept: truth, encoders, rule SQL
    render.py             truth -> schema columns, habits, planted rows
    ground_truth.py       rules, labels, questions, answers
    checks.py             the acceptance checks in section 9
    cli.py
  tests/
  generated/              git-ignored output (section 8)
```

## 3. Pipeline

For each tenant, in this order. The order matters: truth is decided before any
column is written.

1. **Draw the tenant spec** (section 4) from the master seed.
2. **Simulate the business** (section 5), given the tenant spec. The result is
   a model of entities and events with a hidden truth value for all 17
   concepts at each concept's grain (section 8). Some truths are physical
   fact (was the unit rented). Others are the tenant's own policy (when a sale
   counts, what goes into unit cost, who is an active customer), so the
   simulation reads them from the spec. The exception events that make other
   rules wrong (section 6) are simulated here as real events, not added
   afterwards.
3. **Render into the schema** (section 6). Each concept's encoder writes the
   columns it owns so that the tenant's chosen rule reproduces the truth.
4. **Apply data-entry habits**: blanks, notes usage, vocabulary, meter habits.
   Habits must never touch a column that the tenant's chosen rules rely on.
5. **Emit ground truth** (section 8).
6. **Run the checks** (section 9). A tenant that fails is a generator bug, not
   something to drop silently.

## 4. Tenant spec

One Pydantic model per tenant, written to the hidden output. It is the only
input the rest of the pipeline needs.

| Field | Meaning |
| --- | --- |
| `tenant_id`, `tenant_code`, `name` | Identity, as in the `tenant` table |
| `archetype` | One of six to eight kinds of dealer |
| `split` | `seen` or `held_out` |
| `seed` | Derived from the master seed and `tenant_id` |
| `as_of_date`, `history_years` | The tenant's "today" and how far back it goes |
| `size` | Locations, employees, units, customers, yearly volumes |
| `concepts` | For each of the 17 concepts: `rung` (1, 2 or 3) and its parameters (code lists, status lists, thresholds, location and department lists) |
| `vocabulary` | The tenant's code tables per coded column (section 7) |
| `habits` | Blank rates, notes usage, meter habit, status vocabulary |

Population rules:

- Rungs are drawn with archetype-dependent weights, not uniformly, and are not
  tied to size.
- A draw that breaks a compatibility rule (section 7) is redrawn.
- Sizes are skewed: most tenants small, a few large. _(default)_ Cap one tenant
  at about 2 million rows across all tables and the whole database at about
  25 million.
- _(default)_ 200 seen and 50 held-out. One archetype appears only in the
  held-out set. Held-out code vocabularies come from a seed supplied at run
  time and never committed, so they cannot be read from the repo.

## 5. Business simulation

The simulation produces what really happened; rendering decides how it was
typed in.

Lifecycles to model:

- **Units.** Acquired new from a manufacturer or used through trade-in or
  auction; held in stock; some join the rental fleet and are rented several
  times; most are eventually sold; sold units come back as customer-owned
  units for service, and some return later as trade-ins.
- **Sales.** Quote or order, lines (unit, attachments, parts, fees, trade-in),
  invoice, payments. Some deals are abandoned; some are financed and paid over
  months.
- **Rentals.** Contract, periodic invoices, return; some convert to a sale.
- **Service.** Work orders on customer units (repair, maintenance, inspection)
  and on dealer units (setup, reconditioning, rental repair), with labour and
  parts lines, optional warranty claim, invoice, payments.
- **Parts.** Counter sales and work-order usage draw down stock by location.
- **Customers.** Parent and child accounts, duplicates of the same business,
  dormant accounts, house and cash accounts.

Invariants, true at every tenant whatever its rules:

- Every foreign key resolves, and to a row of the same tenant.
- Surrogate ids are unique across all tenants; give each tenant its own id
  block.
- Dates run forwards (acquired, rented, returned, sold; ordered, invoiced,
  paid; opened, closed) and nothing is dated after `tenant.as_of_date`.
- A unit is never on two open rentals at once, and never rented after it is
  sold.
- Payments applied to an invoice never exceed its total.
- `equipment.owner_customer_id` is always correct (null means dealer-owned).

## 6. Rendering: what each column holds

For a concept, the columns fall into three groups: the nominal field (rule 1),
the code columns (rule 2) and the structural facts (rule 3). What a tenant
writes depends on which rule it uses:

| Tenant uses | Nominal field | Code columns | Structural facts |
| --- | --- | --- | --- |
| Rule 1 | Equals the truth on every row | The tenant's ordinary vocabulary, carrying no signal for this concept | As simulated, including exception events that disagree with the truth |
| Rule 2 | Right except on the override rows, where it holds its coarse or default value | The tenant's code list marks exactly the override rows | As simulated, including exception events that disagree with the truth |
| Rule 3 | As described under "Nominal column when ignored" in `concepts.md` | Ordinary vocabulary, no signal | Line up with the truth on every row |

The exception events are the ones listed under "Rows where rung 3 is wrong
elsewhere" in `concepts.md`. They are simulated events a real dealer would
have (a deposit invoice, rental damage billed to the renter), not random
noise.

**Which wrong rules are tested.** A tenant spec only holds parameters for the
rule the tenant uses, so "the other two rules" has no meaning by itself. The
wrong rules tested against a tenant's data are:

- the **plain rule 1**: the nominal field with its documented values and no
  tenant parameters;
- the **plain rule 3**, for concepts whose rule 3 needs no tenant lists;
- the **actual rules of other tenants** for the same concept (a sample of
  them), run unchanged against this tenant's data.

**Which of them must fail** _(default thresholds)_:

| Tenant uses | Must be wrong | May happen to be right |
| --- | --- | --- |
| Rule 1 | Rule 3 (plain, and other tenants') | Other tenants' rule 2, since it extends rule 1 |
| Rule 2 | Plain rule 1; rule 3 | Another tenant's rule 2 with overlapping codes |
| Rule 3 | Plain rule 1; other tenants' rule 2 | Another tenant's rule 3 with overlapping lists |

A rule that must be wrong has to

- disagree with the truth on between 5% and 40% of the relevant rows, and
- change the answer to that concept's question by at least 5% (for a grouped
  answer, in at least one group).

As each concept is implemented, add its exact fill rules to its section in
`concepts.md`, so the design file stays the full description.

## 7. Shared columns and compatibility

Several columns are used by more than one concept, and a row holds one value.

| Column | Concepts that use it |
| --- | --- |
| `customer.account_class` | Internal work, active customer, sales region, past-due invoice, customer as a counting unit |
| `work_order_line.operation_code` | Warranty work, service department, type of work, unit cost |
| `equipment.stock_number` | Rental fleet unit, used unit |
| `location.location_code` | Product line, service department, type of work, revenue branch |
| `work_order.department_id` | Service department, type of work |
| `work_order.work_order_type` | Warranty work, completed work order |
| `work_order.is_internal` | Internal work, unit cost |
| `invoice` links to orders and work orders | Booked sale, available to sell, completed work order, sale date |

Rules:

1. **One vocabulary per coded column per tenant.** Build each tenant's code
   table first. A single code may carry meaning for several concepts at once
   (an account class can be both "its own sales region" and "on extended
   terms"). Concepts on rule 2 select codes from that table; they do not
   invent their own.
2. **Patterns must compose.** Where two concepts at one tenant both mark the
   same column, a row must be able to be both (a used rental unit, a warranty
   maintenance line). Use different positions in the code, or explicit code
   lists, so that each rule's pattern selects exactly its intended rows. The
   `LIKE 'W%'` and `LIKE 'PM%'` patterns in `concepts.md` are examples; a
   tenant's real rule may be an explicit list.
3. **A column is either maintained or neglected at a tenant, not both.** Each
   concept and rule declares which columns it needs maintained and which it
   needs neglected. A tenant draw with a clash is redrawn. One known clash:
   completed work order on rule 2 needs `work_order.work_order_type`
   maintained, while warranty work on rule 3 needs it neglected.
4. **Exception events declare what they touch.** An exception simulated for
   one concept changes facts that other concepts' rules read. An invoice
   entered without its order link, generated to make booked sale's rule 3
   wrong, also breaks rule 3 of available to sell and of sale date. Each
   exception type lists the rules it breaks, and it is only generated at a
   tenant that uses none of them.
5. **Departments and locations are shared too.** If type of work on rule 3
   uses setup and reconditioning departments while service department on
   rule 1 reads the same column, the tenant's department list must serve both.

Deliverable before building all 17 concepts: the full compatibility table
(which rule choices cannot be combined), added to `concepts.md`.

## 8. Output and ground truth

```
datasets/generated/
  seen/
    visible/      one parquet file per table, all seen tenants, with tenant_id
    hidden/
  held_out/
    visible/
    hidden/
```

`visible/` is everything an agent may read. `hidden/` holds:

| File | Contents |
| --- | --- |
| `tenants.jsonl` | The full tenant spec (section 4) |
| `concept_rules.jsonl` | Per tenant and concept: rule number, parameters, and the rule as runnable SQL already filtered to the tenant |
| `column_usage.jsonl` | Per tenant, table and column: maintained, neglected, defaulted or repurposed, with a short note |
| `truth/<concept>.parquet` | Per-row hidden truth: `tenant_id`, the row's id, the truth value |
| `questions.jsonl` | Per tenant: question id, text, concepts involved, answer type, answer, tolerance, and the SQL that produces it |

Grain of each concept's truth (the table whose rows are labelled):

| Concept | Grain | Truth value |
| --- | --- | --- |
| Product line | `equipment` | Line name |
| Rental fleet unit | `equipment` | Yes or no |
| Available to sell | `equipment` | Yes or no |
| Warranty work | `work_order_line` | Yes or no |
| Internal work | `work_order` | Yes or no |
| Active customer | `customer` | Yes or no |
| Used unit | `equipment` | Yes or no |
| Booked sale | `sales_order` | Yes or no |
| Service department | `work_order` | Department name |
| Sales region | `sales_order` | Region name |
| Type of work | `work_order` | Type name |
| Completed work order | `work_order` | Yes or no |
| Past-due invoice | `invoice` | Yes or no |
| Unit cost | `equipment` | Amount |
| Sale date | `sales_order` | Date, null if not a sale |
| Revenue branch | `invoice` | `location_id` |
| Customer as a counting unit | `customer` | The `customer_id` it is counted as |

Product line is the one concept whose rule 3 returns a different grain (sales
orders). It is checked through the order's equipment lines: every unit on the
order must have the order's product line as its truth.

Questions:

- Written in concept language, identical wording across tenants, with explicit
  dates taken from the tenant's `as_of_date`.
- At least two question templates per concept, plus a handful that combine
  concepts (the gross-margin question combines unit cost, sale date and booked
  sale). Each records which concepts it depends on.
- Answer types: a single number, a date, or a table of key and value.
- _(default)_ Comparison: counts exact; amounts within 0.5%; tables compared
  as unordered sets with keys trimmed and lower-cased.

## 9. Acceptance checks

All must pass for every tenant, in `checks.py` and in the test suite.

1. **Deterministic.** Same master seed gives byte-identical output.
2. **Schema identity.** Every table matches `schema.sql`: same columns, order
   and types, for every tenant.
3. **Integrity.** All invariants in section 5 hold.
4. **The tenant's own rule is exact.** For every concept, running the tenant's
   rule SQL reproduces the hidden truth on every row at the concept's grain.
   Because it holds on every row, it holds for every location and every year:
   no part of a tenant follows another rule.
5. **The wrong rules are wrong enough.** The table and thresholds in section 6
   hold.
6. **Answers agree two ways.** Each answer computed from the truth labels in
   pandas equals the answer from the rule SQL in DuckDB.
7. **Habits did not break rules.** Checks 4 to 6 run on the final output,
   after habits are applied.
8. **Separation.** Nothing under `visible/` contains a rule number, a truth
   label or the archetype; held-out output shares no tenant with seen output.

## 10. Milestones

1. **Thin slice.** Two hand-written tenants (A and C from `concepts.md`, with
   C scaled down) and four concepts (product line, available to sell, internal
   work, booked sale), end to end with ground truth and all checks. Tenant C
   decides product line from departments plus locations, the pattern this
   repo exists to test. Stop for the user's review.
2. **All 17 concepts** for those two tenants, plus the compatibility table.
3. **Population.** Archetypes, 250 drawn tenants, the seen and held-out split.
4. **Scale.** Row caps, generation time, and a short usage section for
   `datasets/README.md`.

## Follow-ups outside this spec

`README.md`, `datasets/README.md` and `agents/README.md` predate these
decisions. They say the domain is not chosen, describe hand-written profiles
and per-column ground truth only, and say an agent is handed the data for one
tenant. With one shared database an agent is handed a tenant id.

## Open decisions

- Stack as in section 2, including DuckDB for checks.
- The 200 / 50 split, and holding one archetype out entirely.
- Row caps in section 4.
- Wrong-rule thresholds in section 6 and answer tolerances in section 8.
- Milestone 1's choice of tenants and concepts.
