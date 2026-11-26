"""Top-level entry point: `GeneratorConfig.make()` and `.make_in_dir()`."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel

from generator import ground_truth
from generator.concepts import CONCEPTS
from generator.population import TenantSpec, hand_written_tenants
from generator.render import render
from generator.schema import TABLES
from generator.simulate import simulate

DEFAULT_OUT_DIR = Path(__file__).resolve().parents[1] / "generated"
SPLITS = ("seen", "held_out")
DEFAULT_MASTER_SEED = 20261125


@dataclass
class TenantBuild:
    spec: TenantSpec
    tables: dict[str, pa.Table]  # visible, after habits
    truth: dict[str, pa.Table]  # concept -> per-row truth
    concept_rules: list[dict[str, Any]]
    column_usage: list[dict[str, Any]]
    questions: list[dict[str, Any]]
    exceptions: dict[str, int]


def build_tenant(spec: TenantSpec) -> TenantBuild:
    for name in spec.concepts:
        CONCEPTS[name].validate(spec)
    world = simulate(spec)  # truth is decided here, before any column is rendered
    tables = render(world)
    truth = {name: ground_truth.truth_table(world, name) for name in spec.concepts}
    frames = ground_truth.tenant_frames(tables, spec.tenant_id)
    return TenantBuild(
        spec=spec,
        tables=tables,
        truth=truth,
        concept_rules=ground_truth.concept_rules(spec),
        column_usage=ground_truth.column_usage(spec),
        questions=ground_truth.questions(spec, frames, world.truth),
        exceptions=dict(sorted(world.exceptions.items())),
    )


def _concat(tables: list[pa.Table], schema: pa.Schema) -> pa.Table:
    return pa.concat_tables(tables) if tables else schema.empty_table()


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    lines = [json.dumps(r, sort_keys=True, default=str) for r in records]
    path.write_text("".join(line + "\n" for line in lines))


class GeneratorConfig(BaseModel):
    name: ClassVar[str] = "dealer_tenants"
    master_seed: int = DEFAULT_MASTER_SEED
    out_dir: Path = DEFAULT_OUT_DIR

    def tenant_specs(self) -> list[TenantSpec]:
        return hand_written_tenants(self.master_seed)

    def build(self) -> list[TenantBuild]:
        return [build_tenant(spec) for spec in self.tenant_specs()]

    def make(self) -> dict[str, pd.DataFrame]:
        """One frame per table, all tenants (seen and held-out), visible columns only."""
        builds = self.build()
        return {
            table: _concat([b.tables[table] for b in builds], defn.arrow_schema()).to_pandas(
                types_mapper=pd.ArrowDtype
            )
            for table, defn in TABLES.items()
        }

    def make_in_dir(self, out_dir: Path | None = None) -> Path:
        out = out_dir or self.out_dir
        builds = self.build()
        for split in SPLITS:
            part = [b for b in builds if b.spec.split == split]
            visible, hidden = out / split / "visible", out / split / "hidden"
            (hidden / "truth").mkdir(parents=True, exist_ok=True)
            visible.mkdir(parents=True, exist_ok=True)
            for table, defn in TABLES.items():
                merged = _concat([b.tables[table] for b in part], defn.arrow_schema())
                pq.write_table(merged, visible / f"{table}.parquet")
            for concept in CONCEPTS:
                tables = [b.truth[concept] for b in part if concept in b.truth]
                if tables:
                    pq.write_table(
                        pa.concat_tables(tables), hidden / "truth" / f"{concept}.parquet"
                    )
            _write_jsonl(hidden / "tenants.jsonl", [b.spec.model_dump(mode="json") for b in part])
            _write_jsonl(hidden / "concept_rules.jsonl", [r for b in part for r in b.concept_rules])
            _write_jsonl(hidden / "column_usage.jsonl", [r for b in part for r in b.column_usage])
            _write_jsonl(hidden / "questions.jsonl", [q for b in part for q in b.questions])
            (hidden / "run.json").write_text(json.dumps({"master_seed": self.master_seed}) + "\n")
            _write_jsonl(
                hidden / "exceptions.jsonl",
                [{"tenant_id": b.spec.tenant_id, "events": b.exceptions} for b in part],
            )
        return out
