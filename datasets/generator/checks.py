"""Acceptance checks (spec section 9), run against a generated output directory.

Definitions used here (the spec leaves them open):

- *Relevant rows* for a wrong rule are all of the tenant's rows at the concept's grain.
  Product line rule 3 labels sales orders, so it is compared through the order's
  equipment lines: one row per (order, equipment line), against the unit's truth.
- A wrong rule must disagree with the truth on 5% to 40% of relevant rows and change the
  concept's first question's answer by at least 5% (in at least one group). No rule is
  exempt from the 40% cap.
"""

import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from generator import ground_truth
from generator.concepts import CONCEPTS
from generator.config import SPLITS, GeneratorConfig
from generator.population import TenantSpec
from generator.render import HABIT_COLUMNS, relied_columns
from generator.schema import TABLES
from generator.schema.sql_parser import parse_schema_sql

MIN_WRONG, MAX_WRONG, MIN_ANSWER_CHANGE = 0.05, 0.40, 0.05
_FK_RE = re.compile(r"REFERENCES (\w+) \((\w+)\)")


@dataclass
class Result:
    check: str
    tenant: str
    ok: bool
    detail: str


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)

    def add(self, check: str, tenant: str, ok: bool, detail: str = "") -> None:
        self.results.append(Result(check, tenant, ok, detail))

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    def failures(self) -> list[Result]:
        return [r for r in self.results if not r.ok]

    def text(self) -> str:
        lines = []
        for r in self.results:
            mark = "PASS" if r.ok else "FAIL"
            lines.append(f"[{mark}] {r.check:<22} {r.tenant:<5} {r.detail}")
        n_fail = len(self.failures())
        lines.append(f"{len(self.results) - n_fail} passed, {n_fail} failed")
        return "\n".join(lines)


# ------------------------------------------------------------------ loading
@dataclass
class Output:
    root: Path
    tables: dict[str, pd.DataFrame]  # all splits, all tenants
    specs: dict[int, TenantSpec]
    split_of: dict[int, str]
    truth: dict[str, pa.Table]  # concept -> all tenants
    questions: list[dict[str, Any]]
    master_seed: int

    @classmethod
    def load(cls, root: Path) -> "Output":
        tables, truth_parts = {}, {}
        specs, split_of, questions, seed = {}, {}, [], 0
        for table in TABLES:
            parts = [pq.read_table(root / s / "visible" / f"{table}.parquet") for s in SPLITS]
            tables[table] = pa.concat_tables(parts).to_pandas()
        for split in SPLITS:
            hidden = root / split / "hidden"
            for line in (hidden / "tenants.jsonl").read_text().splitlines():
                spec = TenantSpec.model_validate_json(line)
                specs[spec.tenant_id], split_of[spec.tenant_id] = spec, split
            questions += [
                json.loads(q) for q in (hidden / "questions.jsonl").read_text().split("\n") if q
            ]
            seed = json.loads((hidden / "run.json").read_text())["master_seed"]
            for path in sorted((hidden / "truth").glob("*.parquet")):
                truth_parts.setdefault(path.stem, []).append(pq.read_table(path))
        truth = {k: pa.concat_tables(v) for k, v in truth_parts.items()}
        return cls(root, tables, specs, split_of, truth, questions, seed)

    def frames(self, tenant_id: int) -> ground_truth.Frames:
        out = {}
        for name, df in self.tables.items():
            df = df[df["tenant_id"] == tenant_id].reset_index(drop=True)
            out[name] = df
        return _floats(out)

    def truth_of(self, tenant_id: int) -> ground_truth.Truth:
        return ground_truth.truth_from_tables(self.truth, tenant_id)


def _floats(frames: ground_truth.Frames) -> ground_truth.Frames:
    for name, df in frames.items():
        for col in TABLES[name].pg_columns:
            if col.data_type.startswith("NUMERIC"):
                df[col.name] = df[col.name].astype(float)
    return frames


def connect(root: Path) -> duckdb.DuckDBPyConnection:
    """DuckDB over the visible output only: rules never see the hidden truth."""
    con = duckdb.connect()
    for table in TABLES:
        files = ", ".join(f"'{root / s / 'visible' / f'{table}.parquet'}'" for s in SPLITS)
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet([{files}])")
    return con


# -------------------------------------------------------------- rule labels
def rule_ids(con: duckdb.DuckDBPyConnection, sql: str) -> list[tuple[Any, ...]]:
    return con.execute(sql).fetchall()


def compare_rule(
    con: duckdb.DuckDBPyConnection,
    out: Output,
    tenant_id: int,
    concept: str,
    rung: int,
    sql: str,
) -> tuple[int, int]:
    """(rows that disagree with the truth, relevant rows) for one rule at one tenant."""
    c = CONCEPTS[concept]
    truth = out.truth_of(tenant_id)[concept]
    rows = rule_ids(con, sql)
    table, _ = c.rule_grain(rung)
    if c.kind == "bucket":
        chosen = {r[0] for r in rows}
        wrong = sum((i in chosen) != bool(v) for i, v in truth.items())
        wrong += len(chosen - set(truth))  # ids outside the grain would be a bug too
        return wrong, len(truth)
    labels = {r[0]: r[1] for r in rows}
    if table == c.grain:
        wrong = sum(labels.get(i) != v for i, v in truth.items())
        return wrong, len(truth)
    # product line, rule 3: compare each order's line with its units' truth
    sol = out.tables["sales_order_line"]
    sol = sol[(sol["tenant_id"] == tenant_id) & (sol["line_type"] == "equipment")]
    pairs = list(zip(sol["sales_order_id"], sol["equipment_id"], strict=True))
    wrong = sum(labels.get(so) != truth[eq] for so, eq in pairs)
    return wrong, len(pairs)


def run_question(con: duckdb.DuckDBPyConnection, sql: str, answer_type: str) -> Any:
    rows = con.execute(sql).fetchall()
    if answer_type == "table":
        return {("" if k is None else str(k)): float(v) for k, v in rows}
    return float(rows[0][0] or 0)


# ------------------------------------------------------------------- checks
def check_deterministic(out: Output, report: Report) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        again = GeneratorConfig(master_seed=out.master_seed).make_in_dir(Path(tmp))
        mine = sorted(p.relative_to(out.root) for p in out.root.rglob("*") if p.is_file())
        theirs = sorted(p.relative_to(again) for p in again.rglob("*") if p.is_file())
        differ = [
            p
            for p in mine
            if p not in theirs or (out.root / p).read_bytes() != (again / p).read_bytes()
        ]
        ok = mine == theirs and not differ
        report.add("1 deterministic", "all", ok, f"{len(mine)} files; differing: {differ[:5]}")


def check_schema(out: Output, report: Report) -> None:
    parsed = parse_schema_sql()
    problems = []
    for name, defn in TABLES.items():
        sql_cols = [(c.name, c.data_type) for c in parsed[name].columns]
        py_cols = [(c.name, c.data_type) for c in defn.pg_columns]
        if sql_cols != py_cols:
            problems.append(f"{name}: python definition differs from schema.sql")
        expected = defn.arrow_schema()
        for split in SPLITS:
            got = pq.read_schema(out.root / split / "visible" / f"{name}.parquet")
            if got.names != expected.names or got.types != expected.types:
                problems.append(f"{split}/{name}: parquet schema differs")
    if set(parsed) != set(TABLES):
        problems.append("table sets differ")
    report.add("2 schema identity", "all", not problems, "; ".join(problems) or "17 tables match")


def _date_cols(table: str) -> list[str]:
    return [c.name for c in TABLES[table].pg_columns if c.data_type == "DATE"]


def check_integrity(out: Output, report: Report) -> None:
    t = out.tables
    problems: list[str] = []
    # surrogate ids unique across all tenants
    for name, defn in TABLES.items():
        if t[name].duplicated(subset=defn.primary_key).any():
            problems.append(f"{name}: duplicate primary key")
    # every foreign key resolves, to a row of the same tenant
    for name, defn in TABLES.items():
        for col in defn.pg_columns:
            m = _FK_RE.search(col.modifiers)
            if not m or col.name == "tenant_id":
                continue
            ref_table, ref_col = m.groups()
            ref = t[ref_table].set_index(ref_col)["tenant_id"]
            vals = t[name][[col.name, "tenant_id"]].dropna(subset=[col.name])
            owner = vals[col.name].map(ref)
            if owner.isna().any():
                problems.append(f"{name}.{col.name}: dangling reference")
            elif (owner != vals["tenant_id"]).any():
                problems.append(f"{name}.{col.name}: reference crosses tenants")
    report.add(
        "3 integrity: keys", "all", not problems, "; ".join(problems) or "ids and references ok"
    )
    for tid, spec in out.specs.items():
        report.add("3 integrity: events", spec.tenant_code, *_event_integrity(out, tid, spec))


def _event_integrity(out: Output, tid: int, spec: TenantSpec) -> tuple[bool, str]:
    f = out.frames(tid)
    truth = out.truth_of(tid)
    problems: list[str] = []
    for name in TABLES:
        # a due date is a scheduled date, not an event, so it may fall after the as-of date
        for col in (c for c in _date_cols(name) if c != "due_date"):
            if (f[name][col].dropna() > spec.as_of_date).any():
                problems.append(f"{name}.{col} after as-of")

    def forwards(df: pd.DataFrame, a: str, b: str, label: str) -> None:
        both = df.dropna(subset=[a, b])
        if (both[a] > both[b]).any():
            problems.append(label)

    forwards(f["rental_contract"], "start_date", "end_date", "rental ends before it starts")
    forwards(f["work_order"], "opened_date", "closed_date", "work order closes before opening")
    forwards(f["invoice"], "invoice_date", "due_date", "invoice due before issue")
    forwards(f["warranty_claim"], "submitted_date", "paid_date", "claim paid before submitted")
    pay = f["payment"].merge(f["invoice"], on="invoice_id", suffixes=("", "_inv"))
    forwards(pay, "invoice_date", "payment_date", "payment before invoice")
    if (pay["status"] == "void").any():
        problems.append("payment on a void invoice")
    paid = f["payment"].groupby("invoice_id")["amount"].sum()
    totals = f["invoice"].set_index("invoice_id")["total_amount"]
    if (paid > totals.reindex(paid.index) + 0.005).any():
        problems.append("payments exceed invoice total")
    so = f["sales_order"].set_index("sales_order_id")
    inv = f["invoice"].dropna(subset=["sales_order_id"])
    inv_order_date = inv["sales_order_id"].map(so["order_date"])
    if (inv["invoice_date"] < inv_order_date).any():
        problems.append("invoice before its order")
    eq = f["equipment"].set_index("equipment_id")
    sol = f["sales_order_line"].dropna(subset=["equipment_id"])
    sol = sol.assign(order_date=sol["sales_order_id"].map(so["order_date"]))
    rented = f["rental_contract"]
    if (rented["start_date"] < rented["equipment_id"].map(eq["acquired_date"])).any():
        problems.append("unit rented before acquired")
    acquired = sol["equipment_id"].map(eq["acquired_date"])
    if (sol["order_date"] < acquired).any():
        problems.append("unit ordered before acquired")
    # rentals: one open at a time, never overlapping, never after the sale
    rc = f["rental_contract"].sort_values(["equipment_id", "start_date"])
    if (rc.groupby("equipment_id")["status"].apply(lambda s: (s == "open").sum()) > 1).any():
        problems.append("unit on two open rentals")
    ends = rc["end_date"].where(rc["end_date"].notna(), spec.as_of_date)
    prev_end = ends.groupby(rc["equipment_id"]).shift()
    if (rc["start_date"] < prev_end).dropna().any():
        problems.append("overlapping rentals")
    booked_lines = sol[
        (sol["line_type"] == "equipment")
        & sol["sales_order_id"].map(truth["booked_sale"]).astype(bool)
    ]
    sold_on = booked_lines.groupby("equipment_id")["order_date"].max()
    rent_after = rc["start_date"] > rc["equipment_id"].map(sold_on)
    if rent_after.fillna(False).astype(bool).any():
        problems.append("rented after sold")
    # owner_customer_id: the buyer on the unit's latest booked sale, else the dealer
    expected = (
        booked_lines.sort_values("order_date")
        .groupby("equipment_id")["sales_order_id"]
        .last()
        .map(so["customer_id"])
    )
    for eid, row in eq.iterrows():
        if pd.isna(row["acquired_date"]):
            if pd.isna(row["owner_customer_id"]):
                problems.append(f"customer unit {eid} without owner")
                break
            continue
        want = expected.get(eid)
        have = None if pd.isna(row["owner_customer_id"]) else int(row["owner_customer_id"])
        if (None if want is None else int(want)) != have:
            problems.append(f"unit {eid} owner {have} != {want}")
            break
    return not problems, "; ".join(problems) or "invariants hold"


def check_own_rules(con: duckdb.DuckDBPyConnection, out: Output, report: Report) -> None:
    for tid, spec in out.specs.items():
        for name, (rung, sql) in ground_truth.own_rules(spec).items():
            wrong, n = compare_rule(con, out, tid, name, rung, sql)
            report.add(
                "4 own rule exact",
                spec.tenant_code,
                wrong == 0,
                f"{name} rung {rung}: {wrong}/{n} rows differ",
            )


def wrong_rule_candidates(
    out: Output, spec: TenantSpec, concept: str
) -> tuple[list[tuple[str, int, str]], list[str]]:
    """(label, rung, sql) for the rules that must be wrong, and n/a notes."""
    c = CONCEPTS[concept]
    own = spec.concepts[concept]
    own_sql = c.rule_sql(own.rung, own.params, spec.tenant_id)
    must_plain = {1: [3], 2: [1, 3], 3: [1]}[own.rung]
    must_other = {1: 3, 2: 3, 3: 2}[own.rung]
    out_rules: list[tuple[str, int, str]] = []
    notes: list[str] = []
    seen_sql = {own_sql}
    for rung in must_plain:
        if rung not in c.plain_rungs:
            notes.append(f"plain rule {rung} n/a (needs tenant lists)")
            continue
        sql = c.rule_sql(rung, {}, spec.tenant_id)
        if sql not in seen_sql:
            seen_sql.add(sql)
            out_rules.append((f"plain rule {rung}", rung, sql))
    others = [
        s
        for s in out.specs.values()
        if s.tenant_id != spec.tenant_id and s.concepts[concept].rung == must_other
    ]
    if not others:
        notes.append(f"no other tenant on rule {must_other}")
    for other in others:
        oc = other.concepts[concept]
        sql = c.rule_sql(oc.rung, oc.params, spec.tenant_id)
        if sql not in seen_sql:
            seen_sql.add(sql)
            out_rules.append((f"{other.tenant_code}'s rule {oc.rung}", oc.rung, sql))
        else:
            notes.append(f"{other.tenant_code}'s rule {oc.rung} same as a plain rule")
    return out_rules, notes


def check_wrong_rules(con: duckdb.DuckDBPyConnection, out: Output, report: Report) -> None:
    for tid, spec in out.specs.items():
        rules = ground_truth.own_rules(spec)
        for concept in spec.concepts:
            q = ground_truth.primary_question(concept)
            truth_answer = q.answer(spec, out.frames(tid), out.truth_of(tid))
            candidates, notes = wrong_rule_candidates(out, spec, concept)
            for label, rung, sql in candidates:
                wrong, n = compare_rule(con, out, tid, concept, rung, sql)
                rate = wrong / n if n else 0.0
                swapped = dict(rules) | {concept: (rung, sql)}
                answer = run_question(con, q.sql(spec, swapped), q.answer_type)
                change = ground_truth.answer_change(truth_answer, answer)
                ok = MIN_WRONG <= rate <= MAX_WRONG and change >= MIN_ANSWER_CHANGE
                detail = (
                    f"{concept} vs {label}: {rate:.1%} of {n} rows wrong; "
                    f"answer change {change:.1%}"
                )
                report.add("5 wrong rules wrong", spec.tenant_code, ok, detail)
            for note in notes:
                report.add("5 wrong rules wrong", spec.tenant_code, True, f"{concept}: {note}")


def check_answers(con: duckdb.DuckDBPyConnection, out: Output, report: Report) -> None:
    templates = {q.qid: q for q in ground_truth.QUESTIONS}
    for q in out.questions:
        spec = out.specs[q["tenant_id"]]
        tmpl = templates[q["question_id"]]
        from_truth = tmpl.answer(spec, out.frames(spec.tenant_id), out.truth_of(spec.tenant_id))
        from_sql = run_question(con, q["sql"], q["answer_type"])
        ok = ground_truth.answers_agree(
            from_truth, from_sql, q["measure"]
        ) and ground_truth.answers_agree(q["answer"], from_sql, q["measure"])
        report.add(
            "6 answers agree",
            spec.tenant_code,
            ok,
            f"{q['question_id']}: {ground_truth.round_answer(ground_truth.normalise(from_sql))}",
        )


def check_habits(out: Output, report: Report) -> None:
    for spec in out.specs.values():
        relied = relied_columns(spec)
        clash = relied & set(HABIT_COLUMNS)
        usage = [
            json.loads(line)
            for line in (out.root / out.split_of[spec.tenant_id] / "hidden" / "column_usage.jsonl")
            .read_text()
            .splitlines()
        ]
        neglected = {
            f"{u['table']}.{u['column']}"
            for u in usage
            if u["tenant_id"] == spec.tenant_id and u["usage"] == "neglected"
        }
        bad = sorted(clash | (relied & neglected))
        detail = (
            f"rules read {len(relied)} columns, none touched by habits; "
            "checks 4-6 ran on final output"
        )
        report.add(
            "7 habits kept rules",
            spec.tenant_code,
            not bad,
            f"touched or neglected: {bad}" if bad else detail,
        )


def check_separation(out: Output, report: Report) -> None:
    banned = {s.archetype for s in out.specs.values()} | {"rung", "truth", "held_out", "seen"}
    banned |= set(CONCEPTS)
    problems = []
    for split in SPLITS:
        for name, defn in TABLES.items():
            table = pq.read_table(out.root / split / "visible" / f"{name}.parquet")
            if table.column_names != defn.column_names:
                problems.append(f"{split}/{name}: extra or missing columns")
            for col in table.column_names:
                if pa.types.is_string(table.schema.field(col).type):
                    values = {v.lower() for v in table.column(col).to_pylist() if v}
                    if values & banned:
                        problems.append(f"{split}/{name}.{col} holds a hidden label")
    by_split = {
        split: set(
            pq.read_table(out.root / split / "visible" / "tenant.parquet")
            .column("tenant_id")
            .to_pylist()
        )
        for split in SPLITS
    }
    if by_split["seen"] & by_split["held_out"]:
        problems.append("a tenant is in both splits")
    for split in SPLITS:
        for name in TABLES:
            ids = set(
                pq.read_table(out.root / split / "visible" / f"{name}.parquet")
                .column("tenant_id")
                .to_pylist()
            )
            if not ids <= by_split[split]:
                problems.append(f"{split}/{name} has rows of another split's tenant")
    detail = f"seen {sorted(by_split['seen'])}, held-out {sorted(by_split['held_out'])}"
    report.add("8 separation", "all", not problems, "; ".join(problems) or detail)


def run_checks(root: Path, *, deterministic: bool = True) -> Report:
    out = Output.load(root)
    con = connect(root)
    report = Report()
    if deterministic:
        check_deterministic(out, report)
    check_schema(out, report)
    check_integrity(out, report)
    check_own_rules(con, out, report)
    check_wrong_rules(con, out, report)
    check_answers(con, out, report)
    check_habits(out, report)
    check_separation(out, report)
    return report
