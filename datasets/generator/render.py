"""Truth -> schema columns: concept encoders, tenant vocabulary, data-entry habits."""

import pyarrow as pa

from generator.concepts import CONCEPTS
from generator.population import TenantSpec
from generator.schema import TABLES
from generator.simulate.world import World

# Columns that data-entry habits may blank or fill with free text.
HABIT_COLUMNS: dict[str, str] = {
    "customer.notes": "notes",
    "equipment.notes": "notes",
    "sales_order.notes": "notes",
    "rental_contract.notes": "notes",
    "work_order.notes": "notes",
    "equipment.meter_reading": "meter",
    "work_order.meter_reading": "meter",
    "customer.address_line": "address",
    "equipment.serial_number": "serial",
}

NOTES = [
    "called customer, left message",
    "see paper file",
    "per phone call",
    "rush",
    "customer to pick up",
    "check with office",
    "pricing approved",
    "deliver after 2pm",
]


def relied_columns(spec: TenantSpec) -> set[str]:
    """Every `table.column` that one of the tenant's chosen rules reads."""
    return {col for name, c in spec.concepts.items() for col in CONCEPTS[name].reads(c.rung)}


def render(world: World) -> dict[str, pa.Table]:
    spec = world.spec
    for name in spec.concepts:
        CONCEPTS[name].encode(world)
    _tenant_vocabulary(world)
    touched = apply_habits(world)
    clash = touched & relied_columns(spec)
    if clash:
        raise AssertionError(f"{spec.tenant_code}: habits touched rule columns {sorted(clash)}")
    return {
        table: pa.Table.from_pylist(world.rows[table], schema=defn.arrow_schema())
        for table, defn in TABLES.items()
    }


def _tenant_vocabulary(world: World) -> None:
    allowed = world.spec.vocabulary.get("work_order.work_order_type")
    if allowed:
        for wo in world.rows["work_order"]:
            if wo["work_order_type"] not in allowed:
                wo["work_order_type"] = allowed[0]


def apply_habits(world: World) -> set[str]:
    """Blank or fill habit columns. Returns the `table.column` names it may have changed."""
    habits = world.spec.habits
    relied = relied_columns(world.spec)
    touched: set[str] = set()
    for qualified, habit in HABIT_COLUMNS.items():
        if qualified in relied:
            continue  # never touch a column a chosen rule relies on
        table, column = qualified.split(".")
        touched.add(qualified)
        for row in world.rows[table]:
            if habit == "notes":
                if world.chance(habits.notes_rate):
                    row[column] = world.rng.choice(NOTES)
            elif habit == "meter" and world.chance(habits.meter_blank_rate):
                row[column] = None
            elif habit == "address" and world.chance(habits.address_blank_rate):
                row[column] = None
            elif habit == "serial" and world.chance(habits.serial_blank_rate):
                row[column] = None
    return touched
