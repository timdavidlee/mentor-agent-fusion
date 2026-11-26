"""Generator rules that the acceptance checks rely on but do not show directly."""

import pytest

from generator.concepts import CONCEPTS
from generator.population import tenant_a, tenant_c
from generator.render import HABIT_COLUMNS, relied_columns
from generator.simulate import simulate
from generator.simulate.exceptions import BREAKS, allowed


def test_exception_events_skip_tenants_whose_rules_they_break() -> None:
    a = simulate(tenant_a(1))
    for event in a.exceptions:
        assert allowed(a.spec, event), event
    # A decides available to sell and booked sale by rule 3: no invoice-link exceptions
    assert "deposit_invoice_on_dead_order" not in a.exceptions
    assert "sale_invoice_without_order_link" not in a.exceptions
    assert "unit_held_without_order" not in a.exceptions


def test_tenant_c_gets_the_exceptions_that_make_rule_3_wrong() -> None:
    c = simulate(tenant_c(1))
    for event in BREAKS:
        if allowed(c.spec, event):
            assert c.exceptions.get(event, 0) > 0, event


def test_habits_never_touch_rule_columns() -> None:
    for spec in (tenant_a(1), tenant_c(1)):
        assert not relied_columns(spec) & set(HABIT_COLUMNS)


def test_product_line_rule_3_rejects_a_department_that_misreads_a_line() -> None:
    spec = tenant_c(1)
    depts = [
        d.model_copy(update={"sells_lines": ["construction", "agriculture"]})
        if d.code == "AGR"
        else d
        for d in spec.departments
    ]
    with pytest.raises(ValueError, match="construction"):
        CONCEPTS["product_line"].validate(spec.model_copy(update={"departments": depts}))


def test_truth_decided_before_rendering() -> None:
    world = simulate(tenant_c(1))
    # simulation alone fills the truth for every concept at its grain
    for name, concept in CONCEPTS.items():
        assert len(world.truth[name]) == len(world.rows[concept.grain]), name
    # and leaves the concept-owned nominal columns unwritten
    assert all(m["category"] is None for m in world.rows["equipment_model"])
