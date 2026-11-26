"""Python definitions of the 17 shared tables.

Mirrors `datasets/design/schema.sql`; `tests/test_schema.py` fails if the two drift.
"""

from generator.schema.pg import CreatePgTableSql, PgColumn

TABLES: dict[str, CreatePgTableSql] = {
    "tenant": CreatePgTableSql(
        pg_table="tenant",
        primary_key=["tenant_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id", data_type="INTEGER", modifiers="PRIMARY KEY", llm_description=""
            ),
            PgColumn(
                name="tenant_code",
                data_type="TEXT",
                modifiers="NOT NULL",
                llm_description="short identifier for the business",
            ),
            PgColumn(
                name="name",
                data_type="TEXT",
                modifiers="NOT NULL",
                llm_description="trading name of the dealer",
            ),
            PgColumn(
                name="as_of_date",
                data_type="DATE",
                modifiers="NOT NULL",
                llm_description='date this tenant\'s data was extracted; "today" for its questions',
            ),
        ],
    ),
    "location": CreatePgTableSql(
        pg_table="location",
        primary_key=["location_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="location_id", data_type="INTEGER", modifiers="PRIMARY KEY", llm_description=""
            ),
            PgColumn(
                name="location_code",
                data_type="TEXT",
                modifiers="NOT NULL",
                llm_description="short branch code, e.g. 'B07'",
            ),
            PgColumn(
                name="name",
                data_type="TEXT",
                modifiers="NOT NULL",
                llm_description="branch or yard name",
            ),
            PgColumn(
                name="location_type",
                data_type="TEXT",
                modifiers="",
                llm_description="sales_yard, rental_branch, service_shop, parts_depot, head_office",
            ),
            PgColumn(
                name="region",
                data_type="TEXT",
                modifiers="",
                llm_description="sales region the location reports to",
            ),
            PgColumn(
                name="parent_location_id",
                data_type="INTEGER",
                modifiers="REFERENCES location (location_id)",
                llm_description="owning branch for satellite yards",
            ),
            PgColumn(name="city", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(name="state", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(name="is_active", data_type="BOOLEAN", modifiers="", llm_description=""),
        ],
    ),
    "department": CreatePgTableSql(
        pg_table="department",
        primary_key=["department_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="department_id",
                data_type="INTEGER",
                modifiers="PRIMARY KEY",
                llm_description="",
            ),
            PgColumn(
                name="department_code",
                data_type="TEXT",
                modifiers="NOT NULL",
                llm_description="e.g. 'SALES', 'RENT', 'SVC', 'PARTS', 'AG'",
            ),
            PgColumn(name="name", data_type="TEXT", modifiers="NOT NULL", llm_description=""),
            PgColumn(
                name="department_type",
                data_type="TEXT",
                modifiers="",
                llm_description="sales, service, parts, rental, admin",
            ),
        ],
    ),
    "employee": CreatePgTableSql(
        pg_table="employee",
        primary_key=["employee_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="employee_id", data_type="INTEGER", modifiers="PRIMARY KEY", llm_description=""
            ),
            PgColumn(
                name="employee_number", data_type="TEXT", modifiers="NOT NULL", llm_description=""
            ),
            PgColumn(name="full_name", data_type="TEXT", modifiers="NOT NULL", llm_description=""),
            PgColumn(
                name="job_title",
                data_type="TEXT",
                modifiers="",
                llm_description="salesperson, technician, parts counter, etc.",
            ),
            PgColumn(
                name="department_id",
                data_type="INTEGER",
                modifiers="REFERENCES department (department_id)",
                llm_description="",
            ),
            PgColumn(
                name="location_id",
                data_type="INTEGER",
                modifiers="REFERENCES location (location_id)",
                llm_description="home location",
            ),
            PgColumn(name="hire_date", data_type="DATE", modifiers="", llm_description=""),
            PgColumn(
                name="termination_date",
                data_type="DATE",
                modifiers="",
                llm_description="null while employed",
            ),
        ],
    ),
    "customer": CreatePgTableSql(
        pg_table="customer",
        primary_key=["customer_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="customer_id", data_type="INTEGER", modifiers="PRIMARY KEY", llm_description=""
            ),
            PgColumn(
                name="account_number", data_type="TEXT", modifiers="NOT NULL", llm_description=""
            ),
            PgColumn(name="name", data_type="TEXT", modifiers="NOT NULL", llm_description=""),
            PgColumn(name="address_line", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(name="city", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(name="state", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(name="postal_code", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(
                name="customer_type",
                data_type="TEXT",
                modifiers="",
                llm_description="contractor, farm, government, manufacturer, individual",
            ),
            PgColumn(
                name="account_class",
                data_type="TEXT",
                modifiers="",
                llm_description="dealer-defined class code used for pricing and reporting",
            ),
            PgColumn(
                name="status",
                data_type="TEXT",
                modifiers="",
                llm_description="active, inactive, on_hold",
            ),
            PgColumn(
                name="parent_customer_id",
                data_type="INTEGER",
                modifiers="REFERENCES customer (customer_id)",
                llm_description="parent account for multi-site customers",
            ),
            PgColumn(
                name="home_location_id",
                data_type="INTEGER",
                modifiers="REFERENCES location (location_id)",
                llm_description="branch that owns the relationship",
            ),
            PgColumn(
                name="salesperson_id",
                data_type="INTEGER",
                modifiers="REFERENCES employee (employee_id)",
                llm_description="assigned salesperson",
            ),
            PgColumn(
                name="credit_limit", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
            PgColumn(
                name="payment_terms",
                data_type="TEXT",
                modifiers="",
                llm_description="e.g. NET10, NET30, NET60",
            ),
            PgColumn(name="created_date", data_type="DATE", modifiers="", llm_description=""),
            PgColumn(name="notes", data_type="TEXT", modifiers="", llm_description=""),
        ],
    ),
    "equipment_model": CreatePgTableSql(
        pg_table="equipment_model",
        primary_key=["model_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="model_id", data_type="INTEGER", modifiers="PRIMARY KEY", llm_description=""
            ),
            PgColumn(
                name="make", data_type="TEXT", modifiers="NOT NULL", llm_description="manufacturer"
            ),
            PgColumn(
                name="model_number", data_type="TEXT", modifiers="NOT NULL", llm_description=""
            ),
            PgColumn(name="description", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(
                name="category",
                data_type="TEXT",
                modifiers="",
                llm_description="product line: construction, agriculture, compact",
            ),
            PgColumn(
                name="class_code",
                data_type="TEXT",
                modifiers="",
                llm_description="machine class code, e.g. 'EXC', 'CTL', 'TRC'",
            ),
            PgColumn(
                name="list_price", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
        ],
    ),
    "equipment": CreatePgTableSql(
        pg_table="equipment",
        primary_key=["equipment_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="equipment_id",
                data_type="INTEGER",
                modifiers="PRIMARY KEY",
                llm_description="",
            ),
            PgColumn(
                name="stock_number",
                data_type="TEXT",
                modifiers="",
                llm_description="dealer's stock number for the unit",
            ),
            PgColumn(name="serial_number", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(
                name="model_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES equipment_model (model_id)",
                llm_description="",
            ),
            PgColumn(name="model_year", data_type="INTEGER", modifiers="", llm_description=""),
            PgColumn(name="condition", data_type="TEXT", modifiers="", llm_description="new, used"),
            PgColumn(
                name="status",
                data_type="TEXT",
                modifiers="",
                llm_description="inventory state: available, sold, on_rent, in_service, in_transit",
            ),
            PgColumn(
                name="hold_code",
                data_type="TEXT",
                modifiers="",
                llm_description="reason the unit is held back from sale, null if none",
            ),
            PgColumn(
                name="ownership_type",
                data_type="TEXT",
                modifiers="",
                llm_description="inventory, rental, customer",
            ),
            PgColumn(
                name="owner_customer_id",
                data_type="INTEGER",
                modifiers="REFERENCES customer (customer_id)",
                llm_description="owning customer; null if dealer-owned",
            ),
            PgColumn(
                name="location_id",
                data_type="INTEGER",
                modifiers="REFERENCES location (location_id)",
                llm_description="where the unit physically is",
            ),
            PgColumn(
                name="meter_reading",
                data_type="NUMERIC(10, 1)",
                modifiers="",
                llm_description="latest engine hours",
            ),
            PgColumn(
                name="acquired_date",
                data_type="DATE",
                modifiers="",
                llm_description="date the dealer took the unit into stock",
            ),
            PgColumn(
                name="acquisition_cost",
                data_type="NUMERIC(12, 2)",
                modifiers="",
                llm_description="",
            ),
            PgColumn(name="notes", data_type="TEXT", modifiers="", llm_description=""),
        ],
    ),
    "part": CreatePgTableSql(
        pg_table="part",
        primary_key=["part_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="part_id", data_type="INTEGER", modifiers="PRIMARY KEY", llm_description=""
            ),
            PgColumn(
                name="part_number", data_type="TEXT", modifiers="NOT NULL", llm_description=""
            ),
            PgColumn(name="description", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(name="manufacturer", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(
                name="part_class",
                data_type="TEXT",
                modifiers="",
                llm_description="dealer-defined parts class code",
            ),
            PgColumn(
                name="unit_cost", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
            PgColumn(
                name="list_price", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
        ],
    ),
    "part_inventory": CreatePgTableSql(
        pg_table="part_inventory",
        primary_key=["part_id", "location_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="part_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES part (part_id)",
                llm_description="",
            ),
            PgColumn(
                name="location_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES location (location_id)",
                llm_description="",
            ),
            PgColumn(
                name="bin", data_type="TEXT", modifiers="", llm_description="shelf or bin location"
            ),
            PgColumn(
                name="qty_on_hand", data_type="NUMERIC(10, 2)", modifiers="", llm_description=""
            ),
            PgColumn(
                name="qty_reserved",
                data_type="NUMERIC(10, 2)",
                modifiers="",
                llm_description="allocated to open orders and work orders",
            ),
            PgColumn(
                name="reorder_point", data_type="NUMERIC(10, 2)", modifiers="", llm_description=""
            ),
        ],
    ),
    "sales_order": CreatePgTableSql(
        pg_table="sales_order",
        primary_key=["sales_order_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="sales_order_id",
                data_type="INTEGER",
                modifiers="PRIMARY KEY",
                llm_description="",
            ),
            PgColumn(
                name="order_number", data_type="TEXT", modifiers="NOT NULL", llm_description=""
            ),
            PgColumn(
                name="customer_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES customer (customer_id)",
                llm_description="",
            ),
            PgColumn(
                name="salesperson_id",
                data_type="INTEGER",
                modifiers="REFERENCES employee (employee_id)",
                llm_description="",
            ),
            PgColumn(
                name="location_id",
                data_type="INTEGER",
                modifiers="REFERENCES location (location_id)",
                llm_description="selling location",
            ),
            PgColumn(
                name="department_id",
                data_type="INTEGER",
                modifiers="REFERENCES department (department_id)",
                llm_description="selling department",
            ),
            PgColumn(
                name="order_type",
                data_type="TEXT",
                modifiers="",
                llm_description="equipment, parts, quote",
            ),
            PgColumn(
                name="status",
                data_type="TEXT",
                modifiers="",
                llm_description="open, invoiced, delivered, closed, cancelled",
            ),
            PgColumn(name="order_date", data_type="DATE", modifiers="", llm_description=""),
            PgColumn(
                name="total_amount", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
            PgColumn(name="notes", data_type="TEXT", modifiers="", llm_description=""),
        ],
    ),
    "sales_order_line": CreatePgTableSql(
        pg_table="sales_order_line",
        primary_key=["sales_order_line_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="sales_order_line_id",
                data_type="INTEGER",
                modifiers="PRIMARY KEY",
                llm_description="",
            ),
            PgColumn(
                name="sales_order_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES sales_order (sales_order_id)",
                llm_description="",
            ),
            PgColumn(
                name="line_type",
                data_type="TEXT",
                modifiers="",
                llm_description="equipment, part, attachment, fee, trade_in",
            ),
            PgColumn(
                name="equipment_id",
                data_type="INTEGER",
                modifiers="REFERENCES equipment (equipment_id)",
                llm_description="unit sold or traded in",
            ),
            PgColumn(
                name="part_id",
                data_type="INTEGER",
                modifiers="REFERENCES part (part_id)",
                llm_description="",
            ),
            PgColumn(name="description", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(name="quantity", data_type="NUMERIC(10, 2)", modifiers="", llm_description=""),
            PgColumn(
                name="unit_price", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
            PgColumn(
                name="line_amount",
                data_type="NUMERIC(12, 2)",
                modifiers="",
                llm_description="negative for trade-in allowances",
            ),
        ],
    ),
    "rental_contract": CreatePgTableSql(
        pg_table="rental_contract",
        primary_key=["rental_contract_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="rental_contract_id",
                data_type="INTEGER",
                modifiers="PRIMARY KEY",
                llm_description="",
            ),
            PgColumn(
                name="contract_number", data_type="TEXT", modifiers="NOT NULL", llm_description=""
            ),
            PgColumn(
                name="customer_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES customer (customer_id)",
                llm_description="",
            ),
            PgColumn(
                name="equipment_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES equipment (equipment_id)",
                llm_description="",
            ),
            PgColumn(
                name="location_id",
                data_type="INTEGER",
                modifiers="REFERENCES location (location_id)",
                llm_description="renting branch",
            ),
            PgColumn(
                name="salesperson_id",
                data_type="INTEGER",
                modifiers="REFERENCES employee (employee_id)",
                llm_description="",
            ),
            PgColumn(
                name="contract_type",
                data_type="TEXT",
                modifiers="",
                llm_description="rental, rent_to_own, demo, loaner",
            ),
            PgColumn(
                name="status",
                data_type="TEXT",
                modifiers="",
                llm_description="open, returned, closed, cancelled",
            ),
            PgColumn(name="start_date", data_type="DATE", modifiers="", llm_description=""),
            PgColumn(
                name="end_date",
                data_type="DATE",
                modifiers="",
                llm_description="date the rental ended",
            ),
            PgColumn(
                name="rate_period",
                data_type="TEXT",
                modifiers="",
                llm_description="day, week, month",
            ),
            PgColumn(
                name="rate_amount",
                data_type="NUMERIC(12, 2)",
                modifiers="",
                llm_description="price per rate period",
            ),
            PgColumn(name="notes", data_type="TEXT", modifiers="", llm_description=""),
        ],
    ),
    "work_order": CreatePgTableSql(
        pg_table="work_order",
        primary_key=["work_order_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="work_order_id",
                data_type="INTEGER",
                modifiers="PRIMARY KEY",
                llm_description="",
            ),
            PgColumn(
                name="work_order_number", data_type="TEXT", modifiers="NOT NULL", llm_description=""
            ),
            PgColumn(
                name="customer_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES customer (customer_id)",
                llm_description="customer billed for the work",
            ),
            PgColumn(
                name="equipment_id",
                data_type="INTEGER",
                modifiers="REFERENCES equipment (equipment_id)",
                llm_description="unit worked on",
            ),
            PgColumn(
                name="location_id",
                data_type="INTEGER",
                modifiers="REFERENCES location (location_id)",
                llm_description="shop doing the work",
            ),
            PgColumn(
                name="department_id",
                data_type="INTEGER",
                modifiers="REFERENCES department (department_id)",
                llm_description="service department doing the work",
            ),
            PgColumn(
                name="technician_id",
                data_type="INTEGER",
                modifiers="REFERENCES employee (employee_id)",
                llm_description="lead technician assigned",
            ),
            PgColumn(
                name="work_order_type",
                data_type="TEXT",
                modifiers="",
                llm_description="billing type: customer, warranty, internal, contract",
            ),
            PgColumn(
                name="service_type",
                data_type="TEXT",
                modifiers="",
                llm_description="kind of work done: maintenance, repair, inspection, setup, rebuild",
            ),
            PgColumn(
                name="status",
                data_type="TEXT",
                modifiers="",
                llm_description="open, waiting_parts, complete, invoiced, cancelled",
            ),
            PgColumn(
                name="is_internal",
                data_type="BOOLEAN",
                modifiers="",
                llm_description="true when the dealer bears the cost",
            ),
            PgColumn(name="opened_date", data_type="DATE", modifiers="", llm_description=""),
            PgColumn(name="closed_date", data_type="DATE", modifiers="", llm_description=""),
            PgColumn(
                name="meter_reading",
                data_type="NUMERIC(10, 1)",
                modifiers="",
                llm_description="engine hours when the unit came in",
            ),
            PgColumn(name="notes", data_type="TEXT", modifiers="", llm_description=""),
        ],
    ),
    "work_order_line": CreatePgTableSql(
        pg_table="work_order_line",
        primary_key=["work_order_line_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="work_order_line_id",
                data_type="INTEGER",
                modifiers="PRIMARY KEY",
                llm_description="",
            ),
            PgColumn(
                name="work_order_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES work_order (work_order_id)",
                llm_description="",
            ),
            PgColumn(
                name="line_type",
                data_type="TEXT",
                modifiers="",
                llm_description="labor, part, misc",
            ),
            PgColumn(
                name="operation_code",
                data_type="TEXT",
                modifiers="",
                llm_description="labour operation code",
            ),
            PgColumn(
                name="technician_id",
                data_type="INTEGER",
                modifiers="REFERENCES employee (employee_id)",
                llm_description="",
            ),
            PgColumn(
                name="part_id",
                data_type="INTEGER",
                modifiers="REFERENCES part (part_id)",
                llm_description="",
            ),
            PgColumn(name="description", data_type="TEXT", modifiers="", llm_description=""),
            PgColumn(
                name="labor_hours",
                data_type="NUMERIC(8, 2)",
                modifiers="",
                llm_description="hours worked, labour lines only",
            ),
            PgColumn(
                name="quantity",
                data_type="NUMERIC(10, 2)",
                modifiers="",
                llm_description="parts quantity, part lines only",
            ),
            PgColumn(
                name="unit_price", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
            PgColumn(
                name="unit_cost", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
            PgColumn(
                name="line_amount", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
        ],
    ),
    "warranty_claim": CreatePgTableSql(
        pg_table="warranty_claim",
        primary_key=["warranty_claim_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="warranty_claim_id",
                data_type="INTEGER",
                modifiers="PRIMARY KEY",
                llm_description="",
            ),
            PgColumn(
                name="claim_number", data_type="TEXT", modifiers="NOT NULL", llm_description=""
            ),
            PgColumn(
                name="work_order_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES work_order (work_order_id)",
                llm_description="",
            ),
            PgColumn(
                name="equipment_id",
                data_type="INTEGER",
                modifiers="REFERENCES equipment (equipment_id)",
                llm_description="",
            ),
            PgColumn(
                name="manufacturer",
                data_type="TEXT",
                modifiers="",
                llm_description="manufacturer the claim was filed with",
            ),
            PgColumn(
                name="status",
                data_type="TEXT",
                modifiers="",
                llm_description="submitted, approved, rejected, paid",
            ),
            PgColumn(name="submitted_date", data_type="DATE", modifiers="", llm_description=""),
            PgColumn(name="paid_date", data_type="DATE", modifiers="", llm_description=""),
            PgColumn(
                name="claimed_amount", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
            PgColumn(
                name="approved_amount", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
        ],
    ),
    "invoice": CreatePgTableSql(
        pg_table="invoice",
        primary_key=["invoice_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="invoice_id", data_type="INTEGER", modifiers="PRIMARY KEY", llm_description=""
            ),
            PgColumn(
                name="invoice_number", data_type="TEXT", modifiers="NOT NULL", llm_description=""
            ),
            PgColumn(
                name="customer_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES customer (customer_id)",
                llm_description="",
            ),
            PgColumn(
                name="location_id",
                data_type="INTEGER",
                modifiers="REFERENCES location (location_id)",
                llm_description="",
            ),
            PgColumn(
                name="department_id",
                data_type="INTEGER",
                modifiers="REFERENCES department (department_id)",
                llm_description="",
            ),
            PgColumn(
                name="invoice_type",
                data_type="TEXT",
                modifiers="",
                llm_description="equipment, parts, service, rental",
            ),
            PgColumn(
                name="sales_order_id",
                data_type="INTEGER",
                modifiers="REFERENCES sales_order (sales_order_id)",
                llm_description="source order, if any",
            ),
            PgColumn(
                name="work_order_id",
                data_type="INTEGER",
                modifiers="REFERENCES work_order (work_order_id)",
                llm_description="source work order, if any",
            ),
            PgColumn(
                name="rental_contract_id",
                data_type="INTEGER",
                modifiers="REFERENCES rental_contract (rental_contract_id)",
                llm_description="source rental, if any",
            ),
            PgColumn(
                name="status", data_type="TEXT", modifiers="", llm_description="open, paid, void"
            ),
            PgColumn(name="invoice_date", data_type="DATE", modifiers="", llm_description=""),
            PgColumn(name="due_date", data_type="DATE", modifiers="", llm_description=""),
            PgColumn(name="subtotal", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""),
            PgColumn(
                name="tax_amount", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
            PgColumn(
                name="total_amount", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""
            ),
        ],
    ),
    "payment": CreatePgTableSql(
        pg_table="payment",
        primary_key=["payment_id"],
        pg_columns=[
            PgColumn(
                name="tenant_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES tenant (tenant_id)",
                llm_description="business this row belongs to",
            ),
            PgColumn(
                name="payment_id", data_type="INTEGER", modifiers="PRIMARY KEY", llm_description=""
            ),
            PgColumn(
                name="customer_id",
                data_type="INTEGER",
                modifiers="NOT NULL REFERENCES customer (customer_id)",
                llm_description="",
            ),
            PgColumn(
                name="invoice_id",
                data_type="INTEGER",
                modifiers="REFERENCES invoice (invoice_id)",
                llm_description="invoice the payment was applied to",
            ),
            PgColumn(name="payment_date", data_type="DATE", modifiers="", llm_description=""),
            PgColumn(name="amount", data_type="NUMERIC(12, 2)", modifiers="", llm_description=""),
            PgColumn(
                name="method",
                data_type="TEXT",
                modifiers="",
                llm_description="check, ach, card, cash",
            ),
            PgColumn(
                name="reference",
                data_type="TEXT",
                modifiers="",
                llm_description="check number or bank reference",
            ),
        ],
    ),
}
