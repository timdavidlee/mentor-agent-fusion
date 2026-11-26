"""Concept 1: product line. Truth at `equipment`: construction, agriculture or compact."""

from generator.concepts.base import Concept, choice, not_in_milestone_1, sql_list
from generator.population import ConceptChoice, TenantSpec
from generator.simulate.world import World

# At a rule 3 tenant, the share of models whose category is not the product line
MODELS_WITHOUT_LINE = 0.25
MARKETING_FAMILIES = ["300 Series", "Pro Line", "X Series", "Heritage", "Titan"]


class ProductLine(Concept):
    name = "product_line"
    title = "Product line"
    grain = "equipment"
    id_column = "equipment_id"
    kind = "value"
    plain_rungs = (1,)  # rungs 2 and 3 need the tenant's code lists

    def rule_sql(self, rung: int, params: dict[str, list[str]], tenant_id: int) -> str:
        if rung == 1:
            return (
                "SELECT e.equipment_id, m.category AS product_line\n"
                "FROM equipment e\n"
                "JOIN equipment_model m ON m.model_id = e.model_id\n"
                f"WHERE e.tenant_id = {tenant_id}"
            )
        if rung == 2:
            return (
                "SELECT e.equipment_id,\n"
                f"       CASE WHEN m.class_code IN ({sql_list(params['compact_class_codes'])})"
                " THEN 'compact'\n"
                "            ELSE m.category END AS product_line\n"
                "FROM equipment e\n"
                "JOIN equipment_model m ON m.model_id = e.model_id\n"
                f"WHERE e.tenant_id = {tenant_id}"
            )
        return (
            "SELECT so.sales_order_id,\n"
            f"       CASE WHEN d.department_code IN ({sql_list(params['ag_department_codes'])})"
            " THEN 'agriculture'\n"
            f"            WHEN l.location_code IN ({sql_list(params['compact_location_codes'])})"
            " THEN 'compact'\n"
            "            ELSE 'construction' END AS product_line\n"
            "FROM sales_order so\n"
            "JOIN department d ON d.department_id = so.department_id\n"
            "JOIN location l ON l.location_id = so.location_id\n"
            f"WHERE so.tenant_id = {tenant_id}"
        )

    def rule_grain(self, rung: int) -> tuple[str, str]:
        return ("sales_order", "sales_order_id") if rung == 3 else (self.grain, self.id_column)

    def reads(self, rung: int) -> list[str]:
        if rung == 1:
            return ["equipment.model_id", "equipment_model.category"]
        if rung == 2:
            return ["equipment.model_id", "equipment_model.category", "equipment_model.class_code"]
        return [
            "sales_order.department_id",
            "sales_order.location_id",
            "department.department_code",
            "location.location_code",
        ]

    def column_usage(self, choice: ConceptChoice) -> dict[str, tuple[str, str]]:
        if choice.rung == 3:
            return {
                "equipment_model.category": (
                    "repurposed",
                    "the line on most models; a marketing family or blank on the rest",
                )
            }
        return {}

    def validate(self, spec: TenantSpec) -> None:
        c = spec.concepts[self.name]
        if c.rung != 3:
            return
        ag = set(c.params["ag_department_codes"])
        compact = set(c.params["compact_location_codes"])
        # every department and yard the simulation may sell a line through maps to that line
        for line in ("construction", "agriculture", "compact"):
            for d in (d for d in spec.departments if line in d.sells_lines):
                for loc in (s for s in spec.locations if line in s.stocks_lines):
                    mapped = (
                        "agriculture"
                        if d.code in ag
                        else "compact"
                        if loc.code in compact
                        else "construction"
                    )
                    if mapped != line:
                        where = f"{d.code} at {loc.code}"
                        raise ValueError(f"{spec.tenant_code}: {line} via {where} reads {mapped}")

    def encode(self, world: World) -> None:
        c = choice(world, self.name)
        models = world.rows["equipment_model"]
        if c.rung not in (1, 3):
            raise not_in_milestone_1(self.name, c.rung)
        # rule 3 tenants keep the line on most models; on the rest the category holds the
        # manufacturer's family name, or is blank
        off = set()
        if c.rung == 3:
            ids = [m["model_id"] for m in models]
            off = set(world.rng.sample(ids, round(len(ids) * MODELS_WITHOUT_LINE)))
        for model in models:
            line = world.fact("equipment_model", model["model_id"])["line"]
            if model["model_id"] not in off:
                model["category"] = line
            elif world.chance(0.3):
                model["category"] = None
            else:
                model["category"] = world.rng.choice(MARKETING_FAMILIES)
