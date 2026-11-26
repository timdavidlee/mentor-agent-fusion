"""Concept 8: booked sale. Truth at `sales_order`: is it a real, completed sale."""

from generator.concepts.base import Concept, choice, not_in_milestone_1, sql_list
from generator.population import ConceptChoice
from generator.simulate.world import World

# At a rule 3 tenant, the share of booked orders that someone set to 'closed'
BOOKED_CLOSED = 0.7


class BookedSale(Concept):
    name = "booked_sale"
    title = "Booked sale"
    grain = "sales_order"
    id_column = "sales_order_id"
    kind = "bucket"
    plain_rungs = (1, 3)

    def rule_sql(self, rung: int, params: dict[str, list[str]], tenant_id: int) -> str:
        if rung == 1:
            return (
                "SELECT so.sales_order_id FROM sales_order so\n"
                f"WHERE so.tenant_id = {tenant_id}\n"
                "  AND so.status = 'closed'"
            )
        if rung == 2:
            return (
                "SELECT so.sales_order_id FROM sales_order so\n"
                f"WHERE so.tenant_id = {tenant_id}\n"
                f"  AND so.status IN ({sql_list(params['status_list'])})\n"
                "  AND so.order_type <> 'quote'"
            )
        return (
            "SELECT so.sales_order_id FROM sales_order so\n"
            f"WHERE so.tenant_id = {tenant_id}\n"
            "  AND EXISTS (SELECT 1 FROM invoice i\n"
            "              WHERE i.sales_order_id = so.sales_order_id\n"
            "                AND i.status <> 'void')"
        )

    def reads(self, rung: int) -> list[str]:
        if rung == 1:
            return ["sales_order.status"]
        if rung == 2:
            return ["sales_order.status", "sales_order.order_type"]
        return ["invoice.sales_order_id", "invoice.status"]

    def column_usage(self, choice: ConceptChoice) -> dict[str, tuple[str, str]]:
        if choice.rung == 3:
            return {
                "sales_order.status": (
                    "neglected",
                    "'closed' on most booked deals; the rest stay 'open' after the deal is done",
                )
            }
        return {}

    def encode(self, world: World) -> None:
        c = choice(world, self.name)
        for order in world.rows["sales_order"]:
            facts = world.fact("sales_order", order["sales_order_id"])
            outcome, kind = facts["outcome"], facts["kind"]
            if c.rung == 3:
                order["order_type"] = kind
                if outcome == "booked":
                    # closed by the bookkeeper on most deals; the rest stay 'open'
                    order["status"] = "closed" if world.chance(BOOKED_CLOSED) else "open"
                elif outcome == "voided" or (outcome == "abandoned" and world.chance(0.3)):
                    order["status"] = "cancelled"
                else:
                    order["status"] = "open"
            elif c.rung == 2:
                order["order_type"], order["status"] = self._rung2(world, c, outcome, kind)
            else:
                raise not_in_milestone_1(self.name, c.rung)

    @staticmethod
    def _rung2(world: World, c: ConceptChoice, outcome: str, kind: str) -> tuple[str, str]:
        listed = c.params["status_list"]
        if outcome == "booked":
            # mostly 'closed' (the nominal value); the rest at the tenant's other listed statuses
            others = [s for s in listed if s != "closed"]
            status = "closed" if world.chance(0.55) or not others else world.rng.choice(others)
            return kind, status
        if outcome == "quote":
            # expired quotes get closed, which the nominal rule would count as sales
            return "quote", "closed" if world.chance(0.25) else "open"
        if outcome == "abandoned":
            return kind, "open" if world.chance(0.5) else "cancelled"
        return kind, "cancelled"  # voided deals and dead deposits
