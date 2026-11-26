"""Simulate one dealer: stock, rentals, sales, service, invoices and payments.

The simulation sets structural facts (who owns a unit, where it stands, which invoice
links to which order) and records hidden truth. Concept encoders (`render.py`) then
write the nominal and code columns each concept owns.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from generator.population import TenantSpec
from generator.simulate.exceptions import allowed
from generator.simulate.world import Row, World, money, qty

LINES = ("construction", "agriculture", "compact")

MAKES: dict[str, list[str]] = {
    "construction": ["Halvorsen", "Dunmore"],
    "agriculture": ["Prairieline", "Halvorsen"],
    "compact": ["Kestrel", "Dunmore"],
}
CLASSES: dict[str, list[tuple[str, str, int]]] = {
    # class code, description, typical list price
    "construction": [
        ("EXC", "crawler excavator", 310_000),
        ("DOZ", "crawler dozer", 280_000),
        ("WHL", "wheel loader", 240_000),
        ("BHL", "backhoe loader", 130_000),
    ],
    "agriculture": [
        ("TRC", "row-crop tractor", 260_000),
        ("CMB", "combine", 520_000),
        ("BAL", "round baler", 60_000),
    ],
    "compact": [
        ("CTL", "compact track loader", 75_000),
        ("MEX", "mini excavator", 65_000),
        ("SSL", "skid steer loader", 55_000),
    ],
}

FIRST = ["Ann", "Bill", "Carla", "Dev", "Eli", "Fay", "Gus", "Hana", "Ivan", "Jo", "Kai", "Lena"]
LAST = ["Olsen", "Price", "Reyes", "Stone", "Tran", "Vance", "Walsh", "Young", "Zeller", "Moss"]
BUSINESS = ["Ridge", "Valley", "Summit", "Prairie", "River", "Oak", "Iron", "Blue", "Twin", "Cedar"]
SUFFIX = {
    "contractor": ["Excavating", "Construction", "Grading", "Site Works", "Paving"],
    "farm": ["Farms", "Acres", "Grain Co", "Cattle Co"],
    "government": ["County Highway Dept", "Township Roads", "Parks District"],
}

TAX_RATE = {11: Decimal("0.07"), 13: Decimal("0.0625")}


def simulate(spec: TenantSpec) -> World:
    w = World(spec=spec, rng=random.Random(spec.seed))
    sim = _Sim(w)
    sim.run()
    return w


class _Sim:
    def __init__(self, w: World) -> None:
        self.w = w
        self.spec: TenantSpec = w.spec
        self.rng = w.rng
        self.loc_by_code: dict[str, Row] = {}
        self.dept_by_code: dict[str, Row] = {}
        self.staff: dict[str, list[int]] = {}  # department_type -> employee ids
        self.staff_by_dept: dict[str, list[int]] = {}
        self.trading_customers: list[int] = []
        self.house: dict[str, int] = {}  # purpose -> customer id
        self.manufacturer: dict[str, int] = {}  # make -> customer id
        self.models: dict[str, list[Row]] = {line: [] for line in LINES}
        self.parts: list[Row] = []
        self.tax = TAX_RATE.get(self.spec.tenant_id, Decimal("0.07"))
        self.unit_target = spec_units_target(self.spec)
        self.stock_rows = 0
        self.order_lines: dict[int, list[Row]] = {}

    # ------------------------------------------------------------------ setup
    def run(self) -> None:
        w = self.w
        w.add(
            "tenant",
            tenant_id=self.spec.tenant_id,
            tenant_code=self.spec.tenant_code,
            name=self.spec.name,
            as_of_date=self.spec.as_of_date,
        )
        self._locations()
        self._departments()
        self._employees()
        self._models()
        self._customers()
        self._parts()
        self._units()
        self._parts_orders()

    def _locations(self) -> None:
        for spec in self.spec.locations:
            row = self.w.add(
                "location",
                location_code=spec.code,
                name=spec.name,
                location_type=spec.location_type,
                region=spec.region,
                city=spec.city,
                state=spec.state,
                is_active=True,
            )
            self.loc_by_code[spec.code] = row
        for spec in self.spec.locations:
            if spec.parent_code:
                parent = self.loc_by_code[spec.parent_code]
                self.loc_by_code[spec.code]["parent_location_id"] = parent["location_id"]

    def _departments(self) -> None:
        for spec in self.spec.departments:
            row = self.w.add(
                "department",
                department_code=spec.code,
                name=spec.name,
                department_type=spec.department_type,
            )
            self.dept_by_code[spec.code] = row

    def _locations_of_type(self, *types: str) -> list[Row]:
        return [r for r in self.w.rows["location"] if r["location_type"] in types]

    def _home_locations(self, dept_code: str) -> list[Row]:
        dspec = next(d for d in self.spec.departments if d.code == dept_code)
        if dspec.department_type == "sales":
            locs = [
                self.loc_by_code[s.code]
                for s in self.spec.locations
                if set(s.stocks_lines) & set(dspec.sells_lines)
            ]
        elif dspec.department_type == "service":
            locs = self._locations_of_type("service_shop", "sales_yard")
        elif dspec.department_type == "rental":
            locs = self._locations_of_type("rental_branch")
        elif dspec.department_type == "parts":
            locs = self._locations_of_type("parts_depot", "sales_yard")
        else:
            locs = self._locations_of_type("head_office")
        return locs or self.w.rows["location"][:1]

    def _employees(self) -> None:
        w = self.w
        titles = {
            "sales": "salesperson",
            "service": "technician",
            "parts": "parts counter",
            "rental": "rental coordinator",
            "admin": "office manager",
        }
        n = 0
        for dspec in self.spec.departments:
            dept = self.dept_by_code[dspec.code]
            homes = self._home_locations(dspec.code)
            for i in range(dspec.headcount):
                n += 1
                row = w.add(
                    "employee",
                    employee_number=f"E{n:04d}",
                    full_name=f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}",
                    job_title=titles[dspec.department_type],
                    department_id=dept["department_id"],
                    location_id=homes[i % len(homes)]["location_id"],
                    hire_date=w.day_between(w.start - timedelta(days=3000), w.start),
                )
                self.staff.setdefault(dspec.department_type, []).append(row["employee_id"])
                self.staff_by_dept.setdefault(dspec.code, []).append(row["employee_id"])

    def _models(self) -> None:
        n_per_class = 2 if self.spec.size.units < 1000 else 3
        for line in LINES:
            for class_code, desc, price in CLASSES[line]:
                for k in range(n_per_class):
                    make = MAKES[line][k % len(MAKES[line])]
                    row = self.w.add(
                        "equipment_model",
                        make=make,
                        model_number=f"{class_code[0]}{self.rng.randint(100, 990)}{'ABCDEFG'[k]}",
                        description=f"{make} {desc}",
                        class_code=class_code,
                        list_price=money(round(price * self.rng.uniform(0.8, 1.25), -2)),
                    )
                    self.w.truth.setdefault("product_line", {})
                    self.w.fact("equipment_model", row["model_id"])["line"] = line
                    self.models[line].append(row)

    def _customers(self) -> None:
        w = self.w
        vocab = self.spec.vocabulary
        house_classes = vocab["customer.house_classes"]
        mfr_class = vocab["customer.manufacturer_class"][0]
        trading = [
            c for c in vocab["customer.account_class"] if c not in house_classes and c != mfr_class
        ]
        yards = self._locations_of_type("sales_yard")
        sales_staff = self.staff.get("sales", [])
        # house accounts: the dealer billing itself
        for i, cls in enumerate(house_classes):
            purpose = ["shop", "fleet"][i] if len(house_classes) > 1 else "all"
            label = {"shop": "Shop Account", "fleet": "Rental Fleet Account", "all": "Internal"}
            row = w.add(
                "customer",
                account_number=f"H{i + 1:03d}",
                name=f"{self.spec.name} {label[purpose]}",
                account_class=cls,
                status="active",
                home_location_id=yards[0]["location_id"] if yards else None,
                payment_terms="NET30",
                created_date=w.start,
            )
            if purpose == "all":
                self.house["shop"] = self.house["fleet"] = row["customer_id"]
            else:
                self.house[purpose] = row["customer_id"]
        makes = sorted({m for ms in MAKES.values() for m in ms})
        for i, make in enumerate(makes):
            row = w.add(
                "customer",
                account_number=f"M{i + 1:03d}",
                name=f"{make} Manufacturing Warranty",
                customer_type="manufacturer",
                account_class=mfr_class,
                status="active",
                payment_terms="NET60",
                created_date=w.start,
            )
            self.manufacturer[make] = row["customer_id"]
        types = ["contractor", "farm", "government", "individual"]
        weights = [0.5, 0.25, 0.05, 0.2]
        for i in range(self.spec.size.customers):
            ctype = self.rng.choices(types, weights)[0]
            if ctype == "individual":
                name = f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"
            else:
                name = f"{self.rng.choice(BUSINESS)} {self.rng.choice(SUFFIX[ctype])}"
            parent = None
            if ctype == "contractor" and self.trading_customers and self.chance(0.08):
                parent = self.rng.choice(self.trading_customers)
            home = self.rng.choice(yards) if yards else None
            row = w.add(
                "customer",
                account_number=f"{10000 + i}",
                name=name,
                address_line=f"{self.rng.randint(10, 9999)} {self.rng.choice(BUSINESS)} Rd",
                city=home["city"] if home else None,
                state=home["state"] if home else None,
                postal_code=f"{self.rng.randint(50000, 62999)}",
                customer_type=ctype,
                account_class=self._class_for(ctype, trading),
                status="active" if self.chance(0.85) else "inactive",
                parent_customer_id=parent,
                home_location_id=home["location_id"] if home else None,
                salesperson_id=self.rng.choice(sales_staff) if sales_staff else None,
                credit_limit=money(self.rng.choice([5000, 25000, 50000, 100000, 250000])),
                payment_terms=self.rng.choice(["NET10", "NET30", "NET30", "NET60"]),
                created_date=w.day_between(w.start - timedelta(days=2000), w.as_of),
            )
            self.trading_customers.append(row["customer_id"])

    def _class_for(self, ctype: str, trading: list[str]) -> str:
        # deterministic mapping by position in the tenant's own vocabulary
        index = {"contractor": 0, "farm": 1, "government": 2, "individual": 3}[ctype]
        if ctype == "contractor" and len(trading) > 3:
            return self.rng.choice(trading[:2])
        return trading[min(index, len(trading) - 1)]

    def _parts(self) -> None:
        w = self.w
        classes = self.spec.vocabulary["part.part_class"]
        makes = sorted({m for ms in MAKES.values() for m in ms})
        for i in range(self.spec.size.parts):
            cost = self.rng.uniform(4, 900)
            row = w.add(
                "part",
                part_number=f"P{self.rng.randint(1000, 9999)}-{i:04d}",
                description=self.rng.choice(
                    ["filter", "seal kit", "hydraulic hose", "bearing", "track roller", "belt"]
                ),
                manufacturer=self.rng.choice(makes),
                part_class=classes[i % len(classes)],
                unit_cost=money(cost),
                list_price=money(cost * self.rng.uniform(1.3, 1.8)),
            )
            self.parts.append(row)
        stocking = self._locations_of_type("parts_depot", "sales_yard", "service_shop")
        for part in self.parts:
            for loc in stocking:
                if len(stocking) > 1 and not self.chance(0.5):
                    continue
                w.add(
                    "part_inventory",
                    part_id=part["part_id"],
                    location_id=loc["location_id"],
                    bin=f"{self.rng.choice('ABCDEF')}{self.rng.randint(1, 40):02d}",
                    qty_on_hand=qty(self.rng.randint(0, 40)),
                    qty_reserved=qty(self.rng.randint(0, 3)),
                    reorder_point=qty(self.rng.randint(2, 10)),
                )

    # ------------------------------------------------------------- helpers
    def pick_line(self) -> str:
        mix = self.spec.mix.line_mix
        return self.rng.choices(list(mix), list(mix.values()))[0]

    def chance(self, p: float) -> bool:
        return self.w.chance(p)

    def employee(self, dept_type: str) -> int | None:
        staff = self.staff.get(dept_type)
        return self.rng.choice(staff) if staff else None

    def selling_point(self, line: str) -> tuple[Row, Row]:
        """Department and location that sell a unit of this line (same for every deal)."""
        depts = [d for d in self.spec.departments if line in d.sells_lines]
        locs = [s for s in self.spec.locations if line in s.stocks_lines]
        dept = self.dept_by_code[self.rng.choice(depts).code]
        loc = self.loc_by_code[self.rng.choice(locs).code]
        return dept, loc

    def stock_yard(self, line: str) -> Row:
        locs = [s for s in self.spec.locations if line in s.stocks_lines]
        return self.loc_by_code[self.rng.choice(locs).code]

    def fleet_location(self) -> Row:
        branches = self._locations_of_type("rental_branch")
        return self.rng.choice(branches) if branches else self.w.rows["location"][0]

    def shop_location(self) -> Row:
        return self.rng.choice(self._locations_of_type("service_shop", "sales_yard"))

    def service_dept(self) -> Row:
        codes = [d.code for d in self.spec.departments if d.department_type == "service"]
        return self.dept_by_code[codes[0]]

    def salesperson_at(self, dept: Row) -> int | None:
        staff = self.staff_by_dept.get(dept["department_code"])
        return self.rng.choice(staff) if staff else self.employee("sales")

    # ------------------------------------------------------------ invoices
    def invoice(
        self,
        *,
        customer_id: int,
        on: date,
        invoice_type: str,
        subtotal: Decimal,
        location_id: int | None,
        department_id: int | None,
        sales_order_id: int | None = None,
        work_order_id: int | None = None,
        rental_contract_id: int | None = None,
        void: bool = False,
    ) -> Row:
        w = self.w
        tax = money(subtotal * self.tax)
        total = subtotal + tax
        row = w.add(
            "invoice",
            invoice_number=f"IN{len(w.rows['invoice']) + 1:06d}",
            customer_id=customer_id,
            location_id=location_id,
            department_id=department_id,
            invoice_type=invoice_type,
            sales_order_id=sales_order_id,
            work_order_id=work_order_id,
            rental_contract_id=rental_contract_id,
            status="void" if void else "open",
            invoice_date=on,
            due_date=on + timedelta(days=30),
            subtotal=subtotal,
            tax_amount=tax,
            total_amount=total,
        )
        if not void:
            self._payments(row)
        return row

    def _payments(self, inv: Row) -> None:
        """Pay an invoice in one or two instalments, never more than its total."""
        w = self.w
        total: Decimal = inv["total_amount"]
        age = (w.as_of - inv["invoice_date"]).days
        if age < 3:
            return
        if age > 60:
            share = 1.0 if self.chance(0.94) else self.rng.uniform(0.3, 0.9)
        else:
            partial = self.rng.uniform(0.2, 0.8) if self.chance(0.3) else 0.0
            share = 1.0 if self.chance(0.5) else partial
        if share == 0:
            return
        to_pay = total if share == 1.0 else money(total * Decimal(str(share)))
        instalments = (
            [to_pay] if self.chance(0.8) else [money(to_pay / 2), to_pay - money(to_pay / 2)]
        )
        paid_on, paid = inv["invoice_date"], Decimal(0)
        for amount in instalments:
            latest = min(w.as_of, paid_on + timedelta(days=50))
            paid_on = w.day_between(paid_on + timedelta(days=1), latest)
            if paid_on > w.as_of or amount <= 0:
                break
            w.add(
                "payment",
                customer_id=inv["customer_id"],
                invoice_id=inv["invoice_id"],
                payment_date=paid_on,
                amount=amount,
                method=self.rng.choice(["check", "ach", "ach", "card"]),
                reference=f"R{self.rng.randint(100000, 999999)}",
            )
            paid += amount
        if paid == total:
            inv["status"] = "paid"

    # --------------------------------------------------------------- units
    def _units(self) -> None:
        w = self.w
        mix = self.spec.mix
        n_customer = round(self.spec.size.units * mix.customer_unit_share)
        for _ in range(n_customer):
            self._customer_brought_unit()
        while self.stock_rows < self.unit_target - n_customer:
            line = self.pick_line()
            new = self.chance(mix.new_share)
            model = self.rng.choice(self.models[line])
            acquired = w.day_between(w.start, w.as_of - timedelta(days=5))
            price = float(model["list_price"])
            cost = price * (self.rng.uniform(0.72, 0.82) if new else self.rng.uniform(0.4, 0.6))
            self._stock_unit(
                model=model,
                acquired=acquired,
                cost=money(round(cost, -1)),
                new=new,
                source="manufacturer" if new else "auction",
            )

    def _unit_row(self, model: Row, *, new: bool, year: int) -> Row:
        w = self.w
        row = w.add(
            "equipment",
            serial_number=f"{model['class_code']}{self.rng.randint(10_000_000, 99_999_999)}",
            model_id=model["model_id"],
            model_year=year,
        )
        line = w.fact("equipment_model", model["model_id"])["line"]
        facts = w.fact("equipment", row["equipment_id"])
        facts.update(line=line, new=new, held=None, in_transit=False, off_yard=False)
        w.truth.setdefault("product_line", {})[row["equipment_id"]] = line
        return row

    def _customer_brought_unit(self) -> None:
        w = self.w
        line = self.rng.choices(
            list(self.spec.mix.line_mix), list(self.spec.mix.line_mix.values())
        )[0]
        model = self.rng.choice(self.models[line])
        row = self._unit_row(model, new=False, year=self.rng.randint(2008, w.as_of.year))
        customer = self.rng.choice(self.trading_customers)
        row.update(ownership_type="customer", owner_customer_id=customer)
        facts = w.fact("equipment", row["equipment_id"])
        facts.update(kind="customer", state="customer", meter_base=self.rng.randint(300, 6000))
        facts["meter_rate"] = self.rng.uniform(0.6, 1.4)
        facts["meter_from"] = w.start
        self._customer_service(row, customer, w.start, sold_new_on=None)
        self._finish_unit(row)

    def _stock_unit(
        self,
        *,
        model: Row,
        acquired: date,
        cost: Decimal,
        new: bool,
        source: str,
    ) -> Row:
        w = self.w
        mix = self.spec.mix
        self.stock_rows += 1
        year = acquired.year if new else self.rng.randint(2010, acquired.year)
        row = self._unit_row(model, new=new, year=year)
        unit_id = row["equipment_id"]
        row.update(
            stock_number=f"{self.spec.tenant_code[0]}{len(w.rows['equipment']):05d}",
            condition="new" if new else "used",
            ownership_type="inventory",
            acquired_date=acquired,
            acquisition_cost=cost,
        )
        facts = w.fact("equipment", unit_id)
        facts.update(
            kind="stock",
            source=source,
            meter_base=0 if new else self.rng.randint(400, 5000),
            meter_rate=0.02,
            meter_from=acquired,
            state="in_stock",
        )
        line = facts["line"]
        row["location_id"] = self.stock_yard(line)["location_id"]
        # preparation: pre-delivery setup for new units, reconditioning for used
        if self.chance(0.7 if new else 0.75):
            self._work_order(
                row,
                kind="pdi" if new else "recon",
                on=w.day_between(acquired, acquired + timedelta(days=10)),
            )
        t = acquired + timedelta(days=self.rng.randint(3, 15))
        if t < w.as_of:
            t_sale = self._fleet_life(row, t) if self.chance(mix.fleet_share) else t
            if t_sale is not None:
                row["location_id"] = self.stock_yard(line)["location_id"]
                self._sale_path(row, t_sale)
        self._finish_unit(row)
        return row

    def _fleet_life(self, row: Row, t: date) -> date | None:
        """Rent the unit out repeatedly. Returns the day it moves to sale stock, if it does."""
        w = self.w
        mix = self.spec.mix
        facts = w.fact("equipment", row["equipment_id"])
        facts.update(fleet=True, meter_rate=4.0)
        branch = self.fleet_location()
        row.update(ownership_type="rental", location_id=branch["location_id"])
        fleet_end = t + timedelta(days=self.rng.randint(365, 1100))
        while True:
            start = t + timedelta(days=self.rng.randint(2, 30))
            if start >= w.as_of or start >= fleet_end:
                break
            length = self.rng.randint(5, 60)
            end = start + timedelta(days=length)
            customer = self.rng.choice(self.trading_customers)
            period = self.rng.choice(["day", "week", "month"])
            rate = (
                float(w.by_id["equipment_model"][row["model_id"]]["list_price"])
                * {
                    "day": 0.003,
                    "week": 0.012,
                    "month": 0.035,
                }[period]
            )
            open_now = end >= w.as_of
            contract = w.add(
                "rental_contract",
                contract_number=f"RC{len(w.rows['rental_contract']) + 1:05d}",
                customer_id=customer,
                equipment_id=row["equipment_id"],
                location_id=branch["location_id"],
                salesperson_id=self.employee("rental") or self.employee("sales"),
                contract_type="rental",
                status="open" if open_now else "returned",
                start_date=start,
                end_date=None if open_now else end,
                rate_period=period,
                rate_amount=money(rate),
            )
            periods = max(1, length // {"day": 1, "week": 7, "month": 30}[period])
            bill_on = start if open_now else end
            self.invoice(
                customer_id=customer,
                on=bill_on,
                invoice_type="rental",
                subtotal=money(rate * (1 if open_now else periods)),
                location_id=branch["location_id"],
                department_id=self._dept_id("rental"),
                rental_contract_id=contract["rental_contract_id"],
            )
            if open_now:
                facts["state"] = "on_rent"
                return None
            after = end + timedelta(days=self.rng.randint(1, 5))
            if after < w.as_of:
                if self.chance(mix.rental_damage_rate) and allowed(
                    self.spec, "rental_damage_billed_to_renter"
                ):
                    self._work_order(row, kind="rental_damage", on=after, customer=customer)
                    w.note_exception("rental_damage_billed_to_renter")
                elif self.chance(mix.fleet_repair_rate):
                    self._work_order(row, kind="fleet_repair", on=after)
            t = end
        if fleet_end >= w.as_of:
            facts["state"] = "fleet_idle"
            return None
        row["ownership_type"] = "inventory"
        facts["meter_rate"] = 0.02
        return max(t, fleet_end)

    def _dept_id(self, dept_type: str) -> int | None:
        for d in self.spec.departments:
            if d.department_type == dept_type:
                return self.dept_by_code[d.code]["department_id"]
        return None

    def _sale_path(self, row: Row, t0: date) -> None:
        w = self.w
        mix = self.spec.mix
        facts = w.fact("equipment", row["equipment_id"])
        dwell = self.rng.expovariate(1 / mix.stock_dwell_days)
        sale_on = t0 + timedelta(days=int(dwell) + 1)
        window_end = min(sale_on, w.as_of)
        for _ in range(w.poisson(mix.quotes_per_unit)):
            self._equipment_order(row, w.day_between(t0, window_end), outcome="quote")
        if (window_end - t0).days > 2 and self.chance(mix.voided_deal_rate):
            self._equipment_order(row, w.day_between(t0, window_end), outcome="voided")
        if (
            (window_end - t0).days > 2
            and self.chance(mix.dead_deposit_rate)
            and allowed(self.spec, "deposit_invoice_on_dead_order")
        ):
            self._equipment_order(row, w.day_between(t0, window_end), outcome="dead_deposit")
            w.note_exception("deposit_invoice_on_dead_order")
        if sale_on <= w.as_of - timedelta(days=5):
            order = self._equipment_order(row, sale_on, outcome="booked")
            customer = order["customer_id"]
            row.update(owner_customer_id=customer, ownership_type="customer", location_id=None)
            facts.update(state="sold", sold_on=sale_on, meter_rate=self.rng.uniform(0.6, 1.4))
            facts["meter_base"] = self.meter(row, sale_on)
            facts["meter_from"] = sale_on
            self._customer_service(
                row, customer, sale_on, sold_new_on=sale_on if facts["new"] else None
            )
            if self.chance(mix.trade_in_rate) and self.stock_rows < self.unit_target:
                self._trade_in(order, sale_on)
            return
        # still in stock on the as-of date
        if allowed(self.spec, "unit_held_without_order") and self.chance(mix.hold_share):
            facts["held"] = self.rng.choice(["DEP", "QC", "TRF"])
            w.note_exception("unit_held_without_order")
        elif allowed(self.spec, "unit_in_transit_to_yard") and self.chance(mix.in_transit_share):
            facts["in_transit"] = True
            w.note_exception("unit_in_transit_to_yard")
        elif allowed(self.spec, "for_sale_unit_off_yard") and self.chance(mix.off_yard_share):
            off = self._locations_of_type("rental_branch", "service_shop")
            if off:
                facts["off_yard"] = True
                row["location_id"] = self.rng.choice(off)["location_id"]
                w.note_exception("for_sale_unit_off_yard")

    def _equipment_order(self, unit: Row, on: date, *, outcome: str) -> Row:
        w = self.w
        facts = w.fact("equipment", unit["equipment_id"])
        dept, loc = self.selling_point(facts["line"])
        customer = self.rng.choice(self.trading_customers)
        model = w.by_id["equipment_model"][unit["model_id"]]
        base = float(model["list_price"]) if facts["new"] else float(unit["acquisition_cost"]) * 1.3
        price = money(round(base * self.rng.uniform(0.86, 1.0), -1))
        order = w.add(
            "sales_order",
            order_number=f"SO{len(w.rows['sales_order']) + 1:06d}",
            customer_id=customer,
            salesperson_id=self.salesperson_at(dept),
            location_id=loc["location_id"],
            department_id=dept["department_id"],
            order_date=on,
        )
        w.fact("sales_order", order["sales_order_id"]).update(outcome=outcome, kind="equipment")
        w.truth.setdefault("booked_sale", {})[order["sales_order_id"]] = outcome == "booked"
        self._order_line(
            order,
            "equipment",
            price,
            equipment_id=unit["equipment_id"],
            description=model["description"],
        )
        if outcome in ("booked", "quote") and self.chance(0.3):
            self._order_line(
                order,
                "attachment",
                money(self.rng.choice([1800, 3500, 6200])),
                description="bucket / attachment",
            )
        if outcome == "booked" and self.chance(0.5):
            self._order_line(
                order, "fee", money(self.rng.choice([350, 600, 950])), description="delivery"
            )
        self._order_total(order)
        if outcome == "booked":
            on_inv = min(on + timedelta(days=self.rng.randint(0, 4)), w.as_of)
            unlinked = allowed(self.spec, "sale_invoice_without_order_link") and self.chance(
                self.spec.mix.unlinked_invoice_rate
            )
            if unlinked:
                w.note_exception("sale_invoice_without_order_link")
            self.invoice(
                customer_id=customer,
                on=on_inv,
                invoice_type="equipment",
                subtotal=order["total_amount"],
                location_id=loc["location_id"],
                department_id=dept["department_id"],
                sales_order_id=None if unlinked else order["sales_order_id"],
            )
        elif outcome == "voided":
            self.invoice(
                customer_id=customer,
                on=min(on + timedelta(days=2), w.as_of),
                invoice_type="equipment",
                subtotal=order["total_amount"],
                location_id=loc["location_id"],
                department_id=dept["department_id"],
                sales_order_id=order["sales_order_id"],
                void=True,
            )
        elif outcome == "dead_deposit":
            self.invoice(
                customer_id=customer,
                on=min(on + timedelta(days=1), w.as_of),
                invoice_type="equipment",
                subtotal=money(self.rng.choice([2500, 5000, 10000])),
                location_id=loc["location_id"],
                department_id=dept["department_id"],
                sales_order_id=order["sales_order_id"],
            )
        return order

    def _order_line(
        self,
        order: Row,
        line_type: str,
        amount: Decimal,
        *,
        equipment_id: int | None = None,
        part_id: int | None = None,
        quantity: Decimal = Decimal("1.00"),
        description: str | None = None,
    ) -> Row:
        row = self.w.add(
            "sales_order_line",
            sales_order_id=order["sales_order_id"],
            line_type=line_type,
            equipment_id=equipment_id,
            part_id=part_id,
            description=description,
            quantity=quantity,
            unit_price=money(amount / quantity),
            line_amount=amount,
        )
        self.order_lines.setdefault(order["sales_order_id"], []).append(row)
        return row

    def _order_total(self, order: Row) -> None:
        lines = [
            r
            for r in self.w.rows["sales_order_line"]
            if r["sales_order_id"] == order["sales_order_id"]
        ]
        order["total_amount"] = sum((r["line_amount"] for r in lines), Decimal(0))

    def _trade_in(self, order: Row, on: date) -> None:
        line = self.rng.choices(
            list(self.spec.mix.line_mix), list(self.spec.mix.line_mix.values())
        )[0]
        model = self.rng.choice(self.models[line])
        allowance = money(round(float(model["list_price"]) * self.rng.uniform(0.3, 0.5), -2))
        # the traded unit is new to the dealer: it gets its own equipment row
        traded = self._stock_unit(
            model=model, acquired=on, cost=allowance, new=False, source="trade_in"
        )
        self._order_line(
            order,
            "trade_in",
            -allowance,
            equipment_id=traded["equipment_id"],
            description="trade-in allowance",
        )
        self._order_total(order)

    def _customer_service(
        self, unit: Row, customer: int, t0: date, *, sold_new_on: date | None
    ) -> None:
        w = self.w
        mix = self.spec.mix
        years = max((w.as_of - t0).days, 0) / 365
        for _ in range(w.poisson(mix.service_visits_per_year * years)):
            on = w.day_between(t0 + timedelta(days=5), w.as_of - timedelta(days=1))
            if on <= t0:
                continue
            warranty = (
                sold_new_on is not None
                and (on - sold_new_on).days < 365
                and self.chance(mix.warranty_rate * 3)
            )
            wo = self._work_order(
                unit, kind="warranty" if warranty else "customer_service", on=on, customer=customer
            )
            if (
                not warranty
                and wo["closed_date"] is not None
                and self.chance(mix.rework_rate)
                and allowed(self.spec, "rework_absorbed_on_customer_unit")
            ):
                again = wo["closed_date"] + timedelta(days=self.rng.randint(2, 20))
                if again < w.as_of:
                    self._work_order(unit, kind="rework", on=again, customer=customer)
                    w.note_exception("rework_absorbed_on_customer_unit")

    # --------------------------------------------------------- work orders
    def meter(self, unit: Row, on: date) -> Decimal:
        facts = self.w.fact("equipment", unit["equipment_id"])
        days = max((on - facts["meter_from"]).days, 0)
        return qty(round(float(facts["meter_base"]) + days * facts["meter_rate"], 1))

    def _work_order(self, unit: Row, *, kind: str, on: date, customer: int | None = None) -> Row:
        w = self.w
        on = min(on, w.as_of)
        internal = kind in ("pdi", "recon", "fleet_repair", "rework")
        if kind in ("pdi", "recon"):
            bill_to = self.house["shop"]
        elif kind == "fleet_repair":
            bill_to = self.house["fleet"]
        elif kind == "warranty":
            make = w.by_id["equipment_model"][unit["model_id"]]["make"]
            bill_to = self.manufacturer[make]
        else:
            assert customer is not None
            bill_to = customer
        loc = (
            self.shop_location()
            if unit["location_id"] is None
            else w.by_id["location"][unit["location_id"]]
        )
        if loc["location_type"] not in ("service_shop", "sales_yard"):
            loc = self.shop_location()
        duration = self.rng.randint(0, 12)
        closed = on + timedelta(days=duration)
        if closed > w.as_of:
            closed = None
        service_type = {
            "pdi": "setup",
            "recon": "repair",
            "fleet_repair": "repair",
            "rental_damage": "repair",
            "warranty": "repair",
            "rework": "repair",
        }.get(kind) or self.rng.choices(["maintenance", "repair", "inspection"], [0.4, 0.5, 0.1])[0]
        wo_type = "warranty" if kind == "warranty" else ("internal" if internal else "customer")
        wo = w.add(
            "work_order",
            work_order_number=f"WO{len(w.rows['work_order']) + 1:06d}",
            customer_id=bill_to,
            equipment_id=unit["equipment_id"],
            location_id=loc["location_id"],
            department_id=self.service_dept()["department_id"],
            technician_id=self.employee("service"),
            work_order_type=wo_type,
            service_type=service_type,
            status=self._wo_status(closed, internal),
            opened_date=on,
            closed_date=closed,
            meter_reading=self.meter(unit, on),
        )
        w.fact("work_order", wo["work_order_id"]).update(kind=kind, internal=internal)
        w.truth.setdefault("internal_work", {})[wo["work_order_id"]] = internal
        subtotal = self._work_order_lines(
            wo, kind=kind, internal=internal, service_type=service_type
        )
        if closed is not None and kind == "warranty":
            make = w.by_id["equipment_model"][unit["model_id"]]["make"]
            paid = closed + timedelta(days=self.rng.randint(20, 70))
            approved = self.chance(0.85)
            w.add(
                "warranty_claim",
                claim_number=f"WC{len(w.rows['warranty_claim']) + 1:05d}",
                work_order_id=wo["work_order_id"],
                equipment_id=unit["equipment_id"],
                manufacturer=make,
                status=("paid" if paid <= w.as_of else "approved") if approved else "rejected",
                submitted_date=closed,
                paid_date=paid if approved and paid <= w.as_of else None,
                claimed_amount=subtotal,
                approved_amount=subtotal if approved else None,
            )
        elif closed is not None and not internal:
            self.invoice(
                customer_id=bill_to,
                on=closed,
                invoice_type="service",
                subtotal=subtotal,
                location_id=loc["location_id"],
                department_id=wo["department_id"],
                work_order_id=wo["work_order_id"],
            )
        return wo

    def _wo_status(self, closed: date | None, internal: bool) -> str:
        if closed is None:
            return "open"
        # billed jobs are often left at 'complete', so the status does not mark internal work
        return "complete" if internal or self.chance(0.5) else "invoiced"

    def _work_order_lines(self, wo: Row, kind: str, internal: bool, service_type: str) -> Decimal:
        w = self.w
        ops = self.spec.vocabulary["work_order_line.operation_code"]
        # customer labour rate, internal labour rate, technician cost per hour
        rate, internal_rate, tech_cost = Decimal(135), Decimal(95), Decimal(58)
        total = Decimal(0)
        heavy = kind == "rental_damage"  # damage repairs are big jobs
        for _ in range(self.rng.randint(2, 4) if heavy else self.rng.randint(1, 3)):
            hours = qty(self.rng.choice([3, 4, 6, 8] if heavy else [0.5, 1, 1.5, 2, 3, 4, 6, 8]))
            price = internal_rate if internal else rate
            amount = money(hours * price)
            w.add(
                "work_order_line",
                work_order_id=wo["work_order_id"],
                line_type="labor",
                operation_code=self._op_code(ops, kind, service_type),
                technician_id=wo["technician_id"],
                description=f"{service_type} labour",
                labor_hours=hours,
                unit_price=price,
                unit_cost=tech_cost,
                line_amount=amount,
            )
            total += amount
        for _ in range(self.rng.randint(0, 3)):
            part = self.rng.choice(self.parts)
            n = qty(self.rng.randint(1, 4))
            price = part["unit_cost"] if internal else part["list_price"]
            amount = money(n * price)
            w.add(
                "work_order_line",
                work_order_id=wo["work_order_id"],
                line_type="part",
                part_id=part["part_id"],
                description=part["description"],
                quantity=n,
                unit_price=price,
                unit_cost=part["unit_cost"],
                line_amount=amount,
            )
            total += amount
        return total

    def _op_code(self, ops: list[str], kind: str, service_type: str) -> str:
        # positions in the tenant's own operation-code list
        if kind == "pdi":
            return ops[3] if len(ops) > 3 else ops[0]
        if kind == "warranty":
            return ops[-1]
        if service_type == "maintenance":
            return ops[2] if len(ops) > 2 else ops[0]
        return self.rng.choice(ops[:2])

    # --------------------------------------------------------------- parts
    def _parts_orders(self) -> None:
        w = self.w
        years = self.spec.history_years
        n = self.spec.size.parts_orders_per_year * years
        parts_id = self._dept_id("parts")
        counters = self._locations_of_type("parts_depot", "sales_yard")
        for _ in range(n):
            on = w.day_between(w.start, w.as_of - timedelta(days=1))
            booked = self.chance(0.88)
            loc = self.rng.choice(counters)
            customer = self.rng.choice(self.trading_customers)
            order = w.add(
                "sales_order",
                order_number=f"SO{len(w.rows['sales_order']) + 1:06d}",
                customer_id=customer,
                salesperson_id=self.employee("parts"),
                location_id=loc["location_id"],
                department_id=parts_id,
                order_date=on,
            )
            outcome = "booked" if booked else "abandoned"
            w.fact("sales_order", order["sales_order_id"]).update(outcome=outcome, kind="parts")
            w.truth.setdefault("booked_sale", {})[order["sales_order_id"]] = booked
            for _ in range(self.rng.randint(1, 4)):
                part = self.rng.choice(self.parts)
                n_q = qty(self.rng.randint(1, 6))
                self._order_line(
                    order,
                    "part",
                    money(n_q * part["list_price"]),
                    part_id=part["part_id"],
                    quantity=n_q,
                    description=part["description"],
                )
            self._order_total(order)
            if booked:
                self.invoice(
                    customer_id=customer,
                    on=min(on + timedelta(days=self.rng.randint(0, 2)), w.as_of),
                    invoice_type="parts",
                    subtotal=order["total_amount"],
                    location_id=loc["location_id"],
                    department_id=order["department_id"],
                    sales_order_id=order["sales_order_id"],
                )

    # -------------------------------------------------------------- finish
    def _finish_unit(self, row: Row) -> None:
        """Record the as-of state of a unit: meter and the available-to-sell truth."""
        w = self.w
        facts = w.fact("equipment", row["equipment_id"])
        row["meter_reading"] = self.meter(row, w.as_of)
        state = facts["state"]
        available = (state == "in_stock" and not facts["held"] and not facts["in_transit"]) or (
            state == "fleet_idle" and self.spec.idle_fleet_is_for_sale
        )
        w.truth.setdefault("available_to_sell", {})[row["equipment_id"]] = available


def spec_units_target(spec: TenantSpec) -> int:
    return spec.size.units
