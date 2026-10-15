
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, send_from_directory
)
import sqlite3
import os
from pathlib import Path
from datetime import date

app = Flask(__name__, template_folder=".")
app.secret_key = os.environ.get(
    "SECRET_KEY", "local-demo-change-this-key"
)

DB_PATH = Path(__file__).resolve().parent / "expenses.db"


def connect_db():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connect_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                expense_date TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                name TEXT PRIMARY KEY,
                value REAL NOT NULL
            )
        """)

        db.execute("""
            INSERT OR IGNORE INTO settings (name, value)
            VALUES ('monthly_budget', 10000)
        """)


def get_budget(db):
    row = db.execute(
        "SELECT value FROM settings WHERE name = 'monthly_budget'"
    ).fetchone()
    return float(row["value"]) if row else 10000.0


# Initialize tables when Flask or Gunicorn loads this module.
init_db()


@app.route("/")
def home():
    month = date.today().strftime("%Y-%m")

    with connect_db() as db:
        total = db.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE substr(expense_date, 1, 7) = ?
        """, (month,)).fetchone()["total"]

        count = db.execute("""
            SELECT COUNT(*) AS count
            FROM expenses
            WHERE substr(expense_date, 1, 7) = ?
        """, (month,)).fetchone()["count"]

        recent = db.execute("""
            SELECT * FROM expenses
            ORDER BY expense_date DESC, id DESC
            LIMIT 5
        """).fetchall()

        budget = get_budget(db)

    return render_template(
        "templates.html",
        page="home",
        total=float(total),
        count=count,
        recent=recent,
        budget=budget,
        remaining=budget - float(total)
    )


@app.route("/add", methods=["GET", "POST"])
def add_expense():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        amount_text = request.form.get("amount", "").strip()
        expense_date = request.form.get("expense_date", "").strip()

        if not title or not category or not amount_text or not expense_date:
            flash("Please fill in all fields.")
            return redirect(url_for("add_expense"))

        try:
            amount = float(amount_text)
            date.fromisoformat(expense_date)
            if amount <= 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid date and an amount greater than zero.")
            return redirect(url_for("add_expense"))

        allowed_categories = {
            "Food", "Travel", "Education", "Shopping",
            "Entertainment", "Bills", "Health", "Other"
        }
        if category not in allowed_categories:
            flash("Please choose a valid category.")
            return redirect(url_for("add_expense"))

        with connect_db() as db:
            db.execute("""
                INSERT INTO expenses
                    (title, category, amount, expense_date)
                VALUES (?, ?, ?, ?)
            """, (title, category, amount, expense_date))

        flash("Expense added successfully!")
        return redirect(url_for("expenses"))

    return render_template(
        "templates.html",
        page="add",
        today=date.today().isoformat()
    )


@app.route("/expenses")
def expenses():
    search = request.args.get("search", "").strip()

    with connect_db() as db:
        rows = db.execute("""
            SELECT * FROM expenses
            WHERE title LIKE ? OR category LIKE ?
            ORDER BY expense_date DESC, id DESC
        """, (f"%{search}%", f"%{search}%")).fetchall()

    total = sum(float(row["amount"]) for row in rows)

    return render_template(
        "templates.html",
        page="expenses",
        expenses=rows,
        search=search,
        total=total
    )


@app.route("/delete/<int:expense_id>", methods=["POST"])
def delete_expense(expense_id):
    with connect_db() as db:
        db.execute(
            "DELETE FROM expenses WHERE id = ?",
            (expense_id,)
        )

    flash("Expense deleted successfully.")
    return redirect(url_for("expenses"))


@app.route("/budget", methods=["GET", "POST"])
def budget():
    if request.method == "POST":
        try:
            amount = float(request.form.get("budget", ""))
            if amount <= 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid budget greater than zero.")
            return redirect(url_for("budget"))

        with connect_db() as db:
            db.execute("""
                UPDATE settings
                SET value = ?
                WHERE name = 'monthly_budget'
            """, (amount,))

        flash("Monthly budget updated successfully!")
        return redirect(url_for("budget"))

    month = date.today().strftime("%Y-%m")

    with connect_db() as db:
        monthly_budget = get_budget(db)
        spent = db.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM expenses
            WHERE substr(expense_date, 1, 7) = ?
        """, (month,)).fetchone()["total"]

    spent = float(spent)

    return render_template(
        "templates.html",
        page="budget",
        budget=monthly_budget,
        spent=spent,
        remaining=monthly_budget - spent
    )


@app.route("/report")
def report():
    month = date.today().strftime("%Y-%m")

    with connect_db() as db:
        categories = db.execute("""
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE substr(expense_date, 1, 7) = ?
            GROUP BY category
            ORDER BY total DESC
        """, (month,)).fetchall()

    total = sum(float(row["total"]) for row in categories)

    return render_template(
        "templates.html",
        page="report",
        categories=categories,
        total=total
    )


@app.route("/style.css")
def style():
    return send_from_directory(
        str(Path(__file__).resolve().parent),
        "style.css",
        mimetype="text/css"
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
