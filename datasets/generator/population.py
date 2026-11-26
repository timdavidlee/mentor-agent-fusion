"""Tenant specs. Milestone 1: tenants A and C from `concepts.md`, written by hand."""

import hashlib
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

Line = Literal["construction", "agriculture", "compact"]
LocationType = Literal["sales_yard", "rental_branch", "service_shop", "parts_depot", "head_office"]


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LocationSpec(Frozen):
    code: str
    name: str
    location_type: LocationType
    region: str | None
    city: str
    state: str
    parent_code: str | None = None
    stocks_lines: list[Line] = []  # lines whose sale stock stands at this yard


class DepartmentSpec(Frozen):
    code: str
    name: str
    department_type: Literal["sales", "service", "parts", "rental", "admin"]
    sells_lines: list[Line] = []  # equipment lines this sales department sells
    headcount: int


class Size(Frozen):
    units: int  # equipment rows on record, dealer stock plus customer-owned
    customers: int
    parts: int
    parts_orders_per_year: int


class BusinessMix(Frozen):
    """Shape of the business. Drawn from the archetype in milestone 3."""

    line_mix: dict[Line, float]
    customer_unit_share: float  # units on record that the dealer never owned
    fleet_share: float  # dealer-acquired units that join the rental fleet
    new_share: float
    stock_dwell_days: float
    quotes_per_unit: float
    trade_in_rate: float
    service_visits_per_year: float
    warranty_rate: float
    rework_rate: float
    fleet_repair_rate: float
    rental_damage_rate: float
    voided_deal_rate: float
    # exception events; generated only where no rule of the tenant is broken by them
    hold_share: float = 0.0
    in_transit_share: float = 0.0
    off_yard_share: float = 0.0
    dead_deposit_rate: float = 0.0
    unlinked_invoice_rate: float = 0.0


class ConceptChoice(Frozen):
    rung: Literal[1, 2, 3]
    params: dict[str, list[str]] = {}


class Habits(Frozen):
    notes_rate: float  # share of rows whose notes column is filled
    meter_blank_rate: float
    address_blank_rate: float
    serial_blank_rate: float


class TenantSpec(Frozen):
    tenant_id: int
    tenant_code: str
    name: str
    archetype: str
    split: Literal["seen", "held_out"]
    seed: int
    as_of_date: date
    history_years: int
    size: Size
    mix: BusinessMix
    locations: list[LocationSpec]
    departments: list[DepartmentSpec]
    concepts: dict[str, ConceptChoice]
    vocabulary: dict[str, list[str]]
    habits: Habits
    # policy truths the simulation reads (not physical fact)
    idle_fleet_is_for_sale: bool


def derive_seed(master_seed: int, tenant_id: int) -> int:
    digest = hashlib.sha256(f"{master_seed}:{tenant_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def tenant_a(master_seed: int) -> TenantSpec:
    """Single-yard family dealer."""
    return TenantSpec(
        tenant_id=11,
        tenant_code="BRN",
        name="Brennan Equipment",
        archetype="single_yard_family_dealer",
        split="seen",
        seed=derive_seed(master_seed, 11),
        as_of_date=date(2026, 6, 30),
        history_years=6,
        size=Size(units=300, customers=220, parts=80, parts_orders_per_year=40),
        mix=BusinessMix(
            line_mix={"construction": 0.7, "agriculture": 0.18, "compact": 0.12},
            customer_unit_share=0.2,
            fleet_share=0.18,
            new_share=0.6,
            stock_dwell_days=150,
            quotes_per_unit=1.0,
            trade_in_rate=0.15,
            service_visits_per_year=1.0,
            warranty_rate=0.15,
            rework_rate=0.015,
            fleet_repair_rate=0.6,
            rental_damage_rate=0.45,
            voided_deal_rate=0.03,
        ),
        locations=[
            LocationSpec(
                code="MAIN",
                name="Brennan Yard",
                location_type="sales_yard",
                region=None,
                city="Millbrook",
                state="IA",
                stocks_lines=["construction", "agriculture", "compact"],
            )
        ],
        departments=[
            DepartmentSpec(
                code="SALES",
                name="Sales",
                department_type="sales",
                sells_lines=["construction", "agriculture", "compact"],
                headcount=2,
            ),
            DepartmentSpec(code="SVC", name="Service", department_type="service", headcount=3),
            DepartmentSpec(code="PARTS", name="Parts", department_type="parts", headcount=1),
            DepartmentSpec(code="OFC", name="Office", department_type="admin", headcount=2),
        ],
        concepts={
            "product_line": ConceptChoice(rung=1),
            "available_to_sell": ConceptChoice(rung=3),
            "internal_work": ConceptChoice(
                rung=2, params={"house_account_classes": ["HSE", "SHOP"]}
            ),
            "booked_sale": ConceptChoice(rung=3),
        },
        vocabulary={
            "customer.account_class": ["RET", "CON", "FRM", "GOV", "OEM", "HSE", "SHOP"],
            "customer.house_classes": ["HSE", "SHOP"],
            "customer.manufacturer_class": ["OEM"],
            "equipment.status": ["available", "sold"],
            "equipment.hold_code": [],
            "sales_order.status": ["open", "closed", "cancelled"],
            "sales_order.order_type": ["equipment", "parts"],
            "work_order.work_order_type": ["customer"],
            "work_order_line.operation_code": ["LAB", "DIAG", "PM", "PDI", "RECON", "WAR"],
            "part.part_class": ["FLT", "LUB", "HYD", "ENG", "UC", "ELEC"],
        },
        habits=Habits(
            notes_rate=0.55, meter_blank_rate=0.45, address_blank_rate=0.15, serial_blank_rate=0.1
        ),
        idle_fleet_is_for_sale=True,
    )


def tenant_c(master_seed: int) -> TenantSpec:
    """Multi-region distributor, scaled down from 25 locations to 10."""
    yard = "sales_yard"
    return TenantSpec(
        tenant_id=13,
        tenant_code="NLM",
        name="Northline Machinery",
        archetype="multi_region_distributor",
        split="held_out",
        seed=derive_seed(master_seed, 13),
        as_of_date=date(2026, 9, 30),
        history_years=3,
        size=Size(units=1500, customers=900, parts=300, parts_orders_per_year=400),
        mix=BusinessMix(
            line_mix={"construction": 0.5, "agriculture": 0.25, "compact": 0.25},
            customer_unit_share=0.15,
            fleet_share=0.2,
            new_share=0.7,
            stock_dwell_days=200,
            quotes_per_unit=0.6,
            trade_in_rate=0.12,
            service_visits_per_year=0.7,
            warranty_rate=0.15,
            rework_rate=0.03,
            fleet_repair_rate=0.35,
            rental_damage_rate=0.12,
            voided_deal_rate=0.02,
            hold_share=0.2,
            in_transit_share=0.08,
            off_yard_share=0.2,
            dead_deposit_rate=0.2,
            unlinked_invoice_rate=0.08,
        ),
        locations=[
            LocationSpec(
                code="H01",
                name="Northline Head Office",
                location_type="head_office",
                region="Central",
                city="Des Plaines",
                state="IL",
            ),
            LocationSpec(
                code="Y02",
                name="Rockford Yard",
                location_type=yard,
                region="North",
                city="Rockford",
                state="IL",
                stocks_lines=["construction"],
            ),
            LocationSpec(
                code="Y05",
                name="Peoria Yard",
                location_type=yard,
                region="South",
                city="Peoria",
                state="IL",
                stocks_lines=["construction", "agriculture"],
            ),
            LocationSpec(
                code="A08",
                name="Bloomington Ag Center",
                location_type=yard,
                region="South",
                city="Bloomington",
                state="IL",
                stocks_lines=["agriculture"],
            ),
            LocationSpec(
                code="C14",
                name="Elgin Compact Store",
                location_type=yard,
                region="North",
                city="Elgin",
                state="IL",
                parent_code="Y02",
                stocks_lines=["compact"],
            ),
            LocationSpec(
                code="C21",
                name="Springfield Compact Store",
                location_type=yard,
                region="South",
                city="Springfield",
                state="IL",
                parent_code="Y05",
                stocks_lines=["compact"],
            ),
            LocationSpec(
                code="R03",
                name="Joliet Rental",
                location_type="rental_branch",
                region="North",
                city="Joliet",
                state="IL",
            ),
            LocationSpec(
                code="R06",
                name="Decatur Rental",
                location_type="rental_branch",
                region="South",
                city="Decatur",
                state="IL",
            ),
            LocationSpec(
                code="S04",
                name="Central Service Shop",
                location_type="service_shop",
                region="Central",
                city="Bloomington",
                state="IL",
            ),
            LocationSpec(
                code="P09",
                name="Parts Distribution",
                location_type="parts_depot",
                region="Central",
                city="Normal",
                state="IL",
            ),
        ],
        departments=[
            DepartmentSpec(
                code="CON",
                name="Equipment Sales",
                department_type="sales",
                sells_lines=["construction", "compact"],
                headcount=10,
            ),
            DepartmentSpec(
                code="AGR",
                name="Ag Sales",
                department_type="sales",
                sells_lines=["agriculture"],
                headcount=4,
            ),
            DepartmentSpec(
                code="TURF",
                name="Turf and Grounds",
                department_type="sales",
                sells_lines=["agriculture"],
                headcount=2,
            ),
            DepartmentSpec(code="RENT", name="Rental", department_type="rental", headcount=8),
            DepartmentSpec(
                code="SVC", name="Shop Service", department_type="service", headcount=16
            ),
            DepartmentSpec(
                code="FLD", name="Field Service", department_type="service", headcount=6
            ),
            DepartmentSpec(code="PARTS", name="Parts", department_type="parts", headcount=8),
            DepartmentSpec(code="ADM", name="Administration", department_type="admin", headcount=6),
        ],
        concepts={
            "product_line": ConceptChoice(
                rung=3,
                params={
                    "ag_department_codes": ["AGR", "TURF"],
                    "compact_location_codes": ["C14", "C21"],
                },
            ),
            "available_to_sell": ConceptChoice(
                rung=2,
                params={"status_list": ["available", "ready"], "hold_codes": ["DEP", "QC", "TRF"]},
            ),
            "internal_work": ConceptChoice(rung=1),
            "booked_sale": ConceptChoice(
                rung=2, params={"status_list": ["invoiced", "delivered", "closed"]}
            ),
        },
        vocabulary={
            "customer.account_class": ["A1", "A2", "B1", "GOVT", "MFR", "DLR"],
            "customer.house_classes": ["DLR"],
            "customer.manufacturer_class": ["MFR"],
            "equipment.status": ["available", "ready", "on_rent", "fleet", "sold", "in_transit"],
            "equipment.hold_code": ["DEP", "QC", "TRF", "MKT"],
            "sales_order.status": ["open", "invoiced", "delivered", "closed", "cancelled"],
            "sales_order.order_type": ["equipment", "parts", "quote"],
            "work_order.work_order_type": ["customer", "warranty", "internal"],
            "work_order_line.operation_code": ["L100", "L200", "D10", "P50", "S20", "R30", "W90"],
            "part.part_class": ["F1", "F2", "HY", "EN", "UC", "EL", "LB"],
        },
        habits=Habits(
            notes_rate=0.05, meter_blank_rate=0.05, address_blank_rate=0.03, serial_blank_rate=0.01
        ),
        idle_fleet_is_for_sale=False,
    )


def hand_written_tenants(master_seed: int) -> list[TenantSpec]:
    return [tenant_a(master_seed), tenant_c(master_seed)]
