"""Concept 3: available to sell. Truth at `equipment`: could a salesperson sell it today."""

from generator.concepts.base import Concept, choice, not_in_milestone_1, sql_list
from generator.population import ConceptChoice, TenantSpec
from generator.simulate.world import World

# At a rule 3 tenant, the share of sold units whose status the clerk changed to 'sold'
SOLD_STATUS_UPDATED = 0.8


class AvailableToSell(Concept):
    name = "available_to_sell"
    title = "Available to sell"
    grain = "equipment"
    id_column = "equipment_id"
    kind = "bucket"
    plain_rungs = (1, 3)

    def rule_sql(self, rung: int, params: dict[str, list[str]], tenant_id: int) -> str:
        if rung == 1:
            return (
                "SELECT e.equipment_id FROM equipment e\n"
                f"WHERE e.tenant_id = {tenant_id}\n"
                "  AND e.status = 'available'"
            )
        if rung == 2:
            return (
                "SELECT e.equipment_id FROM equipment e\n"
                f"WHERE e.tenant_id = {tenant_id}\n"
                f"  AND e.status IN ({sql_list(params['status_list'])})\n"
                "  AND (e.hold_code IS NULL\n"
                f"       OR e.hold_code NOT IN ({sql_list(params['hold_codes'])}))"
            )
        return (
            "SELECT e.equipment_id FROM equipment e\n"
            "JOIN location l ON l.location_id = e.location_id\n"
            f"WHERE e.tenant_id = {tenant_id}\n"
            "  AND e.owner_customer_id IS NULL\n"
            "  AND l.location_type = 'sales_yard'\n"
            "  AND NOT EXISTS (SELECT 1 FROM rental_contract rc\n"
            "                  WHERE rc.equipment_id = e.equipment_id\n"
            "                    AND rc.status = 'open')\n"
            "  AND NOT EXISTS (SELECT 1 FROM sales_order_line sol\n"
            "                  JOIN invoice i ON i.sales_order_id = sol.sales_order_id\n"
            "                  WHERE sol.equipment_id = e.equipment_id\n"
            "                    AND sol.line_type = 'equipment'\n"
            "                    AND i.status <> 'void')"
        )

    def reads(self, rung: int) -> list[str]:
        if rung == 1:
            return ["equipment.status"]
        if rung == 2:
            return ["equipment.status", "equipment.hold_code"]
        return [
            "equipment.owner_customer_id",
            "equipment.location_id",
            "location.location_type",
            "rental_contract.equipment_id",
            "rental_contract.status",
            "sales_order_line.equipment_id",
            "sales_order_line.line_type",
            "invoice.sales_order_id",
            "invoice.status",
        ]

    def column_usage(self, choice: ConceptChoice) -> dict[str, tuple[str, str]]:
        if choice.rung == 3:
            return {
                "equipment.status": (
                    "neglected",
                    "'available' at receipt; changed to 'sold' on most sales, never for rentals",
                ),
                "equipment.hold_code": ("neglected", "never filled"),
            }
        return {}

    def validate(self, spec: TenantSpec) -> None:
        c = spec.concepts[self.name]
        if c.rung != 3:
            return
        # rule 3 reads the yard: sale stock must stand at sales yards, and idle fleet units
        # count as for sale exactly when they stand at one too
        if any(s.location_type != "sales_yard" for s in spec.locations if s.stocks_lines):
            raise ValueError(f"{spec.tenant_code}: sale stock off a sales yard breaks rule 3")
        has_branches = any(s.location_type == "rental_branch" for s in spec.locations)
        if spec.idle_fleet_is_for_sale == has_branches:
            raise ValueError(f"{spec.tenant_code}: idle-fleet policy disagrees with rule 3")

    def encode(self, world: World) -> None:
        c = choice(world, self.name)
        for unit in world.rows["equipment"]:
            facts = world.fact("equipment", unit["equipment_id"])
            truth = world.truth[self.name][unit["equipment_id"]]
            if c.rung == 3:
                # set to 'available' at receipt; the clerk marks most sales 'sold' but never
                # rentals; customer units were never received
                if facts["kind"] != "stock":
                    unit["status"] = None
                elif facts["state"] == "sold" and world.chance(SOLD_STATUS_UPDATED):
                    unit["status"] = "sold"
                else:
                    unit["status"] = "available"
                unit["hold_code"] = None
            elif c.rung == 2:
                unit["status"], unit["hold_code"] = self._rung2(world, c, facts, truth)
            else:
                raise not_in_milestone_1(self.name, c.rung)

    @staticmethod
    def _rung2(
        world: World, c: ConceptChoice, facts: dict, truth: bool
    ) -> tuple[str | None, str | None]:
        sellable = c.params["status_list"]
        holds = c.params["hold_codes"]
        spare_holds = [h for h in world.spec.vocabulary["equipment.hold_code"] if h not in holds]
        state = facts["state"]
        if truth:
            status = world.rng.choice(sellable)
            hold = world.rng.choice(spare_holds) if spare_holds and world.chance(0.1) else None
            return status, hold
        if state == "in_stock" and facts["held"]:
            return "available", facts["held"]  # looks for sale, held back by its hold code
        if state == "in_stock" and facts["in_transit"]:
            return "in_transit", None
        return {
            "on_rent": "on_rent",
            "fleet_idle": "fleet",
            "sold": "sold",
            "customer": None,
        }[state], None
