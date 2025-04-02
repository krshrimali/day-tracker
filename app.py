import base64
import json
import os
import sqlite3
from datetime import date, datetime, timedelta

import pandas as pd
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Required for flash messages


@app.context_processor
def inject_now():
    return {"datetime": datetime}


def get_db_connection(db_name="data.db"):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    return conn


def get_user_db():
    username = session.get("username")
    if username:
        db_name = f"data_{username}.db"
    else:
        db_name = "data.db"
    return db_name


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_password = generate_password_hash(
            password, method="pbkdf2:sha256"
        )

        conn = get_db_connection()
        try:
            conn.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_password),
            )
            conn.commit()
            flash("Signup successful! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash(
                "Username already exists. Please choose a different one.",
                "danger",
            )
            return redirect(url_for("signup"))
        finally:
            conn.close()
    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["username"] = username
            # Ensure user database and tables exist
            db_name = f"data_{username}.db"
            if not os.path.exists(db_name):
                conn = get_db_connection(db_name)
                conn.execute(
                    "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT NOT NULL, ticket_link TEXT, time_spent REAL NOT NULL, comments TEXT, category TEXT, date TEXT NOT NULL)"
                )
                conn.execute(
                    "CREATE TABLE schedule (id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, activity TEXT NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL)"
                )
                conn.close()
            flash("Logged in successfully!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid credentials. Please try again.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out successfully!", "success")
    return redirect(url_for("login"))


@app.route("/")
def index():
    if "username" not in session:
        return redirect(url_for("login"))

    log_work_data = session.get("log_work_data", {})

    # Handle log work data transferred as base64 string (if present)
    log_work_data_b64 = request.args.get("logWorkData")
    if log_work_data_b64:
        log_work_data_str = base64.b64decode(log_work_data_b64).decode("utf-8")
        log_work_data = json.loads(log_work_data_str)
        session["log_work_data"] = log_work_data

    return render_template("index.html", log_work_data=log_work_data)


@app.route("/submit", methods=["POST"])
def submit():
    db_name = get_user_db()

    # Retrieve form data
    task = request.form.get("task")
    ticket_link = request.form.get("ticket_link")
    time_spent = request.form.get("time_spent")
    comments = request.form.get("comments")
    category = request.form.get("category")

    # Save to session to persist form data across navigations
    session["log_work_data"] = {
        "task": task,
        "ticket_link": ticket_link,
        "time_spent": time_spent,
        "comments": comments,
        "category": category,
    }

    if request.form.get("clear"):
        session.pop("log_work_data", None)
        flash("Form cleared!", "success")
        return redirect(url_for("index"))

    try:
        print("Writing to DB")
        conn = get_db_connection(db_name)
        conn.execute(
            "INSERT INTO tasks (task, ticket_link, time_spent, comments, category, date) VALUES (?, ?, ?, ?, ?, ?)",
            (task, ticket_link, time_spent, comments, category, date.today()),
        )
        conn.commit()
        conn.close()
        session.pop("log_work_data", None)
        flash("Task added successfully!", "success")
    except Exception as e:
        flash(
            "An error occurred while logging your work. Please try again.",
            "danger",
        )
        print(f"Error logging work: {e}")

    return redirect(url_for("index"))


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    db_name = get_user_db()
    conn = get_db_connection(db_name)
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (id,)).fetchone()

    if request.method == "POST":
        task = request.form.get("task")
        ticket_link = request.form.get("ticket_link")
        time_spent = request.form.get("time_spent")
        comments = request.form.get("comments")
        category = request.form.get("category")

        conn.execute(
            "UPDATE tasks SET task = ?, ticket_link = ?, time_spent = ?, comments = ?, category = ? WHERE id = ?",
            (task, ticket_link, time_spent, comments, category, id),
        )
        conn.commit()
        conn.close()

        flash("Task updated successfully!", "success")
        return redirect(url_for("summary"))

    conn.close()
    return render_template("edit.html", task=task)


@app.route("/delete/<int:id>", methods=["POST"])
def delete(id):
    db_name = get_user_db()
    conn = get_db_connection(db_name)
    conn.execute("DELETE FROM tasks WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash("Task deleted successfully!", "success")
    return redirect(url_for("summary"))


@app.route("/summary", methods=["GET", "POST"])
def summary():
    if "username" not in session:
        return redirect(url_for("login"))

    db_name = get_user_db()
    sort_column = request.args.get("sort", "date")
    sort_order = request.args.get("order", "asc")

    default_date = date.today()
    start_date = request.form.get("start_date", str(default_date))
    end_date = request.form.get("end_date", str(default_date))
    last_days = request.form.get("last_days")
    top_x = request.form.get("top_x")
    show_all = request.form.get("show_all")

    query = "SELECT * FROM tasks"

    if show_all:
        query += " WHERE 1=1"
    elif last_days:
        end_date = default_date
        start_date = end_date - timedelta(days=int(last_days) - 1)
        query += f' WHERE date BETWEEN "{start_date}" AND "{end_date}"'
    elif start_date and end_date:
        query += f' WHERE date BETWEEN "{start_date}" AND "{end_date}"'
    else:
        query += f' WHERE date = "{default_date}"'

    if sort_column:
        query += f" ORDER BY {sort_column} {sort_order}"

    if top_x:
        query += f" LIMIT {top_x}"
    else:
        query += " LIMIT 10"

    conn = get_db_connection(db_name)
    tasks = conn.execute(query).fetchall()
    conn.close()

    return render_template(
        "summary.html",
        tasks=tasks,
        start_date=start_date,
        end_date=end_date,
        last_days=last_days,
        top_x=top_x,
        show_all=show_all,
    )


@app.route("/export")
def export_summary():
    db_name = get_user_db()
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    last_days = request.args.get("last_days", "")

    if last_days:
        end_date = date.today()
        start_date = end_date - timedelta(days=int(last_days) - 1)
    elif not (start_date and end_date):
        end_date = date.today()
        start_date = end_date - timedelta(days=6)

    conn = get_db_connection(db_name)
    query = f'SELECT * FROM tasks WHERE date BETWEEN "{start_date}" AND "{end_date}"'
    tasks = conn.execute(query).fetchall()
    conn.close()

    df = pd.DataFrame([dict(row) for row in tasks])
    df.to_excel("summary.xlsx", index=False)

    return send_file("summary.xlsx", as_attachment=True)


@app.route("/grouped_summary", methods=["POST"])
def grouped_summary():
    db_name = get_user_db()
    data = request.get_json()
    group_by = data.get("group_by")
    last_days = data.get("last_days")
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    top_x = data.get("top_x")

    query = f"SELECT {group_by} AS group_item, SUM(time_spent) as total_time FROM tasks"

    conditions = []
    if last_days:
        end_date = date.today()
        start_date = end_date - timedelta(days=int(last_days) - 1)
        conditions.append(f'date BETWEEN "{start_date}" AND "{end_date}"')
    elif start_date and end_date:
        conditions.append(f'date BETWEEN "{start_date}" AND "{end_date}"')

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += f" GROUP BY {group_by}"
    if top_x:
        query += f" ORDER BY total_time DESC LIMIT {top_x}"

    conn = get_db_connection(db_name)
    tasks = conn.execute(query).fetchall()
    conn.close()

    return jsonify(
        [
            {"group_item": row["group_item"], "total_time": row["total_time"]}
            for row in tasks
        ]
    )


@app.route("/chart_data")
def chart_data():
    db_name = get_user_db()
    conn = get_db_connection(db_name)
    tasks_by_date = conn.execute(
        "SELECT date, SUM(time_spent) as total_time FROM tasks GROUP BY date"
    ).fetchall()
    tasks_by_ticket = conn.execute(
        "SELECT ticket_link AS group_item, SUM(time_spent) as total_time FROM tasks GROUP BY ticket_link"
    ).fetchall()
    tasks_by_category = conn.execute(
        "SELECT category AS group_item, SUM(time_spent) as total_time FROM tasks GROUP BY category"
    ).fetchall()

    data = {
        "dates": [row["date"] for row in tasks_by_date],
        "times": [row["total_time"] for row in tasks_by_date],
        "tickets": [
            {"label": row["group_item"], "time": row["total_time"]}
            for row in tasks_by_ticket
        ],
        "categories": [
            {"label": row["group_item"], "time": row["total_time"]}
            for row in tasks_by_category
        ],
    }

    conn.close()
    return jsonify(data)


@app.route("/pie_chart_data", methods=["GET"])
def pie_chart_data():
    db_name = get_user_db()
    group_by = request.args.get("group_by", "category")
    last_days = request.args.get("last_days")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    query = f"SELECT {group_by} AS group_item, SUM(time_spent) AS total_time FROM tasks"

    # Build the condition based on the presence of `last_days` or `date range`
    condition = []
    if last_days:
        end_date = date.today()
        start_date = end_date - timedelta(days=int(last_days) - 1)
        condition.append(f"date BETWEEN '{start_date}' AND '{end_date}'")
    elif start_date and end_date:
        condition.append(f"date BETWEEN '{start_date}' AND '{end_date}'")

    if condition:
        query += f" WHERE {' AND '.join(condition)}"

    query += f" GROUP BY {group_by}"

    conn = get_db_connection(db_name)
    tasks = conn.execute(query).fetchall()
    conn.close()

    data = {
        "groups": [task["group_item"] for task in tasks],
        "times": [task["total_time"] for task in tasks],
    }

    return jsonify(data)


@app.route("/bar_chart_page")
def bar_chart_page():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("bar_chart.html")


@app.route("/pie_chart_page")
def pie_chart_page():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("pie_chart.html")


@app.route("/schedule", methods=["GET", "POST"])
def schedule():
    if "username" not in session:
        return redirect(url_for("login"))

    db_name = get_user_db()
    if request.method == "POST":
        date = request.form.get("date")
        activities = request.form.getlist("activity")
        start_times = request.form.getlist("start_time")
        end_times = request.form.getlist("end_time")
        links = request.form.getlist("link")
        categories = request.form.getlist("category")
        moved_to_log_work_flags = [
            int(x) for x in request.form.getlist("moved_to_log_work")
        ]

        conn = get_db_connection(db_name)
        conn.execute("DELETE FROM schedule WHERE date = ?", (date,))

        for (
            activity,
            start_time,
            end_time,
            link,
            category,
            moved_to_log_work,
        ) in zip(
            activities,
            start_times,
            end_times,
            links,
            categories,
            moved_to_log_work_flags,
        ):
            conn.execute(
                "INSERT INTO schedule (date, activity, start_time, end_time, link, category, moved_to_log_work) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    date,
                    activity,
                    start_time,
                    end_time,
                    link,
                    category,
                    moved_to_log_work,
                ),
            )
        conn.commit()
        conn.close()

        flash("Schedule updated successfully!", "success")
        return redirect(url_for("schedule", date=date))

    date = request.args.get("date", str(datetime.today().date()))
    conn = get_db_connection(db_name)
    schedule = conn.execute(
        "SELECT * FROM schedule WHERE date = ?", (date,)
    ).fetchall()
    conn.close()
    return render_template("schedule.html", schedule=schedule, date=date)


@app.route("/schedule_summary", methods=["GET", "POST"])
def schedule_summary():
    if "username" not in session:
        return redirect(url_for("login"))

    db_name = get_user_db()
    date_str = request.form.get("date", str(datetime.today().date()))
    activities = []

    if request.method == "POST":
        conn = get_db_connection(db_name)
        schedule = conn.execute(
            "SELECT * FROM schedule WHERE date = ?", (date_str,)
        ).fetchall()
        conn.close()

        for entry in schedule:
            start_time = datetime.strptime(
                f"{date_str} {entry['start_time']}", "%Y-%m-%d %H:%M"
            )
            end_time = datetime.strptime(
                f"{date_str} {entry['end_time']}", "%Y-%m-%d %H:%M"
            )
            time_spent = (end_time - start_time).total_seconds() / 3600.0
            activities.append(
                {
                    "activity": entry["activity"],
                    "start_time": entry["start_time"],
                    "end_time": entry["end_time"],
                    "time_spent": time_spent,
                }
            )

    return render_template(
        "schedule_summary.html", activities=activities, date=date_str
    )


@app.route("/move_entry", methods=["POST"])
def move_entry():
    if "username" not in session:
        return redirect(url_for("login"))

    entry_id = request.form.get("entry_id")
    if not entry_id:
        return jsonify({"error": "Invalid Entry ID"}), 400

    db_name = get_user_db()

    conn = get_db_connection(db_name)
    conn.execute(
        "UPDATE schedule SET moved_to_log_work = 1 WHERE id = ?", (entry_id,)
    )
    conn.commit()
    conn.close()
    print("Called")

    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=9876)
