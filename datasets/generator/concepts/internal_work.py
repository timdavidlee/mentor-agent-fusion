"""Concept 5: internal work. Truth at `work_order`: does the dealer bear the cost."""

from generator.concepts.base import Concept, choice, not_in_milestone_1, sql_list
from generator.population import ConceptChoice, TenantSpec
from generator.simulate.world import World


class InternalWork(Concept):
    name = "internal_work"
    title = "Internal work"
    grain = "work_order"
    id_column = "work_order_id"
    kind = "bucket"
    plain_rungs = (1, 3)

    def rule_sql(self, rung: int, params: dict[str, list[str]], tenant_id: int) -> str:
        if rung == 1:
            return (
                "SELECT wo.work_order_id FROM work_order wo\n"
                f"WHERE wo.tenant_id = {tenant_id}\n"
                "  AND wo.is_internal = TRUE"
            )
        if rung == 2:
            return (
                "SELECT wo.work_order_id FROM work_order wo\n"
                "JOIN customer c ON c.customer_id = wo.customer_id\n"
                f"WHERE wo.tenant_id = {tenant_id}\n"
                "  AND (wo.is_internal = TRUE"
                f" OR c.account_class IN ({sql_list(params['house_account_classes'])}))"
            )
        return (
            "SELECT wo.work_order_id FROM work_order wo\n"
            "JOIN equipment e ON e.equipment_id = wo.equipment_id\n"
            f"WHERE wo.tenant_id = {tenant_id}\n"
            "  AND e.owner_customer_id IS NULL"
        )

    def reads(self, rung: int) -> list[str]:
        if rung == 1:
            return ["work_order.is_internal"]
        if rung == 2:
            return ["work_order.is_internal", "work_order.customer_id", "customer.account_class"]
        return ["work_order.equipment_id", "equipment.owner_customer_id"]

    def column_usage(self, choice: ConceptChoice) -> dict[str, tuple[str, str]]:
        if choice.rung == 2:
            return {
                "work_order.is_internal": (
                    "defaulted",
                    "false unless the writer ticks it; house accounts mark the rest",
                )
            }
        if choice.rung == 3:
            return {"work_order.is_internal": ("defaulted", "false on every row")}
        return {}

    def validate(self, spec: TenantSpec) -> None:
        c = spec.concepts[self.name]
        if c.rung == 2:
            house = set(spec.vocabulary["customer.house_classes"])
            if not house <= set(c.params["house_account_classes"]):
                raise ValueError(f"{spec.tenant_code}: house accounts outside the rule's list")

    def encode(self, world: World) -> None:
        c = choice(world, self.name)
        house_ids = {
            r["customer_id"]
            for r in world.rows["customer"]
            if r["account_class"] in world.spec.vocabulary["customer.house_classes"]
        }
        for wo in world.rows["work_order"]:
            truth = world.truth[self.name][wo["work_order_id"]]
            if c.rung == 1:
                wo["is_internal"] = truth
            elif c.rung == 2:
                if truth and wo["customer_id"] not in house_ids:
                    wo["is_internal"] = True  # absorbed on a customer's own account
                else:
                    # the flag is ticked on some internal work; the house account marks the rest
                    wo["is_internal"] = truth and world.chance(0.2)
            else:
                raise not_in_milestone_1(self.name, c.rung)
