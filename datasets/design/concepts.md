# Concept catalogue and tenant population (draft)

Status: **proposed, not yet confirmed.** Domain: a machinery sales + services
dealer. Schema: [`schema.sql`](schema.sql).

## What varies between tenants

Every tenant has the same tables and columns. What differs is the **rule** a
tenant uses to decide a business concept such as "rental fleet unit" or
"warranty work". The same question therefore needs a different query at each
tenant.

Each concept below has three rules ("rungs"), and a tenant picks one rung per
concept:

1. **One field.** The column nominally meant for the concept is filled and
   trusted.
2. **One field plus codes.** The field is partly right; a tenant-specific list
   of codes overrides or extends it.
3. **A combination across tables.** The nominal field is ignored; the concept
   follows from departments, locations, account types or related records.

For each concept the generator first decides the **hidden truth** for every
row, then writes the columns so that the tenant's rung reproduces that truth.
Columns belonging to the other rungs are filled as described under "Nominal
column when ignored", so applying the wrong rung gives a wrong answer.

**A tenant's rule is consistent.** For each concept a tenant uses exactly one
rung, with one set of code lists, for every row, every location and its whole
history. Tenant A always decides product line from the single field; tenant B
always decides it from the field plus its two other filters. Rules differ
between tenants, never within one. The generator must check this: for every
tenant and concept, the tenant's own rule reproduces the hidden truth on
every row.

Rung 3 is not a safe default. At tenants on rung 1 or 2 the generator plants
rows where the rung 3 rule disagrees with the tenant's own rule; each concept
lists them under "Rows where rung 3 is wrong elsewhere".

`equipment.owner_customer_id` is the one column every tenant fills reliably:
null means the dealer owns the unit.

Code lists (`'CTL'`, `'R%'`, `'HSE'` and so on) are examples. Each tenant has
its own lists, so two tenants on the same rung still need different queries.

Dates in the rules assume an as-of date of 2026-06-30. Each tenant has its own,
in `tenant.as_of_date`.

All tenants live in one database and every table has a `tenant_id` column. The
rules below are written for one tenant: to run one, filter its outermost table
on `tenant_id`. Ids are unique across tenants, so the joins and subqueries need
no tenant condition of their own.

## Concepts

### 1. Product line

- **Hidden truth:** every unit belongs to one line: construction, agriculture
  or compact.
- **Question:** what was equipment sales revenue by product line in 2025?
- **Nominal column when ignored:** `equipment_model.category` holds the
  manufacturer's marketing family ("300 Series"), or is null.
- **Rows where rung 3 is wrong elsewhere:** departments are organised by
  function, so one sales department sells every line from every location.
- **Also depends on:** Booked sale, for which orders count as revenue.

```sql
-- Rung 1: the model's category
SELECT e.equipment_id, m.category AS product_line
FROM equipment e
JOIN equipment_model m ON m.model_id = e.model_id;

-- Rung 2: category, with certain class codes reassigned
SELECT e.equipment_id,
       CASE WHEN m.class_code IN ('CTL', 'MEX', 'SSL') THEN 'compact'
            ELSE m.category END AS product_line
FROM equipment e
JOIN equipment_model m ON m.model_id = e.model_id;

-- Rung 3: the selling department and location decide the line
SELECT so.sales_order_id,
       CASE WHEN d.department_code IN ('AG', 'TURF') THEN 'agriculture'
            WHEN l.location_code IN ('B07', 'B09') THEN 'compact'
            ELSE 'construction' END AS product_line
FROM sales_order so
JOIN department d ON d.department_id = so.department_id
JOIN location l ON l.location_id = so.location_id;
```

Rung 3 is decided per sales order, not per unit. The generator keeps the two
consistent by selling each unit only through a department and location that
map to its true line.

### 2. Rental fleet unit

- **Hidden truth:** whether the dealer currently holds the unit to rent out.
- **Question:** how many units were in the rental fleet on the as-of date?
- **Nominal column when ignored:** `equipment.ownership_type` stays at the
  entry default `'inventory'` for every dealer-owned unit.
- **Rows where rung 3 is wrong elsewhere:** fleet units bought this month and
  not yet rented; fleet units parked at a sales yard; former rental units
  moved to sale stock but still standing at the rental branch.

```sql
-- Rung 1: ownership type
SELECT e.equipment_id FROM equipment e
WHERE e.ownership_type = 'rental';

-- Rung 2: ownership type, plus units restocked under a rental stock number
SELECT e.equipment_id FROM equipment e
WHERE e.ownership_type = 'rental' OR e.stock_number LIKE 'R%';

-- Rung 3: dealer-owned, kept at a rental branch, and rented at least once
SELECT e.equipment_id FROM equipment e
JOIN location l ON l.location_id = e.location_id
WHERE e.owner_customer_id IS NULL
  AND l.location_type = 'rental_branch'
  AND EXISTS (SELECT 1 FROM rental_contract rc
              WHERE rc.equipment_id = e.equipment_id);
```

### 3. Available to sell

- **Hidden truth:** whether a salesperson could sell the unit today.
- **Question:** how many units are available to sell, by location?
- **Nominal column when ignored:** `equipment.status` is set at receipt and
  never updated, so sold and rented units still read `'available'`.
- **Rows where rung 3 is wrong elsewhere:** units at a sales yard held for
  inspection or a verbal deposit with no order yet; units for sale that stand
  at a rental branch or service shop.

```sql
-- Rung 1: status
SELECT e.equipment_id FROM equipment e
WHERE e.status = 'available';

-- Rung 2: a tenant-specific status list, minus units on hold
SELECT e.equipment_id FROM equipment e
WHERE e.status IN ('available', 'in_stock', 'ready')
  AND (e.hold_code IS NULL OR e.hold_code NOT IN ('DEP', 'QC', 'TRF'));

-- Rung 3: dealer-owned, at a sales yard, not out on rent, not yet invoiced as sold
SELECT e.equipment_id FROM equipment e
JOIN location l ON l.location_id = e.location_id
WHERE e.owner_customer_id IS NULL
  AND l.location_type = 'sales_yard'
  AND NOT EXISTS (SELECT 1 FROM rental_contract rc
                  WHERE rc.equipment_id = e.equipment_id
                    AND rc.status = 'open')
  AND NOT EXISTS (SELECT 1 FROM sales_order_line sol
                  JOIN invoice i ON i.sales_order_id = sol.sales_order_id
                  WHERE sol.equipment_id = e.equipment_id
                    AND sol.line_type = 'equipment'
                    AND i.status <> 'void');
```

### 4. Warranty work

- **Hidden truth:** for every labour and parts line, whether the manufacturer
  pays for it.
- **Question:** what share of 2025 service labour hours was warranty work?
- **Nominal column when ignored:** `work_order.work_order_type` is
  `'customer'` for nearly everything.
- **Rows where rung 3 is wrong elsewhere:** claims the manufacturer rejected,
  later billed to the customer; warranty work claimed in a monthly batch with
  no claim row per work order.

```sql
-- Rung 1: work order type (whole work order is warranty or not)
SELECT wol.work_order_line_id FROM work_order_line wol
JOIN work_order wo ON wo.work_order_id = wol.work_order_id
WHERE wo.work_order_type = 'warranty';

-- Rung 2: work order type, plus warranty operation codes on mixed work orders
SELECT wol.work_order_line_id FROM work_order_line wol
JOIN work_order wo ON wo.work_order_id = wol.work_order_id
WHERE wo.work_order_type = 'warranty' OR wol.operation_code LIKE 'W%';

-- Rung 3: a claim was filed, or the manufacturer is the billed customer
SELECT wol.work_order_line_id FROM work_order_line wol
JOIN work_order wo ON wo.work_order_id = wol.work_order_id
JOIN customer c ON c.customer_id = wo.customer_id
WHERE c.customer_type = 'manufacturer'
   OR EXISTS (SELECT 1 FROM warranty_claim wc
              WHERE wc.work_order_id = wo.work_order_id);
```

### 5. Internal work

- **Hidden truth:** whether the dealer itself bears the cost of the work order
  (rental-fleet repair, pre-delivery inspection, reconditioning).
- **Question:** what was external service revenue last quarter?
- **Nominal column when ignored:** `work_order.is_internal` is false on every
  row.
- **Rows where rung 3 is wrong elsewhere:** rental damage repaired on a
  dealer-owned unit and billed to the renter; rework on a customer's unit
  that the dealer absorbs.

```sql
-- Rung 1: the flag
SELECT wo.work_order_id FROM work_order wo
WHERE wo.is_internal = TRUE;

-- Rung 2: the flag, plus work billed to house accounts
SELECT wo.work_order_id FROM work_order wo
JOIN customer c ON c.customer_id = wo.customer_id
WHERE wo.is_internal = TRUE OR c.account_class IN ('HSE', 'SHOP');

-- Rung 3: the unit worked on belongs to the dealer
SELECT wo.work_order_id FROM work_order wo
JOIN equipment e ON e.equipment_id = wo.equipment_id
WHERE e.owner_customer_id IS NULL;
```

### 6. Active customer

- **Hidden truth:** whether the tenant itself would count the customer in its
  active-customer figure.
- **Question:** how many active customers did the dealer have on the as-of
  date?
- **Nominal column when ignored:** `customer.status` is `'active'` for every
  customer ever created.
- **Rows where rung 3 is wrong elsewhere:** dormant accounts the tenant keeps
  active on purpose; one-off buyers invoiced last year whom the tenant has
  marked inactive.

```sql
-- Rung 1: status
SELECT c.customer_id FROM customer c
WHERE c.status = 'active';

-- Rung 2: status, minus catch-all and non-trading account classes
SELECT c.customer_id FROM customer c
WHERE c.status = 'active'
  AND (c.account_class IS NULL
       OR c.account_class NOT IN ('CASH', 'HSE', 'EMP'));

-- Rung 3: invoiced in the last 24 months, or holding an open rental
SELECT c.customer_id FROM customer c
WHERE EXISTS (SELECT 1 FROM invoice i
              WHERE i.customer_id = c.customer_id
                AND i.invoice_date > '2024-06-30')
   OR EXISTS (SELECT 1 FROM rental_contract rc
              WHERE rc.customer_id = c.customer_id
                AND rc.status = 'open');
```

### 7. Used unit

- **Hidden truth:** whether the unit is used (anything not used is new).
- **Question:** how many dealer-owned units on record are used, and what did
  they cost to acquire?
- **Nominal column when ignored:** `equipment.condition` is `'new'` on every
  row, because it is the entry default.
- **Rows where rung 3 is wrong elsewhere:** demo units with meter time and a
  demo contract that the tenant still sells as new; used units bought at
  auction with a blank meter reading.

```sql
-- Rung 1: condition
SELECT e.equipment_id FROM equipment e
WHERE e.condition = 'used';

-- Rung 2: condition, plus used and demo stock-number prefixes
SELECT e.equipment_id FROM equipment e
WHERE e.condition = 'used'
   OR e.stock_number LIKE 'U%'
   OR e.stock_number LIKE 'D%';

-- Rung 3: taken in trade, rented out before, or carrying real meter time
SELECT e.equipment_id FROM equipment e
WHERE e.meter_reading > 10
   OR EXISTS (SELECT 1 FROM rental_contract rc
              WHERE rc.equipment_id = e.equipment_id)
   OR EXISTS (SELECT 1 FROM sales_order_line sol
              WHERE sol.equipment_id = e.equipment_id
                AND sol.line_type = 'trade_in');
```

### 8. Booked sale

- **Hidden truth:** whether a sales order is a real, completed sale. Some
  tenants also keep quotes and abandoned deals in `sales_order`.
- **Question:** how many equipment sales were booked in 2025, and for how
  much?
- **Nominal column when ignored:** `sales_order.status` stays `'open'` after
  the deal is done.
- **Rows where rung 3 is wrong elsewhere:** deposit invoices on orders that
  were never completed; completed orders whose invoice was entered without a
  link to the order.

```sql
-- Rung 1: status
SELECT so.sales_order_id FROM sales_order so
WHERE so.status = 'closed';

-- Rung 2: a tenant-specific status list, minus quote-type orders
SELECT so.sales_order_id FROM sales_order so
WHERE so.status IN ('invoiced', 'delivered', 'closed')
  AND so.order_type <> 'quote';

-- Rung 3: a live invoice exists for the order
SELECT so.sales_order_id FROM sales_order so
WHERE EXISTS (SELECT 1 FROM invoice i
              WHERE i.sales_order_id = so.sales_order_id
                AND i.status <> 'void');
```

### 9. Service department

- **Hidden truth:** every work order belongs to one service department: shop
  service, field service or component rebuild.
- **Question:** what were service labour hours by service department in 2025?
- **Nominal column when ignored:** `work_order.department_id` points at a
  single catch-all `'SVC'` department on every work order.
- **Rows where rung 3 is wrong elsewhere:** shop technicians sent out on a
  field call; field technicians doing shop work between calls; rebuilds done
  at an ordinary branch.

```sql
-- Rung 1: the work order's department
SELECT wo.work_order_id, d.department_code AS service_department
FROM work_order wo
JOIN department d ON d.department_id = wo.department_id;

-- Rung 2: the department, except that travel operation codes mean field service
SELECT wo.work_order_id,
       CASE WHEN EXISTS (SELECT 1 FROM work_order_line wol
                         WHERE wol.work_order_id = wo.work_order_id
                           AND wol.operation_code IN ('TRVL', 'MILE'))
            THEN 'FIELD' ELSE d.department_code END AS service_department
FROM work_order wo
JOIN department d ON d.department_id = wo.department_id;

-- Rung 3: the building, then the lead technician's own department
SELECT wo.work_order_id,
       CASE WHEN l.location_code IN ('B03', 'B11') THEN 'REBUILD'
            WHEN td.department_code = 'FLD' THEN 'FIELD'
            ELSE 'SHOP' END AS service_department
FROM work_order wo
JOIN location l ON l.location_id = wo.location_id
JOIN employee t ON t.employee_id = wo.technician_id
JOIN department td ON td.department_id = t.department_id;
```

### 10. Sales region

- **Hidden truth:** every sales order belongs to one sales region.
- **Question:** what were equipment sales by sales region in 2025?
- **Nominal column when ignored:** `location.region` is null, or holds the
  manufacturer's district code for the branch.
- **Rows where rung 3 is wrong elsewhere:** salespeople based at one branch
  who sell out of another; house sales with no salesperson.
- **Also depends on:** Booked sale, for which orders count.

```sql
-- Rung 1: the selling location's region
SELECT so.sales_order_id, l.region AS sales_region
FROM sales_order so
JOIN location l ON l.location_id = so.location_id;

-- Rung 2: the location's region, except account classes run as their own region
SELECT so.sales_order_id,
       CASE WHEN c.account_class IN ('NAT', 'GOV') THEN 'National accounts'
            ELSE l.region END AS sales_region
FROM sales_order so
JOIN location l ON l.location_id = so.location_id
JOIN customer c ON c.customer_id = so.customer_id;

-- Rung 3: the hub branch above the salesperson's home location
SELECT so.sales_order_id, COALESCE(hub.name, home.name) AS sales_region
FROM sales_order so
JOIN employee sp ON sp.employee_id = so.salesperson_id
JOIN location home ON home.location_id = sp.location_id
LEFT JOIN location hub ON hub.location_id = home.parent_location_id;
```

### 11. Type of work

- **Hidden truth:** every work order is one kind of work: maintenance,
  repair, inspection, setup or rebuild. This is separate from who pays for it
  (concepts 4 and 5).
- **Question:** how many work orders of each type of work were closed in
  2025?
- **Nominal column when ignored:** `work_order.service_type` is null, or
  `'repair'` on every row.
- **Rows where rung 3 is wrong elsewhere:** repairs that happen to use a
  filter or oil; setup work done by the main shop; rebuilds done outside the
  rebuild centre.

```sql
-- Rung 1: service type
SELECT wo.work_order_id, wo.service_type AS type_of_work
FROM work_order wo;

-- Rung 2: service type, overridden by operation-code prefixes on the lines
SELECT wo.work_order_id,
       CASE WHEN EXISTS (SELECT 1 FROM work_order_line wol
                         WHERE wol.work_order_id = wo.work_order_id
                           AND wol.operation_code LIKE 'PM%')
            THEN 'maintenance'
            WHEN EXISTS (SELECT 1 FROM work_order_line wol
                         WHERE wol.work_order_id = wo.work_order_id
                           AND wol.operation_code LIKE 'INSP%')
            THEN 'inspection'
            ELSE wo.service_type END AS type_of_work
FROM work_order wo;

-- Rung 3: the department, the building, then the class of parts used
SELECT wo.work_order_id,
       CASE WHEN d.department_code IN ('PDI', 'RECON') THEN 'setup'
            WHEN l.location_code IN ('B03', 'B11') THEN 'rebuild'
            WHEN EXISTS (SELECT 1 FROM work_order_line wol
                         JOIN part p ON p.part_id = wol.part_id
                         WHERE wol.work_order_id = wo.work_order_id
                           AND p.part_class IN ('FLT', 'LUB'))
            THEN 'maintenance'
            ELSE 'repair' END AS type_of_work
FROM work_order wo
JOIN department d ON d.department_id = wo.department_id
JOIN location l ON l.location_id = wo.location_id;
```

### 12. Completed work order

- **Hidden truth:** whether the work itself is finished.
- **Question:** how many work orders were completed in 2025?
- **Nominal column when ignored:** `work_order.status` stays `'open'` long
  after the unit has left the shop.
- **Rows where rung 3 is wrong elsewhere:** jobs invoiced in stages while work
  continues; finished internal work orders that never get an invoice.

```sql
-- Rung 1: status
SELECT wo.work_order_id FROM work_order wo
WHERE wo.status = 'complete';

-- Rung 2: a status list, plus closed internal and warranty jobs that skip invoicing
SELECT wo.work_order_id FROM work_order wo
WHERE wo.status IN ('complete', 'invoiced', 'closed')
   OR (wo.work_order_type IN ('internal', 'warranty')
       AND wo.closed_date IS NOT NULL);

-- Rung 3: a closed date is set and a live invoice exists
SELECT wo.work_order_id FROM work_order wo
WHERE wo.closed_date IS NOT NULL
  AND EXISTS (SELECT 1 FROM invoice i
              WHERE i.work_order_id = wo.work_order_id
                AND i.status <> 'void');
```

### 13. Past-due invoice

- **Hidden truth:** whether the tenant treats the invoice as past due on the
  as-of date.
- **Question:** what was total past-due receivables on the as-of date?
- **Nominal column when ignored:** `invoice.status` is only ever `'open'` or
  `'paid'`, and `invoice.due_date` is a copy of `invoice_date`.
- **Rows where rung 3 is wrong elsewhere:** part-paid invoices on an agreed
  payment plan; payments received but entered without an invoice link.

```sql
-- Rung 1: status
SELECT i.invoice_id FROM invoice i
WHERE i.status = 'overdue';

-- Rung 2: open and past the due date, minus account classes on extended terms
SELECT i.invoice_id FROM invoice i
JOIN customer c ON c.customer_id = i.customer_id
WHERE i.status = 'open'
  AND i.due_date < '2026-06-30'
  AND (c.account_class IS NULL OR c.account_class NOT IN ('GOV', 'NAT'));

-- Rung 3: not fully paid, and older than the customer's payment terms allow
SELECT i.invoice_id FROM invoice i
JOIN customer c ON c.customer_id = i.customer_id
WHERE i.status <> 'void'
  AND i.total_amount > (SELECT COALESCE(SUM(p.amount), 0) FROM payment p
                        WHERE p.invoice_id = i.invoice_id)
  AND ((c.payment_terms = 'NET10' AND i.invoice_date < '2026-06-20')
    OR (c.payment_terms = 'NET60' AND i.invoice_date < '2026-05-01')
    OR (COALESCE(c.payment_terms, '') NOT IN ('NET10', 'NET60')
        AND i.invoice_date < '2026-05-31'));
```

### 14. Unit cost

A measure, not a bucket: the rungs give different amounts for the same unit.

- **Hidden truth:** the tenant's own cost basis for each unit it has owned.
- **Question:** what was total gross margin on equipment units sold in 2025?
- **Nominal column on other rungs:** at rung 2 and 3 tenants
  `equipment.acquisition_cost` is the bare purchase price.
- **Rows where rung 3 is wrong elsewhere:** at rung 1 tenants
  `acquisition_cost` is entered as landed cost, so adding work orders counts
  freight and setup twice.
- **Also depends on:** Booked sale, Sale date, and (rung 3) Internal work.

```sql
-- Rung 1: acquisition cost
SELECT e.equipment_id, e.acquisition_cost AS unit_cost
FROM equipment e;

-- Rung 2: acquisition cost plus freight and setup lines charged to the unit
SELECT e.equipment_id,
       e.acquisition_cost + COALESCE((
           SELECT SUM(wol.unit_cost * COALESCE(wol.quantity, wol.labor_hours, 1))
           FROM work_order wo
           JOIN work_order_line wol ON wol.work_order_id = wo.work_order_id
           WHERE wo.equipment_id = e.equipment_id
             AND wol.operation_code IN ('FRT', 'PDI', 'SETUP')), 0) AS unit_cost
FROM equipment e;

-- Rung 3: acquisition cost plus every internal work order on the unit
-- (is_internal stands in for the tenant's own internal-work rule)
SELECT e.equipment_id,
       e.acquisition_cost + COALESCE((
           SELECT SUM(wol.unit_cost * COALESCE(wol.quantity, wol.labor_hours, 1))
           FROM work_order wo
           JOIN work_order_line wol ON wol.work_order_id = wo.work_order_id
           WHERE wo.equipment_id = e.equipment_id
             AND wo.is_internal = TRUE), 0) AS unit_cost
FROM equipment e;
```

### 15. Sale date

A measure, not a bucket: the rungs give different dates for the same order.

- **Hidden truth:** the date on which the tenant counts the sale.
- **Question:** what were equipment sales in December 2025?
- **Nominal column when ignored:** `sales_order.order_date` is the day the
  quote was first typed in.
- **Rows where rung 3 is wrong elsewhere:** financed deals paid off in
  instalments long after delivery.
- **Also depends on:** Booked sale.

```sql
-- Rung 1: order date
SELECT so.sales_order_id, so.order_date AS sale_date
FROM sales_order so;

-- Rung 2: order date, except order types that count from their first invoice
SELECT so.sales_order_id,
       CASE WHEN so.order_type IN ('rent_to_own', 'consignment')
            THEN (SELECT MIN(i.invoice_date) FROM invoice i
                  WHERE i.sales_order_id = so.sales_order_id
                    AND i.status <> 'void')
            ELSE so.order_date END AS sale_date
FROM sales_order so;

-- Rung 3: the day the last payment on the order's invoices arrived
SELECT so.sales_order_id,
       (SELECT MAX(p.payment_date) FROM invoice i
        JOIN payment p ON p.invoice_id = i.invoice_id
        WHERE i.sales_order_id = so.sales_order_id
          AND i.status <> 'void') AS sale_date
FROM sales_order so;
```

### 16. Revenue branch

- **Hidden truth:** the location credited with each invoice's revenue.
- **Question:** what was invoiced revenue by branch in 2025?
- **Nominal column when ignored:** `invoice.location_id` is head office,
  where the billing clerk sits, on every invoice.
- **Rows where rung 3 is wrong elsewhere:** customers who buy from a branch
  other than their home branch.

```sql
-- Rung 1: the invoice's location
SELECT i.invoice_id, i.location_id AS revenue_location_id
FROM invoice i;

-- Rung 2: the invoice's location, except listed satellite yards roll up to their parent
SELECT i.invoice_id,
       CASE WHEN l.location_code IN ('B07S', 'B09S') THEN l.parent_location_id
            ELSE i.location_id END AS revenue_location_id
FROM invoice i
JOIN location l ON l.location_id = i.location_id;

-- Rung 3: the customer's home branch, else their salesperson's home branch
SELECT i.invoice_id,
       COALESCE(c.home_location_id, sp.location_id) AS revenue_location_id
FROM invoice i
JOIN customer c ON c.customer_id = i.customer_id
LEFT JOIN employee sp ON sp.employee_id = c.salesperson_id;
```

### 17. Customer as a counting unit

- **Hidden truth:** which account rows the tenant regards as one customer.
- **Question:** how many distinct customers were invoiced in 2025?
- **Nominal column when ignored:** `customer.parent_customer_id` is null on
  every row, and the same business appears under several accounts.
- **Rows where rung 3 is wrong elsewhere:** separate businesses that share a
  name and postcode, such as franchisees at one address.

```sql
-- Rung 1: every account is a customer
SELECT c.customer_id, c.customer_id AS counted_as
FROM customer c;

-- Rung 2: accounts roll up to their parent, except classes kept separate
SELECT c.customer_id,
       CASE WHEN c.account_class IN ('GOV') THEN c.customer_id
            ELSE COALESCE(c.parent_customer_id, c.customer_id) END AS counted_as
FROM customer c;

-- Rung 3: accounts with the same name and postcode are one customer
SELECT c.customer_id,
       MIN(c.customer_id) OVER (
           PARTITION BY UPPER(TRIM(c.name)), c.postal_code) AS counted_as
FROM customer c;
```

## Tenant population

Target: **about 250 tenants**, generated, not hand-written.

- **Archetypes set the shape of the business.** Six to eight kinds of dealer
  (single-yard family dealer, rental-heavy yard, multi-region distributor,
  two-store agriculture dealer, service-only shop, used-equipment trader, and
  so on). An archetype fixes size ranges, the mix of sales, rental and
  service, and data-entry habits.
- **Each tenant draws its own rules.** From its seed, a tenant picks one rung
  per concept and its own code lists. With 17 concepts there are far more
  combinations than tenants, so no two tenants need the same set of queries.
- **Rungs are weighted, not uniform, and not tied to size.** An archetype can
  lean towards a rung (small dealers lean away from rung 1 for status
  fields), but a large tenant is not always on rung 1.
- **Sizes are skewed.** Most tenants are small and a few are large, as in a
  real customer base. The largest tenants need a row cap so the whole
  database stays practical to generate and query; the cap is still to be set.
- **Seen and held-out.** Proposed split: 200 seen, 50 held-out. Held-out
  tenants use code lists no seen tenant uses, and one archetype appears only
  in the held-out set.

## Example tenants

Four illustrative tenants, one from each of four archetypes. The number in
each cell is the rung that tenant uses.

| Concept | A. Single-yard family dealer | B. Rental-heavy yard, 3 branches | C. Multi-region distributor, 25 locations | D. Two-store agriculture dealer |
| --- | --- | --- | --- | --- |
| Product line | 1 | 2 | 3 | 1 |
| Rental fleet unit | 2 | 1 | 3 | 3 |
| Available to sell | 3 | 2 | 2 | 1 |
| Warranty work | 3 | 1 | 2 | 2 |
| Internal work | 2 | 3 | 1 | 3 |
| Active customer | 3 | 2 | 1 | 2 |
| Used unit | 2 | 3 | 1 | 3 |
| Booked sale | 3 | 1 | 2 | 2 |
| Service department | 2 | 1 | 3 | 1 |
| Sales region | 3 | 1 | 2 | 2 |
| Type of work | 3 | 2 | 1 | 2 |
| Completed work order | 3 | 1 | 2 | 2 |
| Past-due invoice | 3 | 2 | 1 | 2 |
| Unit cost | 1 | 3 | 2 | 1 |
| Sale date | 1 | 3 | 2 | 3 |
| Revenue branch | 1 | 2 | 3 | 1 |
| Customer as a counting unit | 3 | 1 | 2 | 3 |

Tenants also differ in the secondary ways already listed in
[`../README.md`](../README.md): volume, history length, which optional columns
are filled, and how consistent data entry is.

| | A | B | C | D |
| --- | --- | --- | --- | --- |
| Locations | 1 | 3 | 25 | 2 |
| Employees | 8 | 40 | 400 | 25 |
| Units on record | 300 | 1,200 | 10,000 | 800 |
| Notes columns | Heavily used | Rarely used | Rarely used | Heavily used |
| `equipment.meter_reading` | Hours or miles, often blank | Hours, at each rental return | Hours, frequent | Hours, at service only |

## Ground truth per tenant

For each concept: the rung used, the tenant's code lists, the rule as SQL, and
the answer to each question. This sits alongside the per-column record already
described in [`../README.md`](../README.md).
