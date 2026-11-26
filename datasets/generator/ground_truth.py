"""Hidden ground truth: rules, truth labels, column usage, questions and answers."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

import pandas as pd
import pyarrow as pa

from generator.concepts import CONCEPTS
from generator.population import TenantSpec
from generator.render import HABIT_COLUMNS, relied_columns
from generator.schema import TABLES
from generator.simulate.world import World

Frames = dict[str, pd.DataFrame]  # one tenant's visible tables
Truth = dict[str, dict[int, Any]]  # concept -> row id -> truth value
Answer = float | dict[str, float]
Rules = dict[str, tuple[int, str]]  # concept -> (rung, rule SQL)

AMOUNT_TOLERANCE = 0.005  # amounts within 0.5%; counts exact


# ----------------------------------------------------------------- truth labels
def truth_table(world: World, concept: str) -> pa.Table:
    c = CONCEPTS[concept]
    labels = world.truth[concept]
    ids = sorted(labels)
    value_type = pa.bool_() if c.kind == "bucket" else pa.string()
    return pa.table(
        {
            "tenant_id": pa.array([world.spec.tenant_id] * len(ids), pa.int64()),
            c.id_column: pa.array(ids, pa.int64()),
            "truth": pa.array([labels[i] for i in ids], value_type),
        }
    )


def truth_from_tables(tables: dict[str, pa.Table], tenant_id: int) -> Truth:
    truth: Truth = {}
    for concept, table in tables.items():
        df = table.to_pandas()
        df = df[df["tenant_id"] == tenant_id]
        id_col = CONCEPTS[concept].id_column
        truth[concept] = dict(zip(df[id_col].tolist(), df["truth"].tolist(), strict=True))
    return truth


# ------------------------------------------------------------------- rules
def own_rules(spec: TenantSpec) -> Rules:
    return {
        name: (c.rung, CONCEPTS[name].rule_sql(c.rung, c.params, spec.tenant_id))
        for name, c in spec.concepts.items()
    }


def concept_rules(spec: TenantSpec) -> list[dict[str, Any]]:
    return [
        {
            "tenant_id": spec.tenant_id,
            "concept": name,
            "rung": c.rung,
            "params": c.params,
            "grain": CONCEPTS[name].rule_grain(c.rung)[0],
            "sql": CONCEPTS[name].rule_sql(c.rung, c.params, spec.tenant_id),
        }
        for name, c in spec.concepts.items()
    ]


def column_usage(spec: TenantSpec) -> list[dict[str, Any]]:
    declared: dict[str, tuple[str, str]] = {}
    for name, c in spec.concepts.items():
        declared.update(CONCEPTS[name].column_usage(c))
    relied = relied_columns(spec)
    h = spec.habits
    rates = {
        "notes": 1 - h.notes_rate,
        "meter": h.meter_blank_rate,
        "address": h.address_blank_rate,
        "serial": h.serial_blank_rate,
    }
    out: list[dict[str, Any]] = []
    for table, defn in TABLES.items():
        for col in defn.column_names:
            qualified = f"{table}.{col}"
            usage, note = "maintained", ""
            if qualified in declared:
                usage, note = declared[qualified]
            elif qualified in HABIT_COLUMNS and qualified not in relied:
                blank = rates[HABIT_COLUMNS[qualified]]
                usage = "neglected" if blank > 0.3 else "maintained"
                note = f"blank on about {blank:.0%} of rows"
            if qualified in relied and usage == "neglected":
                raise AssertionError(f"{spec.tenant_code}: {qualified} relied on but neglected")
            out.append(
                {
                    "tenant_id": spec.tenant_id,
                    "table": table,
                    "column": col,
                    "usage": usage,
                    "note": note,
                    "read_by_tenant_rule": qualified in relied,
                }
            )
    return out


# --------------------------------------------------------------- questions
def prior_year(spec: TenantSpec) -> tuple[date, date]:
    y = spec.as_of_date.year - 1
    return date(y, 1, 1), date(y, 12, 31)


def last_quarter(spec: TenantSpec) -> tuple[date, date]:
    """The last complete calendar quarter ending on or before the as-of date."""
    d = spec.as_of_date
    q = (d.month - 1) // 3
    start = date(d.year, 3 * q + 1, 1)
    end = date(d.year + (q == 3), (3 * q + 3) % 12 + 1, 1) - timedelta(days=1)
    if d < end:  # the as-of quarter is not finished: use the one before
        end = start - timedelta(days=1)
        start = date(end.year, end.month - 2, 1)
    return start, end


def label_cte(concept: str, sql: str) -> str:
    cols = "id" if CONCEPTS[concept].kind == "bucket" else "id, value"
    indented = "\n".join("    " + line for line in sql.splitlines())
    return f"{concept} AS (\n  SELECT * FROM (\n{indented}\n  ) AS r({cols})\n)"


def with_rules(rules: Rules, concepts: tuple[str, ...], body: str) -> str:
    ctes = ",\n".join(label_cte(c, rules[c][1]) for c in concepts)
    return f"WITH {ctes}\n{body}"


def _d(value: date) -> str:
    return f"DATE '{value.isoformat()}'"


@dataclass(frozen=True)
class QuestionTemplate:
    qid: str
    concept: str  # the concept the question is written for
    concepts: tuple[str, ...]  # every concept the answer depends on
    answer_type: Literal["number", "table"]
    measure: Literal["count", "amount"]
    text: Callable[[TenantSpec], str]
    sql: Callable[[TenantSpec, Rules], str]
    answer: Callable[[TenantSpec, Frames, Truth], Answer]


def _booked_equipment_lines(spec: TenantSpec, f: Frames, t: Truth) -> pd.DataFrame:
    lo, hi = prior_year(spec)
    so = f["sales_order"]
    so = so[so["sales_order_id"].map(t["booked_sale"]).astype(bool)]
    so = so[(so["order_date"] >= lo) & (so["order_date"] <= hi)]
    sol = f["sales_order_line"]
    sol = sol[(sol["line_type"] == "equipment") & sol["sales_order_id"].isin(so["sales_order_id"])]
    return sol.assign(line=sol["equipment_id"].map(t["product_line"]))


def _pl_join(rules: Rules) -> str:
    table, _ = CONCEPTS["product_line"].rule_grain(rules["product_line"][0])
    return "pl.id = so.sales_order_id" if table == "sales_order" else "pl.id = sol.equipment_id"


def _pl_sql(agg: str) -> Callable[[TenantSpec, Rules], str]:
    def build(spec: TenantSpec, rules: Rules) -> str:
        lo, hi = prior_year(spec)
        body = (
            f"SELECT pl.value AS key, {agg} AS value\n"
            "FROM sales_order so\n"
            "JOIN sales_order_line sol ON sol.sales_order_id = so.sales_order_id\n"
            "                         AND sol.line_type = 'equipment'\n"
            f"LEFT JOIN product_line pl ON {_pl_join(rules)}\n"
            f"WHERE so.tenant_id = {spec.tenant_id}\n"
            "  AND so.sales_order_id IN (SELECT id FROM booked_sale)\n"
            f"  AND so.order_date BETWEEN {_d(lo)} AND {_d(hi)}\n"
            "GROUP BY 1"
        )
        return with_rules(rules, ("booked_sale", "product_line"), body)

    return build


def _ats_units(f: Frames, t: Truth) -> pd.DataFrame:
    e = f["equipment"]
    return e[e["equipment_id"].map(t["available_to_sell"]).astype(bool)]


def _ats_by_location(spec: TenantSpec, f: Frames, t: Truth) -> Answer:
    units = _ats_units(f, t)
    codes = dict(zip(f["location"]["location_id"], f["location"]["location_code"], strict=True))
    keys = units["location_id"].map(codes)
    return {str(k): float(v) for k, v in keys.value_counts(dropna=False).items()}


def _iw_external_revenue(spec: TenantSpec, f: Frames, t: Truth) -> Answer:
    lo, hi = last_quarter(spec)
    wo = f["work_order"]
    wo = wo[(wo["opened_date"] >= lo) & (wo["opened_date"] <= hi)]
    wo = wo[~wo["work_order_id"].map(t["internal_work"]).astype(bool)]
    wol = f["work_order_line"]
    return float(wol[wol["work_order_id"].isin(wo["work_order_id"])]["line_amount"].sum())


def _iw_internal_count(spec: TenantSpec, f: Frames, t: Truth) -> Answer:
    lo, hi = prior_year(spec)
    wo = f["work_order"]
    wo = wo[(wo["opened_date"] >= lo) & (wo["opened_date"] <= hi)]
    return float(wo["work_order_id"].map(t["internal_work"]).astype(bool).sum())


def _booked_equipment_orders(spec: TenantSpec, f: Frames, t: Truth) -> pd.DataFrame:
    lo, hi = prior_year(spec)
    so = f["sales_order"]
    so = so[so["sales_order_id"].map(t["booked_sale"]).astype(bool)]
    so = so[(so["order_date"] >= lo) & (so["order_date"] <= hi)]
    sol = f["sales_order_line"]
    with_unit = set(sol[sol["line_type"] == "equipment"]["sales_order_id"])
    return so[so["sales_order_id"].isin(with_unit)]


def _bs_sql(agg: str) -> Callable[[TenantSpec, Rules], str]:
    def build(spec: TenantSpec, rules: Rules) -> str:
        lo, hi = prior_year(spec)
        body = (
            f"SELECT {agg}\n"
            "FROM sales_order so\n"
            f"WHERE so.tenant_id = {spec.tenant_id}\n"
            "  AND so.sales_order_id IN (SELECT id FROM booked_sale)\n"
            f"  AND so.order_date BETWEEN {_d(lo)} AND {_d(hi)}\n"
            "  AND EXISTS (SELECT 1 FROM sales_order_line sol\n"
            "              WHERE sol.sales_order_id = so.sales_order_id\n"
            "                AND sol.line_type = 'equipment')"
        )
        return with_rules(rules, ("booked_sale",), body)

    return build


def _year(spec: TenantSpec) -> int:
    return spec.as_of_date.year - 1


QUESTIONS: list[QuestionTemplate] = [
    QuestionTemplate(
        qid="product_line.revenue_by_line",
        concept="product_line",
        concepts=("product_line", "booked_sale"),
        answer_type="table",
        measure="amount",
        text=lambda s: (
            f"What was equipment sales revenue by product line in {_year(s)}? Count booked "
            f"sales with an order date from {_year(s)}-01-01 to {_year(s)}-12-31, and take "
            "revenue as the sum of their equipment line amounts."
        ),
        sql=_pl_sql("SUM(sol.line_amount)"),
        answer=lambda s, f, t: {
            str(k): float(v)
            for k, v in _booked_equipment_lines(s, f, t)
            .groupby("line")["line_amount"]
            .sum()
            .items()
        },
    ),
    QuestionTemplate(
        qid="product_line.units_sold_by_line",
        concept="product_line",
        concepts=("product_line", "booked_sale"),
        answer_type="table",
        measure="count",
        text=lambda s: (
            f"How many units were sold on booked sales in {_year(s)}, by product line? Use "
            f"order dates from {_year(s)}-01-01 to {_year(s)}-12-31."
        ),
        sql=_pl_sql("COUNT(*)"),
        answer=lambda s, f, t: {
            str(k): float(v)
            for k, v in _booked_equipment_lines(s, f, t).groupby("line").size().items()
        },
    ),
    QuestionTemplate(
        qid="available_to_sell.count_by_location",
        concept="available_to_sell",
        concepts=("available_to_sell",),
        answer_type="table",
        measure="count",
        text=lambda s: (
            f"How many units were available to sell on {s.as_of_date.isoformat()}, by the "
            "location code where each unit stands?"
        ),
        sql=lambda s, r: with_rules(
            r,
            ("available_to_sell",),
            "SELECT l.location_code AS key, COUNT(*) AS value\n"
            "FROM equipment e\n"
            "LEFT JOIN location l ON l.location_id = e.location_id\n"
            f"WHERE e.tenant_id = {s.tenant_id}\n"
            "  AND e.equipment_id IN (SELECT id FROM available_to_sell)\n"
            "GROUP BY 1",
        ),
        answer=_ats_by_location,
    ),
    QuestionTemplate(
        qid="available_to_sell.acquisition_cost",
        concept="available_to_sell",
        concepts=("available_to_sell",),
        answer_type="number",
        measure="amount",
        text=lambda s: (
            "What is the total recorded acquisition cost of the units available to sell on "
            f"{s.as_of_date.isoformat()}?"
        ),
        sql=lambda s, r: with_rules(
            r,
            ("available_to_sell",),
            "SELECT COALESCE(SUM(e.acquisition_cost), 0)\n"
            "FROM equipment e\n"
            f"WHERE e.tenant_id = {s.tenant_id}\n"
            "  AND e.equipment_id IN (SELECT id FROM available_to_sell)",
        ),
        answer=lambda s, f, t: float(_ats_units(f, t)["acquisition_cost"].fillna(0).sum()),
    ),
    QuestionTemplate(
        qid="internal_work.external_revenue_last_quarter",
        concept="internal_work",
        concepts=("internal_work",),
        answer_type="number",
        measure="amount",
        text=lambda s: (
            "What was external service revenue, as the sum of work order line amounts on work "
            f"orders opened from {last_quarter(s)[0].isoformat()} to "
            f"{last_quarter(s)[1].isoformat()} whose cost the dealer does not bear?"
        ),
        sql=lambda s, r: with_rules(
            r,
            ("internal_work",),
            "SELECT COALESCE(SUM(wol.line_amount), 0)\n"
            "FROM work_order wo\n"
            "JOIN work_order_line wol ON wol.work_order_id = wo.work_order_id\n"
            f"WHERE wo.tenant_id = {s.tenant_id}\n"
            f"  AND wo.opened_date BETWEEN {_d(last_quarter(s)[0])} AND {_d(last_quarter(s)[1])}\n"
            "  AND wo.work_order_id NOT IN (SELECT id FROM internal_work)",
        ),
        answer=_iw_external_revenue,
    ),
    QuestionTemplate(
        qid="internal_work.internal_count",
        concept="internal_work",
        concepts=("internal_work",),
        answer_type="number",
        measure="count",
        text=lambda s: (
            f"How many internal work orders were opened from {_year(s)}-01-01 to {_year(s)}-12-31?"
        ),
        sql=lambda s, r: with_rules(
            r,
            ("internal_work",),
            "SELECT COUNT(*)\n"
            "FROM work_order wo\n"
            f"WHERE wo.tenant_id = {s.tenant_id}\n"
            f"  AND wo.opened_date BETWEEN {_d(prior_year(s)[0])} AND {_d(prior_year(s)[1])}\n"
            "  AND wo.work_order_id IN (SELECT id FROM internal_work)",
        ),
        answer=_iw_internal_count,
    ),
    QuestionTemplate(
        qid="booked_sale.equipment_sales_count",
        concept="booked_sale",
        concepts=("booked_sale",),
        answer_type="number",
        measure="count",
        text=lambda s: (
            f"How many equipment sales were booked in {_year(s)}? Count sales orders with an "
            f"order date from {_year(s)}-01-01 to {_year(s)}-12-31 and at least one equipment line."
        ),
        sql=_bs_sql("COUNT(*)"),
        answer=lambda s, f, t: float(len(_booked_equipment_orders(s, f, t))),
    ),
    QuestionTemplate(
        qid="booked_sale.equipment_sales_amount",
        concept="booked_sale",
        concepts=("booked_sale",),
        answer_type="number",
        measure="amount",
        text=lambda s: (
            f"What was the total amount of equipment sales booked in {_year(s)}, as the sum of "
            "order totals? Use the same orders as the count of booked equipment sales."
        ),
        sql=_bs_sql("COALESCE(SUM(so.total_amount), 0)"),
        answer=lambda s, f, t: float(_booked_equipment_orders(s, f, t)["total_amount"].sum()),
    ),
]


def primary_question(concept: str) -> QuestionTemplate:
    return next(q for q in QUESTIONS if q.concept == concept)


def tenant_frames(tables: dict[str, pa.Table], tenant_id: int) -> Frames:
    """One tenant's tables as pandas, with decimals as floats."""
    frames: Frames = {}
    for name, table in tables.items():
        df = table.to_pandas()
        df = df[df["tenant_id"] == tenant_id].reset_index(drop=True)
        for field in table.schema:
            if pa.types.is_decimal(field.type):
                df[field.name] = df[field.name].astype(float)
        frames[name] = df
    return frames


def round_answer(answer: Answer) -> Answer:
    if isinstance(answer, dict):
        return {k: round(v, 2) for k, v in sorted(answer.items())}
    return round(answer, 2)


def questions(spec: TenantSpec, frames: Frames, truth: Truth) -> list[dict[str, Any]]:
    rules = own_rules(spec)
    out = []
    for q in QUESTIONS:
        if not set(q.concepts) <= set(spec.concepts):
            continue
        out.append(
            {
                "tenant_id": spec.tenant_id,
                "question_id": q.qid,
                "text": q.text(spec),
                "concepts": list(q.concepts),
                "answer_type": q.answer_type,
                "measure": q.measure,
                "answer": round_answer(q.answer(spec, frames, truth)),
                "tolerance": 0.0 if q.measure == "count" else AMOUNT_TOLERANCE,
                "sql": q.sql(spec, rules),
            }
        )
    return out


# ---------------------------------------------------------- answer compare
def normalise(answer: Any) -> Answer:
    """Answers from SQL rows, JSON or pandas -> float or {trimmed lower key: float}."""
    if isinstance(answer, dict):
        return {
            ("" if k is None or k == "None" else str(k)).strip().lower(): float(v)
            for k, v in answer.items()
        }
    return float(answer or 0)


def answers_agree(a: Any, b: Any, measure: str) -> bool:
    a, b = normalise(a), normalise(b)
    if isinstance(a, dict) or isinstance(b, dict):
        if not (isinstance(a, dict) and isinstance(b, dict)) or set(a) != set(b):
            return False
        return all(_close(a[k], b[k], measure) for k in a)
    return _close(a, b, measure)


def _close(a: float, b: float, measure: str) -> bool:
    if measure == "count":
        return round(a) == round(b)
    return abs(a - b) <= AMOUNT_TOLERANCE * max(abs(a), abs(b), 0.01)


def answer_change(truth: Any, other: Any) -> float:
    """Largest relative change between two answers (for a table, over all groups)."""
    t, o = normalise(truth), normalise(other)
    if isinstance(t, dict) and isinstance(o, dict):
        keys = set(t) | set(o)
        return max((_rel(t.get(k, 0.0), o.get(k, 0.0)) for k in keys), default=0.0)
    assert isinstance(t, float) and isinstance(o, float)
    return _rel(t, o)


def _rel(t: float, o: float) -> float:
    if t == o:
        return 0.0
    return abs(o - t) / abs(t) if t else 1.0
