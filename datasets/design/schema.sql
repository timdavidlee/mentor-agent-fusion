-- Shared schema (draft, proposed): machinery sales + services dealer.
-- Identical for every tenant. The comment on each column is its NOMINAL
-- meaning: what the column is officially for, not what a tenant stores there.
-- See concepts.md for how tenants diverge.
--
-- One database holds every tenant (about 250). Every table carries tenant_id.
-- Surrogate ids are unique across all tenants, so a join on an id never
-- crosses tenants. Codes and numbers (location_code, account_number, ...) are
-- only unique within a tenant.

CREATE TABLE tenant (
    tenant_id   INTEGER PRIMARY KEY,
    tenant_code TEXT NOT NULL,                 -- short identifier for the business
    name        TEXT NOT NULL,                 -- trading name of the dealer
    as_of_date  DATE NOT NULL                  -- date this tenant's data was extracted; "today" for its questions
);

CREATE TABLE location (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    location_id        INTEGER PRIMARY KEY,
    location_code      TEXT NOT NULL,          -- short branch code, e.g. 'B07'
    name               TEXT NOT NULL,          -- branch or yard name
    location_type      TEXT,                   -- sales_yard, rental_branch, service_shop, parts_depot, head_office
    region             TEXT,                   -- sales region the location reports to
    parent_location_id INTEGER REFERENCES location (location_id), -- owning branch for satellite yards
    city               TEXT,
    state              TEXT,
    is_active          BOOLEAN
);

CREATE TABLE department (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    department_id   INTEGER PRIMARY KEY,
    department_code TEXT NOT NULL,             -- e.g. 'SALES', 'RENT', 'SVC', 'PARTS', 'AG'
    name            TEXT NOT NULL,
    department_type TEXT                       -- sales, service, parts, rental, admin
);

CREATE TABLE employee (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    employee_id      INTEGER PRIMARY KEY,
    employee_number  TEXT NOT NULL,
    full_name        TEXT NOT NULL,
    job_title        TEXT,                     -- salesperson, technician, parts counter, etc.
    department_id    INTEGER REFERENCES department (department_id),
    location_id      INTEGER REFERENCES location (location_id), -- home location
    hire_date        DATE,
    termination_date DATE                      -- null while employed
);

CREATE TABLE customer (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    customer_id        INTEGER PRIMARY KEY,
    account_number     TEXT NOT NULL,
    name               TEXT NOT NULL,
    address_line       TEXT,
    city               TEXT,
    state              TEXT,
    postal_code        TEXT,
    customer_type      TEXT,                   -- contractor, farm, government, manufacturer, individual
    account_class      TEXT,                   -- dealer-defined class code used for pricing and reporting
    status             TEXT,                   -- active, inactive, on_hold
    parent_customer_id INTEGER REFERENCES customer (customer_id), -- parent account for multi-site customers
    home_location_id   INTEGER REFERENCES location (location_id), -- branch that owns the relationship
    salesperson_id     INTEGER REFERENCES employee (employee_id), -- assigned salesperson
    credit_limit       NUMERIC(12, 2),
    payment_terms      TEXT,                   -- e.g. NET10, NET30, NET60
    created_date       DATE,
    notes              TEXT
);

CREATE TABLE equipment_model (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    model_id     INTEGER PRIMARY KEY,
    make         TEXT NOT NULL,                -- manufacturer
    model_number TEXT NOT NULL,
    description  TEXT,
    category     TEXT,                         -- product line: construction, agriculture, compact
    class_code   TEXT,                         -- machine class code, e.g. 'EXC', 'CTL', 'TRC'
    list_price   NUMERIC(12, 2)
);

CREATE TABLE equipment (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    equipment_id      INTEGER PRIMARY KEY,
    stock_number      TEXT,                    -- dealer's stock number for the unit
    serial_number     TEXT,
    model_id          INTEGER NOT NULL REFERENCES equipment_model (model_id),
    model_year        INTEGER,
    condition         TEXT,                    -- new, used
    status            TEXT,                    -- inventory state: available, sold, on_rent, in_service, in_transit
    hold_code         TEXT,                    -- reason the unit is held back from sale, null if none
    ownership_type    TEXT,                    -- inventory, rental, customer
    owner_customer_id INTEGER REFERENCES customer (customer_id), -- owning customer; null if dealer-owned
    location_id       INTEGER REFERENCES location (location_id), -- where the unit physically is
    meter_reading     NUMERIC(10, 1),          -- latest engine hours
    acquired_date     DATE,                    -- date the dealer took the unit into stock
    acquisition_cost  NUMERIC(12, 2),
    notes             TEXT
);

CREATE TABLE part (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    part_id      INTEGER PRIMARY KEY,
    part_number  TEXT NOT NULL,
    description  TEXT,
    manufacturer TEXT,
    part_class   TEXT,                         -- dealer-defined parts class code
    unit_cost    NUMERIC(12, 2),
    list_price   NUMERIC(12, 2)
);

CREATE TABLE part_inventory (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    part_id       INTEGER NOT NULL REFERENCES part (part_id),
    location_id   INTEGER NOT NULL REFERENCES location (location_id),
    bin           TEXT,                        -- shelf or bin location
    qty_on_hand   NUMERIC(10, 2),
    qty_reserved  NUMERIC(10, 2),              -- allocated to open orders and work orders
    reorder_point NUMERIC(10, 2),
    PRIMARY KEY (part_id, location_id)
);

CREATE TABLE sales_order (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    sales_order_id INTEGER PRIMARY KEY,
    order_number   TEXT NOT NULL,
    customer_id    INTEGER NOT NULL REFERENCES customer (customer_id),
    salesperson_id INTEGER REFERENCES employee (employee_id),
    location_id    INTEGER REFERENCES location (location_id),     -- selling location
    department_id  INTEGER REFERENCES department (department_id), -- selling department
    order_type     TEXT,                       -- equipment, parts, quote
    status         TEXT,                       -- open, invoiced, delivered, closed, cancelled
    order_date     DATE,
    total_amount   NUMERIC(12, 2),
    notes          TEXT
);

CREATE TABLE sales_order_line (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    sales_order_line_id INTEGER PRIMARY KEY,
    sales_order_id      INTEGER NOT NULL REFERENCES sales_order (sales_order_id),
    line_type           TEXT,                  -- equipment, part, attachment, fee, trade_in
    equipment_id        INTEGER REFERENCES equipment (equipment_id), -- unit sold or traded in
    part_id             INTEGER REFERENCES part (part_id),
    description         TEXT,
    quantity            NUMERIC(10, 2),
    unit_price          NUMERIC(12, 2),
    line_amount         NUMERIC(12, 2)         -- negative for trade-in allowances
);

CREATE TABLE rental_contract (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    rental_contract_id INTEGER PRIMARY KEY,
    contract_number    TEXT NOT NULL,
    customer_id        INTEGER NOT NULL REFERENCES customer (customer_id),
    equipment_id       INTEGER NOT NULL REFERENCES equipment (equipment_id),
    location_id        INTEGER REFERENCES location (location_id), -- renting branch
    salesperson_id     INTEGER REFERENCES employee (employee_id),
    contract_type      TEXT,                   -- rental, rent_to_own, demo, loaner
    status             TEXT,                   -- open, returned, closed, cancelled
    start_date         DATE,
    end_date           DATE,                   -- date the rental ended
    rate_period        TEXT,                   -- day, week, month
    rate_amount        NUMERIC(12, 2),         -- price per rate period
    notes              TEXT
);

CREATE TABLE work_order (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    work_order_id     INTEGER PRIMARY KEY,
    work_order_number TEXT NOT NULL,
    customer_id       INTEGER NOT NULL REFERENCES customer (customer_id), -- customer billed for the work
    equipment_id      INTEGER REFERENCES equipment (equipment_id),        -- unit worked on
    location_id       INTEGER REFERENCES location (location_id),          -- shop doing the work
    department_id     INTEGER REFERENCES department (department_id),      -- service department doing the work
    technician_id     INTEGER REFERENCES employee (employee_id),          -- lead technician assigned
    work_order_type   TEXT,                    -- billing type: customer, warranty, internal, contract
    service_type      TEXT,                    -- kind of work done: maintenance, repair, inspection, setup, rebuild
    status            TEXT,                    -- open, waiting_parts, complete, invoiced, cancelled
    is_internal       BOOLEAN,                 -- true when the dealer bears the cost
    opened_date       DATE,
    closed_date       DATE,
    meter_reading     NUMERIC(10, 1),          -- engine hours when the unit came in
    notes             TEXT
);

CREATE TABLE work_order_line (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    work_order_line_id INTEGER PRIMARY KEY,
    work_order_id      INTEGER NOT NULL REFERENCES work_order (work_order_id),
    line_type          TEXT,                   -- labor, part, misc
    operation_code     TEXT,                   -- labour operation code
    technician_id      INTEGER REFERENCES employee (employee_id),
    part_id            INTEGER REFERENCES part (part_id),
    description        TEXT,
    labor_hours        NUMERIC(8, 2),          -- hours worked, labour lines only
    quantity           NUMERIC(10, 2),         -- parts quantity, part lines only
    unit_price         NUMERIC(12, 2),
    unit_cost          NUMERIC(12, 2),
    line_amount        NUMERIC(12, 2)
);

CREATE TABLE warranty_claim (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    warranty_claim_id INTEGER PRIMARY KEY,
    claim_number      TEXT NOT NULL,
    work_order_id     INTEGER NOT NULL REFERENCES work_order (work_order_id),
    equipment_id      INTEGER REFERENCES equipment (equipment_id),
    manufacturer      TEXT,                    -- manufacturer the claim was filed with
    status            TEXT,                    -- submitted, approved, rejected, paid
    submitted_date    DATE,
    paid_date         DATE,
    claimed_amount    NUMERIC(12, 2),
    approved_amount   NUMERIC(12, 2)
);

CREATE TABLE invoice (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    invoice_id         INTEGER PRIMARY KEY,
    invoice_number     TEXT NOT NULL,
    customer_id        INTEGER NOT NULL REFERENCES customer (customer_id),
    location_id        INTEGER REFERENCES location (location_id),
    department_id      INTEGER REFERENCES department (department_id),
    invoice_type       TEXT,                   -- equipment, parts, service, rental
    sales_order_id     INTEGER REFERENCES sales_order (sales_order_id),         -- source order, if any
    work_order_id      INTEGER REFERENCES work_order (work_order_id),           -- source work order, if any
    rental_contract_id INTEGER REFERENCES rental_contract (rental_contract_id), -- source rental, if any
    status             TEXT,                   -- open, paid, void
    invoice_date       DATE,
    due_date           DATE,
    subtotal           NUMERIC(12, 2),
    tax_amount         NUMERIC(12, 2),
    total_amount       NUMERIC(12, 2)
);

CREATE TABLE payment (
    tenant_id          INTEGER NOT NULL REFERENCES tenant (tenant_id), -- business this row belongs to
    payment_id   INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customer (customer_id),
    invoice_id   INTEGER REFERENCES invoice (invoice_id), -- invoice the payment was applied to
    payment_date DATE,
    amount       NUMERIC(12, 2),
    method       TEXT,                         -- check, ach, card, cash
    reference    TEXT                          -- check number or bank reference
);
