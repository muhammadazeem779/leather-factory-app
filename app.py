from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3, os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "leather_factory_app.db")

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

app = Flask(__name__)
app.secret_key = "x"

def init_db():
    # create DB with basic tables if not exists
    con = db()
    cur = con.cursor()
    cur.executescript("""
    PRAGMA foreign_keys = ON;
    CREATE TABLE IF NOT EXISTS processes (
        process_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        description TEXT
    );
    CREATE TABLE IF NOT EXISTS articles (
        article_id INTEGER PRIMARY KEY,
        article_code TEXT NOT NULL UNIQUE,
        description TEXT
    );
    CREATE TABLE IF NOT EXISTS article_process_flow (
        apf_id INTEGER PRIMARY KEY,
        article_id INTEGER NOT NULL,
        process_id INTEGER NOT NULL,
        sequence_order INTEGER NOT NULL,
        UNIQUE(article_id, process_id),
        FOREIGN KEY(article_id) REFERENCES articles(article_id) ON DELETE CASCADE,
        FOREIGN KEY(process_id) REFERENCES processes(process_id) ON DELETE RESTRICT
    );
    """)
    # seed sample data
    cur.executemany(
        "INSERT OR IGNORE INTO processes(name, description) VALUES (?,?)",
        [("Soaking","Rehydrate hides"),("Tanning","Stabilize"),("Dyeing","Apply color")]
    )
    cur.executemany(
        "INSERT OR IGNORE INTO articles(article_code, description) VALUES (?,?)",
        [("ART-1","Sample article"),("ART-2","Another article")]
    )
    cur.executemany(
        "INSERT OR IGNORE INTO article_process_flow(article_id, process_id, sequence_order) VALUES (?,?,?)",
        [(1,1,1),(1,2,2),(1,3,3)]
    )
    con.commit()
    con.close()

@app.route("/")
def index():
    con = db()
    arts = con.execute("SELECT * FROM articles").fetchall()
    con.close()
    return render_template("index.html", arts=arts)

@app.route("/articles/<int:aid>/flow")
def flow(aid):
    con = db()
    art = con.execute("SELECT * FROM articles WHERE article_id=?", (aid,)).fetchone()
    procs = con.execute("SELECT * FROM processes ORDER BY name").fetchall()
    steps = con.execute(
        "SELECT apf.*, p.name as process_name "
        "FROM article_process_flow apf "
        "JOIN processes p ON p.process_id=apf.process_id "
        "WHERE article_id=? ORDER BY sequence_order",
        (aid,)
    ).fetchall()
    con.close()
    return render_template("flow.html", art=art, procs=procs, steps=steps)

@app.route("/articles/<int:aid>/flow/add", methods=["POST"])
def flow_add(aid):
    con = db()
    con.execute(
        "INSERT INTO article_process_flow(article_id, process_id, sequence_order) VALUES (?,?,?)",
        (aid, int(request.form["process_id"]), int(request.form["order"]))
    )
    con.commit()
    con.close()
    flash("Step added")
    return redirect(url_for("flow", aid=aid))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
