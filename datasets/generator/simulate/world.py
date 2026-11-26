"""Mutable container for one tenant's simulated rows, facts and hidden truth."""

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from generator.population import TenantSpec
from generator.schema import TABLES

ID_BLOCK = 1_000_000  # each tenant owns ids [tenant_id * ID_BLOCK, (tenant_id + 1) * ID_BLOCK)

Row = dict[str, Any]

CENT = Decimal("0.01")


def money(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def qty(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class World:
    spec: TenantSpec
    rng: random.Random
    rows: dict[str, list[Row]] = field(default_factory=dict)
    by_id: dict[str, dict[int, Row]] = field(default_factory=dict)
    # simulation facts per row, never rendered: facts[table][id] -> dict
    facts: dict[str, dict[int, dict[str, Any]]] = field(default_factory=dict)
    # hidden truth: truth[concept][row id] -> value
    truth: dict[str, dict[int, Any]] = field(default_factory=dict)
    exceptions: dict[str, int] = field(default_factory=dict)
    _next_id: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for table in TABLES:
            self.rows[table] = []
            self.by_id[table] = {}
            self.facts[table] = {}

    @property
    def as_of(self) -> date:
        return self.spec.as_of_date

    @property
    def start(self) -> date:
        return self.as_of.replace(year=self.as_of.year - self.spec.history_years) + timedelta(1)

    def new_id(self, table: str) -> int:
        current = self._next_id.get(table, self.spec.tenant_id * ID_BLOCK)
        self._next_id[table] = current + 1
        return current + 1

    def add(self, table: str, **values: Any) -> Row:
        """Add a row with every schema column present (missing ones are null)."""
        defn = TABLES[table]
        unknown = set(values) - set(defn.column_names)
        if unknown:
            raise KeyError(f"{table}: unknown columns {sorted(unknown)}")
        row: Row = {name: None for name in defn.column_names}
        row["tenant_id"] = self.spec.tenant_id
        if len(defn.primary_key) == 1:
            pk = defn.primary_key[0]
            if values.get(pk) is None:
                values[pk] = self.new_id(table)
        row.update(values)
        self.rows[table].append(row)
        if len(defn.primary_key) == 1:
            self.by_id[table][row[defn.primary_key[0]]] = row
            self.facts[table][row[defn.primary_key[0]]] = {}
        return row

    def fact(self, table: str, row_id: int) -> dict[str, Any]:
        return self.facts[table][row_id]

    def note_exception(self, name: str) -> None:
        self.exceptions[name] = self.exceptions.get(name, 0) + 1

    # random helpers -------------------------------------------------------
    def chance(self, p: float) -> bool:
        return self.rng.random() < p

    def day_between(self, lo: date, hi: date) -> date:
        if hi <= lo:
            return lo
        return lo + timedelta(days=self.rng.randint(0, (hi - lo).days))

    def poisson(self, mean: float) -> int:
        # Knuth; fine for the small means used here
        limit, k, p = pow(2.718281828459045, -mean), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= limit:
                return k
            k += 1
