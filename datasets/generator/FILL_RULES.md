# Fill rules, milestone 1

The spec (section 6) asks for each concept's exact fill rules to be added to
`datasets/design/concepts.md`. This session was not allowed to edit the design files,
so they are here until someone merges them into `concepts.md`.

**Departure from `concepts.md`.** For the three rule-3 cases above (A's
`equipment.status`, A's `sales_order.status`, C's `equipment_model.category`), the
nominal field is now partly right, not wholly ignored as "Nominal column when ignored"
says ("never updated", "stays 'open'", "marketing family or null"). That keeps every
wrong rule within the spec's 5% to 40% band with no exemption. The shares are constants
in the concept modules: `SOLD_STATUS_UPDATED`, `BOOKED_CLOSED`, `MODELS_WITHOUT_LINE`.
`concepts.md` should be updated to match.

Tenants: A = `BRN` (tenant 11, seen), C = `NLM` (tenant 13, held-out, scaled down to
10 locations and 1,500 units on record).

## Simulation facts the rules read

- Every unit has a hidden line, taken from its model. A unit is one of these: dealer
  stock (`acquired_date` set), or a customer's own unit brought in for service
  (`acquired_date`, `acquisition_cost` and `stock_number` null, `ownership_type =
  'customer'`).
- Its state on the as-of date is one of: `in_stock`, `on_rent`, `fleet_idle`, `sold`,
  `customer`. Units sold on a booked order carry the buyer in `owner_customer_id` and have
  a null location.
- A traded-in unit always gets a new equipment row. The dealer never takes back a unit it
  sold, so an old sale invoice never sits on a unit that is back in stock.

## 1. Product line (truth at `equipment`, per model)

| Rung | Tenant | `equipment_model.category` | Structure |
| --- | --- | --- | --- |
| 1 | A | The true line | One `SALES` department and one location (`MAIN`) sell every line |
| 3 | C | The true line on 75% of models; on the other 25%, a marketing family (`300 Series`, `Pro Line`, ...) or null | Agriculture is sold only by `AGR`/`TURF`; compact only by `CON` at `C14`/`C21`; construction only by `CON` at `Y02`/`Y05`. `ProductLine.validate` rejects any department and location pair that would read as another line |

Rung 2 encoder: not built (milestone 2).

## 3. Available to sell (truth at `equipment`)

Truth: `in_stock`, not held, not in transit; at a tenant with `idle_fleet_is_for_sale`,
also `fleet_idle`.

| Rung | Tenant | `status` / `hold_code` | Structure |
| --- | --- | --- | --- |
| 3 | A | `status = 'available'` at receipt; changed to `sold` on 80% of sold units, never for rentals; null on customer units. `hold_code` null | One location, a `sales_yard`. No holds, no units in transit, no deposit invoices on dead orders, no unlinked invoices |
| 2 | C | Sellable: `available` or `ready`, sometimes with the unlisted hold `MKT`. Held: `available` with `DEP`/`QC`/`TRF`. Otherwise `in_transit`, `on_rent`, `fleet`, `sold`, or null for customer units | Exception events: holds, units in transit to a yard, for-sale units standing at a rental branch or the service shop |

Rung 1 encoder: not built.

## 5. Internal work (truth at `work_order`)

Truth: work the dealer pays for itself: setup (PDI), reconditioning, rental-fleet
repair, and rework absorbed on a customer's unit. Internal work is billed to a house
account (rework is billed to the customer's own account).

| Rung | Tenant | `is_internal` | Structure |
| --- | --- | --- | --- |
| 2 | A | True on 20% of internal work, and on all absorbed rework; false otherwise. House accounts `HSE` (shop) and `SHOP` (fleet) mark the rest | No external work is billed to a house account |
| 1 | C | Equals the truth | House account `DLR` |

Exception events at both tenants: rental damage repaired on a dealer unit and billed to
the renter, and rework absorbed on a customer's unit. Rule 3 also misreads all setup and
reconditioning work on units sold since, because it reads the current owner.

Rung 3 encoder: not built.

## 8. Booked sale (truth at `sales_order`)

Truth: booked equipment deals and booked parts orders. Not booked: quotes, abandoned
parts orders, voided deals (invoice `void`), and dead deals with a deposit invoice.

| Rung | Tenant | `status` / `order_type` | Structure |
| --- | --- | --- | --- |
| 3 | A | Booked: `closed` on 70%, left `open` on the rest. Otherwise `open`, except `cancelled` on voided deals and on 30% of abandoned parts orders. `order_type` is `equipment` or `parts`: A does not mark quotes | Every booked order has one live linked invoice; nothing else does |
| 2 | C | Booked: `closed` (55%) or `invoiced`/`delivered`. Quotes: `order_type = 'quote'`, status `open`, or `closed` once expired (25%). Abandoned parts orders: `open`/`cancelled`. Voided and dead deals: `cancelled` | Exception events: deposit invoices on dead deals; 8% of booked equipment invoices entered without the order link |

Rung 1 encoder: not built.

## Exception events and the rules they break

Listed in `simulate/exceptions.py`. An event is generated only at a tenant that uses
none of the rules it breaks.

| Event | Breaks |
| --- | --- |
| `unit_held_without_order`, `unit_in_transit_to_yard`, `for_sale_unit_off_yard` | Available to sell, rule 3 |
| `deposit_invoice_on_dead_order` | Booked sale rule 3, available to sell rule 3 |
| `sale_invoice_without_order_link` | Booked sale rule 3, available to sell rule 3, sale date rule 3 |
| `rental_damage_billed_to_renter`, `rework_absorbed_on_customer_unit` | Internal work, rule 3 |

## Habits

Habits may change only these columns, and only when none of the tenant's rules reads
them (`render.HABIT_COLUMNS`): the five `notes` columns, `equipment.meter_reading`,
`work_order.meter_reading`, `customer.address_line` and `equipment.serial_number`.
