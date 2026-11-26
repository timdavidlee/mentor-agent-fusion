"""What every concept module provides: rule SQL, encoders and column declarations."""

from abc import ABC, abstractmethod
from typing import ClassVar, Literal

from generator.population import ConceptChoice, TenantSpec
from generator.simulate.world import World

Kind = Literal["bucket", "value"]


def sql_list(values: list[str]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


class Concept(ABC):
    name: ClassVar[str]
    title: ClassVar[str]
    grain: ClassVar[str]  # table whose rows carry the hidden truth
    id_column: ClassVar[str]
    kind: ClassVar[Kind]  # bucket: rule SQL returns the ids that are "yes"; value: (id, value)
    plain_rungs: ClassVar[tuple[int, ...]]  # rungs that make sense with no tenant parameters

    @abstractmethod
    def rule_sql(self, rung: int, params: dict[str, list[str]], tenant_id: int) -> str:
        """The rule as runnable SQL, with its outermost table filtered to one tenant."""

    def rule_grain(self, rung: int) -> tuple[str, str]:
        """Table and id column of the rows the rule returns (product line rung 3 differs)."""
        return self.grain, self.id_column

    @abstractmethod
    def encode(self, world: World) -> None:
        """Write the columns this concept owns so the tenant's rule reproduces the truth."""

    @abstractmethod
    def reads(self, rung: int) -> list[str]:
        """`table.column` names the rule reads; habits must leave them alone."""

    def column_usage(self, choice: ConceptChoice) -> dict[str, tuple[str, str]]:
        """Columns this concept leaves other than maintained: `table.column` -> (usage, note)."""
        return {}

    def validate(self, spec: TenantSpec) -> None:
        """Raise if the tenant spec cannot be rendered under its rule (compatibility)."""
        return None


def choice(world: World, concept: str) -> ConceptChoice:
    return world.spec.concepts[concept]


def not_in_milestone_1(concept: str, rung: int) -> NotImplementedError:
    return NotImplementedError(f"{concept} rung {rung} encoder is not built yet (milestone 2)")
