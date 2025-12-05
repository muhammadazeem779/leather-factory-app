from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3, os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "leather_factory_app.db")

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

app = Flask(__name__)
app.secret_key = "change-this-key"

# ---------- DATABASE INIT ----------

def init_db():
    con = db()
    cur = con.cursor()
    cur.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS vendors (
        vendor_id       INTEGER PRIMARY KEY,
        name            TEXT NOT NULL UNIQUE,
        vendor_type     TEXT CHECK(vendor_type IN ('raw_leather','chemical','service','other')) NOT NULL,
        phone           TEXT,
        email           TEXT,
        tax_id          TEXT,
        address_line1   TEXT,
        address_line2   TEXT,
        city            TEXT,
        state           TEXT,
        postal_code     TEXT,
        country         TEXT,
        is_active       INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS chemicals (
        chemical_id     INTEGER PRIMARY KEY,
        sku             TEXT,
        name            TEXT NOT NULL UNIQUE,
        default_unit    TEXT CHECK(default_unit IN ('kg','g','L','mL','pcs')) NOT NULL,
        hazard_notes    TEXT,
        preferred_vendor_id INTEGER,
        unit_cost       REAL,
        FOREIGN KEY(preferred_vendor_id) REFERENCES vendors(vendor_id)
    );

    CREATE TABLE IF NOT EXISTS processes (
        process_id      INTEGER PRIMARY KEY,
        name            TEXT NOT NULL UNIQUE,
        description     TEXT
    );

    CREATE TABLE IF NOT EXISTS articles (
        article_id      INTEGER PRIMARY KEY,
        article_code    TEXT NOT NULL UNIQUE,
        description     TEXT
    );

    CREATE TABLE IF NOT EXISTS article_process_flow (
        apf_id          INTEGER PRIMARY KEY,
        article_id      INTEGER NOT NULL,
        process_id      INTEGER NOT NULL,
        sequence_order  INTEGER NOT NULL,
        UNIQUE(article_id, process_id),
        FOREIGN KEY(article_id) REFERENCES articles(article_id) ON DELETE CASCADE,
        FOREIGN KEY(process_id) REFERENCES processes(process_id) ON DELETE RESTRICT
    );
    CREATE INDEX IF NOT EXISTS idx_apf_article ON article_process_flow(article_id);
    CREATE INDEX IF NOT EXISTS idx_apf_order   ON article_process_flow(article_id, sequence_order);

    CREATE TABLE IF NOT EXISTS raw_leather_lots (
        lot_id          INTEGER PRIMARY KEY,
        lot_code        TEXT NOT NULL UNIQUE,
        vendor_id       INTEGER NOT NULL,
        purchase_date   TEXT NOT NULL,
        weight_kg       REAL,
        unit_cost       REAL,
        currency        TEXT DEFAULT 'USD',
        notes           TEXT,
        FOREIGN KEY(vendor_id) REFERENCES vendors(vendor_id)
    );

    CREATE TABLE IF NOT EXISTS batches (
        batch_id        INTEGER PRIMARY KEY,
        batch_code      TEXT NOT NULL UNIQUE,
        lot_id          INTEGER NOT NULL,
        article_id      INTEGER,
        start_date      TEXT,
        planned_finish_date TEXT,
        actual_finish_date  TEXT,
        notes           TEXT,
        FOREIGN KEY(lot_id) REFERENCES raw_leather_lots(lot_id),
        FOREIGN KEY(article_id) REFERENCES articles(article_id)
    );

    CREATE TABLE IF NOT EXISTS batch_process_runs (
        run_id          INTEGER PRIMARY KEY,
        batch_id        INTEGER NOT NULL,
        process_id      INTEGER NOT NULL,
        started_at      TEXT,
        ended_at        TEXT,
        operator        TEXT,
        yield_kg        REAL,
        notes           TEXT,
        FOREIGN KEY(batch_id) REFERENCES batches(batch_id),
        FOREIGN KEY(process_id) REFERENCES processes(process_id)
    );

    CREATE TABLE IF NOT EXISTS batch_run_chemicals (
        id              INTEGER PRIMARY KEY,
        run_id          INTEGER NOT NULL,
        chemical_id     INTEGER NOT NULL,
        qty             REAL NOT NULL,
        unit            TEXT CHECK(unit IN ('kg','g','L','mL','pcs')) NOT NULL,
        unit_cost       REAL,
        FOREIGN KEY(run_id) REFERENCES batch_process_runs(run_id),
        FOREIGN KEY(chemical_id) REFERENCES chemicals(chemical_id)
    );

    CREATE TABLE IF NOT EXISTS finished_lots (
        finished_id     INTEGER PRIMARY KEY,
        batch_id        INTEGER NOT NULL,
        finished_code   TEXT,
        finish_date     TEXT,
        grade           TEXT,
        color           TEXT,
        thickness_mm    REAL,
        area_sqft       REAL,
        weight_kg       REAL,
        notes           TEXT,
        FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
    );

    CREATE TABLE IF NOT EXISTS bank_statements (
        bank_txn_id     INTEGER PRIMARY KEY,
        bank_name       TEXT,
        account_last4   TEXT,
        txn_date        TEXT NOT NULL,
        description     TEXT NOT NULL,
        amount          REAL NOT NULL,
        currency        TEXT DEFAULT 'USD',
        imported_file   TEXT
    );

    CREATE TABLE IF NOT EXISTS bank_rules (
        rule_id         INTEGER PRIMARY KEY,
        contains_text   TEXT,
        default_payee   TEXT,
        default_vendor_id INTEGER,
        default_process TEXT,
        default_note    TEXT,
        FOREIGN KEY(default_vendor_id) REFERENCES vendors(vendor_id)
    );

    CREATE VIEW IF NOT EXISTS v_run_chemical_cost AS
    SELECT
        brc.run_id,
        brc.chemical_id,
        brc.qty,
        brc.unit,
        COALESCE(brc.unit_cost, c.unit_cost, 0) AS effective_unit_cost,
        (brc.qty * COALESCE(brc.unit_cost, c.unit_cost, 0)) AS line_cost
    FROM batch_run_chemicals brc
    LEFT JOIN chemicals c ON c.chemical_id = brc.chemical_id;

    CREATE VIEW IF NOT EXISTS v_run_cost AS
    SELECT
        run_id,
        SUM(line_cost) AS chemicals_cost
    FROM v_run_chemical_cost
    GROUP BY run_id;

    CREATE VIEW IF NOT EXISTS v_batch_chemicals_cost AS
    SELECT
        r.batch_id,
        SUM(rc.chemicals_cost) AS total_chem_cost
    FROM batch_process_runs r
    LEFT JOIN v_run_cost rc ON rc.run_id = r.run_id
    GROUP BY r.batch_id;

    CREATE VIEW IF NOT EXISTS v_batch_total_cost AS
    SELECT
        b.batch_id,
        b.batch_code,
        rll.weight_kg * COALESCE(rll.unit_cost,0) AS raw_cost,
        COALESCE(bc.total_chem_cost,0) AS chemicals_cost,
        (rll.weight_kg * COALESCE(rll.unit_cost,0)) + COALESCE(bc.total_chem_cost,0) AS total_cost_estimate
    FROM batches b
    JOIN raw_leather_lots rll ON rll.lot_id = b.lot_id
    LEFT JOIN v_batch_chemicals_cost bc ON bc.batch_id = b.batch_id;
    """)

    # Seed basic master data
    cur.executemany(
        "INSERT OR IGNORE INTO vendors(name, vendor_type, country) VALUES (?,?,?)",
        [
            ("Alpha Hides Co.", "raw_leather", "USA"),
            ("ChemPro Supplies", "chemical", "USA")
        ]
    )
    cur.executemany(
        "INSERT OR IGNORE INTO processes(name, description) VALUES (?,?)",
        [
            ("Soaking", "Rehydrate hides"),
            ("Liming", "Hair removal / opening fiber"),
            ("Pickling", "Acid + salt before tanning"),
            ("Tanning", "Stabilize collagen"),
            ("Dyeing", "Apply color"),
            ("Finishing", "Surface finishing and grading")
        ]
    )
    cur.executemany(
        "INSERT OR IGNORE INTO articles(article_code, description) VALUES (?,?)",
        [
            ("ART-ANILINE-BLUE", "Aniline-dyed blue leather"),
            ("ART-NATURAL", "Natural finish")
        ]
    )
    # Sample flexible flows
    cur.executemany(
        "INSERT OR IGNORE INTO article_process_flow(article_id, process_id, sequence_order) VALUES (?,?,?)",
        [
            (1, 1, 1),  # ART-ANILINE-BLUE: Soaking
            (1, 3, 2),  # Pickling
            (1, 4, 3),  # Tanning
            (1, 5, 4),  # Dyeing
            (1, 6, 5),  # Finishing
            (2, 1, 1),  # ART-NATURAL: Soaking
            (2, 2, 2),  # Liming
            (2, 4, 3),  # Tanning
            (2, 6, 4)   # Finishing
        ]
    )

    con.commit()
    con.close()

# ---------- ROUTES ----------

@app.route("/")
def index():
    con = db()
    articles = con.execute("SELECT * FROM articles ORDER BY article_code").fetchall()
    con.close()
    return render_template("index.html", articles=articles)

# Vendors
@app.route("/vendors")
def vendors():
    con = db()
    rows = con.execute("SELECT * FROM vendors ORDER BY name").fetchall()
    con.close()
    return render_template("vendors.html", rows=rows)

@app.route("/vendors/add", methods=["POST"])
def vendors_add():
    f = request.form
    con = db()
    con.execute("""
        INSERT INTO vendors(name, vendor_type, phone, email, tax_id,
                            address_line1, address_line2, city, state,
                            postal_code, country, is_active)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        f["name"],
        f["vendor_type"],
        f.get("phone"),
        f.get("email"),
        f.get("tax_id"),
        f.get("address_line1"),
        f.get("address_line2"),
        f.get("city"),
        f.get("state"),
        f.get("postal_code"),
        f.get("country", "USA"),
        int(f.get("is_active", "1"))
    ))
    con.commit()
    con.close()
    flash("Vendor added")
    return redirect(url_for("vendors"))

# Chemicals
@app.route("/chemicals")
def chemicals():
    con = db()
    rows = con.execute("""
        SELECT c.*, v.name AS preferred_vendor_name
        FROM chemicals c
        LEFT JOIN vendors v ON v.vendor_id = c.preferred_vendor_id
        ORDER BY c.name
    """).fetchall()
    vendors = con.execute("""
        SELECT vendor_id, name
        FROM vendors
        WHERE vendor_type IN ('chemical','other')
        ORDER BY name
    """).fetchall()
    con.close()
    return render_template("chemicals.html", rows=rows, vendors=vendors)

@app.route("/chemicals/add", methods=["POST"])
def chemicals_add():
    f = request.form
    con = db()
    con.execute("""
        INSERT INTO chemicals(sku, name, default_unit, hazard_notes, preferred_vendor_id, unit_cost)
        VALUES (?,?,?,?,?,?)
    """, (
        f.get("sku"),
        f["name"],
        f["default_unit"],
        f.get("hazard_notes"),
        None if f.get("preferred_vendor_id") in (None, "", "0") else int(f["preferred_vendor_id"]),
        None if f.get("unit_cost") in (None, "") else float(f["unit_cost"])
    ))
    con.commit()
    con.close()
    flash("Chemical added")
    return redirect(url_for("chemicals"))

# Processes
@app.route("/processes")
def processes():
    con = db()
    rows = con.execute("SELECT * FROM processes ORDER BY name").fetchall()
    con.close()
    return render_template("processes.html", rows=rows)

@app.route("/processes/add", methods=["POST"])
def processes_add():
    f = request.form
    con = db()
    con.execute("INSERT INTO processes(name, description) VALUES (?,?)",
                (f["name"], f.get("description")))
    con.commit()
    con.close()
    flash("Process added")
    return redirect(url_for("processes"))

# Articles + flexible flow
@app.route("/articles")
def articles():
    con = db()
    rows = con.execute("SELECT * FROM articles ORDER BY article_code").fetchall()
    con.close()
    return render_template("articles.html", rows=rows)

@app.route("/articles/add", methods=["POST"])
def articles_add():
    f = request.form
    con = db()
    con.execute("INSERT INTO articles(article_code, description) VALUES (?,?)",
                (f["article_code"], f.get("description")))
    con.commit()
    con.close()
    flash("Article added")
    return redirect(url_for("articles"))

@app.route("/articles/<int:article_id>/flow")
def article_flow(article_id):
    con = db()
    article = con.execute("SELECT * FROM articles WHERE article_id=?",
                          (article_id,)).fetchone()
    processes = con.execute("SELECT * FROM processes ORDER BY name").fetchall()
    flow = con.execute("""
        SELECT apf.*, p.name AS process_name
        FROM article_process_flow apf
        JOIN processes p ON p.process_id = apf.process_id
        WHERE apf.article_id=?
        ORDER BY apf.sequence_order
    """, (article_id,)).fetchall()
    con.close()
    return render_template("article_flow.html",
                           article=article, processes=processes, flow=flow)

@app.route("/articles/<int:article_id>/flow/add", methods=["POST"])
def article_flow_add(article_id):
    f = request.form
    con = db()
    con.execute("""
        INSERT INTO article_process_flow(article_id, process_id, sequence_order)
        VALUES (?,?,?)
    """, (
        article_id,
        int(f["process_id"]),
        int(f["sequence_order"])
    ))
    con.commit()
    con.close()
    flash("Step added")
    return redirect(url_for("article_flow", article_id=article_id))

@app.route("/articles/<int:article_id>/flow/delete/<int:apf_id>", methods=["POST"])
def article_flow_delete(article_id, apf_id):
    con = db()
    con.execute("DELETE FROM article_process_flow WHERE apf_id=?", (apf_id,))
    con.commit()
    con.close()
    flash("Step removed")
    return redirect(url_for("article_flow", article_id=article_id))

# Raw lots
@app.route("/lots")
def lots():
    con = db()
    rows = con.execute("""
        SELECT r.*, v.name AS vendor_name
        FROM raw_leather_lots r
        JOIN vendors v ON v.vendor_id = r.vendor_id
        ORDER BY purchase_date DESC, lot_id DESC
    """).fetchall()
    vendors = con.execute("""
        SELECT vendor_id, name FROM vendors
        WHERE vendor_type='raw_leather'
        ORDER BY name
    """).fetchall()
    con.close()
    return render_template("lots.html", rows=rows, vendors=vendors)

@app.route("/lots/add", methods=["POST"])
def lots_add():
    f = request.form
    con = db()
    con.execute("""
        INSERT INTO raw_leather_lots(lot_code, vendor_id, purchase_date,
                                     weight_kg, unit_cost, currency, notes)
        VALUES (?,?,?,?,?,?,?)
    """, (
        f["lot_code"],
        int(f["vendor_id"]),
        f["purchase_date"],
        None if f.get("weight_kg") in (None, "") else float(f["weight_kg"]),
        None if f.get("unit_cost") in (None, "") else float(f["unit_cost"]),
        f.get("currency", "USD"),
        f.get("notes")
    ))
    con.commit()
    con.close()
    flash("Raw lot added")
    return redirect(url_for("lots"))

# Batches
@app.route("/batches")
def batches():
    con = db()
    rows = con.execute("""
        SELECT b.*, r.lot_code, a.article_code
        FROM batches b
        JOIN raw_leather_lots r ON r.lot_id = b.lot_id
        LEFT JOIN articles a ON a.article_id = b.article_id
        ORDER BY b.batch_id DESC
    """).fetchall()
    lots = con.execute("SELECT lot_id, lot_code FROM raw_leather_lots ORDER BY lot_id DESC").fetchall()
    articles = con.execute("SELECT article_id, article_code FROM articles ORDER BY article_code").fetchall()
    con.close()
    return render_template("batches.html", rows=rows, lots=lots, articles=articles)

@app.route("/batches/add", methods=["POST"])
def batches_add():
    f = request.form
    con = db()
    con.execute("""
        INSERT INTO batches(batch_code, lot_id, article_id, start_date, notes)
        VALUES (?,?,?,?,?)
    """, (
        f["batch_code"],
        int(f["lot_id"]),
        None if f.get("article_id") in (None, "", "0") else int(f["article_id"]),
        f.get("start_date"),
        f.get("notes")
    ))
    con.commit()
    con.close()
    flash("Batch added")
    return redirect(url_for("batches"))

# Runs
@app.route("/runs")
def runs():
    con = db()
    rows = con.execute("""
        SELECT r.run_id, r.batch_id, r.process_id, r.started_at, r.ended_at,
               r.operator, r.yield_kg, r.notes,
               b.batch_code, p.name AS process_name
        FROM batch_process_runs r
        JOIN batches b ON b.batch_id = r.batch_id
        JOIN processes p ON p.process_id = r.process_id
        ORDER BY r.run_id DESC
    """).fetchall()
    batches = con.execute("SELECT batch_id, batch_code FROM batches ORDER BY batch_id DESC").fetchall()
    processes = con.execute("SELECT process_id, name FROM processes ORDER BY name").fetchall()
    con.close()
    return render_template("runs.html", rows=rows, batches=batches, processes=processes)

@app.route("/runs/add", methods=["POST"])
def runs_add():
    f = request.form
    con = db()
    con.execute("""
        INSERT INTO batch_process_runs(batch_id, process_id, started_at, ended_at,
                                       operator, yield_kg, notes)
        VALUES (?,?,?,?,?,?,?)
    """, (
        int(f["batch_id"]),
        int(f["process_id"]),
        f.get("started_at"),
        f.get("ended_at"),
        f.get("operator"),
        None if f.get("yield_kg") in (None, "") else float(f["yield_kg"]),
        f.get("notes")
    ))
    con.commit()
    con.close()
    flash("Run added")
    return redirect(url_for("runs"))

# Run chemicals
@app.route("/run_chemicals")
def run_chemicals():
    con = db()
    rows = con.execute("""
        SELECT rc.id, rc.run_id, rc.qty, rc.unit, rc.unit_cost,
               r.batch_id, b.batch_code, p.name AS process_name,
               c.name AS chemical_name
        FROM batch_run_chemicals rc
        JOIN batch_process_runs r ON r.run_id = rc.run_id
        JOIN batches b ON b.batch_id = r.batch_id
        JOIN processes p ON p.process_id = r.process_id
        JOIN chemicals c ON c.chemical_id = rc.chemical_id
        ORDER BY rc.id DESC
    """).fetchall()
    runs = con.execute("""
        SELECT r.run_id,
               b.batch_code || ' - ' || p.name AS label
        FROM batch_process_runs r
        JOIN batches b ON b.batch_id = r.batch_id
        JOIN processes p ON p.process_id = r.process_id
        ORDER BY r.run_id DESC
    """).fetchall()
    chemicals = con.execute("SELECT chemical_id, name FROM chemicals ORDER BY name").fetchall()
    con.close()
    return render_template("run_chemicals.html", rows=rows, runs=runs, chemicals=chemicals)

@app.route("/run_chemicals/add", methods=["POST"])
def run_chemicals_add():
    f = request.form
    con = db()
    con.execute("""
        INSERT INTO batch_run_chemicals(run_id, chemical_id, qty, unit, unit_cost)
        VALUES (?,?,?,?,?)
    """, (
        int(f["run_id"]),
        int(f["chemical_id"]),
        float(f["qty"]),
        f["unit"],
        None if f.get("unit_cost") in (None, "") else float(f["unit_cost"])
    ))
    con.commit()
    con.close()
    flash("Chemical usage added")
    return redirect(url_for("run_chemicals"))

# Costing report
@app.route("/reports/costing")
def report_costing():
    con = db()
    rows = con.execute("SELECT * FROM v_batch_total_cost ORDER BY batch_id DESC").fetchall()
    con.close()
    return render_template("report_costing.html", rows=rows)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
