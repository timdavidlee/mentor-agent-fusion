"""Exception events: real dealer events that make some rules wrong.

Each event lists the (concept, rung) rules it breaks. It is only generated at a tenant
that uses none of them (spec section 7, rule 4).
"""

from generator.population import TenantSpec

BREAKS: dict[str, frozenset[tuple[str, int]]] = {
    # available to sell, rung 3
    "unit_held_without_order": frozenset({("available_to_sell", 3)}),
    "unit_in_transit_to_yard": frozenset({("available_to_sell", 3)}),
    "for_sale_unit_off_yard": frozenset({("available_to_sell", 3)}),
    # booked sale, rung 3 (and the other invoice-link rules)
    "deposit_invoice_on_dead_order": frozenset({("booked_sale", 3), ("available_to_sell", 3)}),
    "sale_invoice_without_order_link": frozenset(
        {("booked_sale", 3), ("available_to_sell", 3), ("sale_date", 3)}
    ),
    # internal work, rung 3
    "rental_damage_billed_to_renter": frozenset({("internal_work", 3)}),
    "rework_absorbed_on_customer_unit": frozenset({("internal_work", 3)}),
}


def allowed(spec: TenantSpec, event: str) -> bool:
    for concept, rung in BREAKS[event]:
        choice = spec.concepts.get(concept)
        if choice is not None and choice.rung == rung:
            return False
    return True
