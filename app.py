from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
import pandas as pd
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- DATABASE ----------------
if not os.path.exists("database"):
    os.makedirs("database")

conn = sqlite3.connect("database/database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS donors(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT,
email TEXT,
phone TEXT,
address TEXT,
blood_group TEXT,
availability TEXT,
password TEXT,
coins INTEGER DEFAULT 0,
last_donation TEXT
)
""")

conn.commit()
conn.close()

# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("home.html")

# ---------------- ABOUT ----------------
@app.route("/about")
def about():
    return render_template("about.html")

# ---------------- SIGNUP ----------------
@app.route("/signup")
def signup():
    return render_template("signup.html")

@app.route("/register", methods=["POST"])
def register():
    data = request.form

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO donors 
    (name,email,phone,address,blood_group,availability,password,coins)
    VALUES (?,?,?,?,?,?,?,?)
    """, (
        data["name"],
        data["email"],
        data["phone"],
        data["address"],
        data["blood_group"],
        "Available",
        data["password"],
        0
    ))

    conn.commit()
    conn.close()

    return redirect("/login")

# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database/database.db")
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM donors WHERE email=? AND password=?", (email,password))
        user = cursor.fetchone()

        conn.close()

        if user:
            session["user"] = email
            return redirect("/dashboard")
        else:
            return "Invalid Login"

    return render_template("login.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT name,availability,coins FROM donors WHERE email=?", (session["user"],))
    user = cursor.fetchone()

    conn.close()

    return render_template("dashboard.html",
                           name=user[0],
                           availability=user[1],
                           coins=user[2])

# ---------------- TOGGLE ----------------
@app.route("/toggle_status", methods=["POST"])
def toggle_status():

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT availability FROM donors WHERE email=?", (session["user"],))
    current = cursor.fetchone()[0]

    new = "Unavailable" if current=="Available" else "Available"

    cursor.execute("UPDATE donors SET availability=? WHERE email=?", (new,session["user"]))

    conn.commit()
    conn.close()

    return redirect("/dashboard")

# ---------------- PROFILE ----------------
from datetime import datetime, timedelta

@app.route("/profile")
def profile():

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT name,email,phone,address,blood_group,availability,coins,last_donation
    FROM donors WHERE email=?
    """,(session["user"],))

    user = cursor.fetchone()
    conn.close()

    # 🔥 Donation interval logic
    last_date = user[7]
    next_date = None
    days_left = None

    if last_date:
        last_date_obj = datetime.strptime(last_date, "%Y-%m-%d")
        next_date_obj = last_date_obj + timedelta(days=90)

        next_date = next_date_obj.strftime("%Y-%m-%d")

        days_left = (next_date_obj - datetime.now()).days

        if days_left < 0:
            days_left = 0

    return render_template("profile.html",
                           user=user,
                           next_date=next_date,
                           days_left=days_left)
# ---------------- DONORS ----------------
@app.route("/donors")
def donors():

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT name,blood_group,phone,address,availability FROM donors")
    data = cursor.fetchall()

    conn.close()

    return render_template("donors.html", donors=data)

# ---------------- REQUEST ----------------
@app.route("/request")
def request_page():
    return render_template("request.html")

@app.route("/emergency")
def emergency():
    return render_template("emergency.html")

@app.route("/regular")
def regular():
    return render_template("regular.html")

# ---------------- MATCH + RANK + REWARD ----------------
@app.route("/submit_request", methods=["POST"])
def submit_request():

    blood = request.form["blood_group"]
    location = request.form["location"].lower()
    req_type = request.form["type"]

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT name,blood_group,phone,address,availability FROM donors")
    donors = cursor.fetchall()

    conn.close()

    donors = [d for d in donors if blood.lower() in d[1].lower()]

    def score(d):
        s = 0
        if d[4] == "Available":
            s += 100
        if location in d[3].lower():
            s += 50
        if req_type == "Emergency":
            s += 20
        return s

    donors = sorted(donors, key=score, reverse=True)

    # Reward system
    if donors:
        top = donors[0]

        conn = sqlite3.connect("database/database.db")
        cursor = conn.cursor()

        cursor.execute("""
        UPDATE donors 
        SET coins=200, last_donation=?
        WHERE name=?
        """,(datetime.now().strftime("%Y-%m-%d"), top[0]))

        conn.commit()
        conn.close()

    return render_template("matched_donors.html",
                           donors=donors,
                           blood_group=blood,
                           type=req_type)

# ---------------- EXCEL IMPORT (ALL SHEETS FINAL) ----------------
@app.route("/upload_excel")
def upload_excel():

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    sheets = pd.read_excel("dataset.xlsx", sheet_name=None)

    total_inserted = 0

    for sheet_name, df in sheets.items():

        print("Processing:", sheet_name)

        if df.empty:
            continue

        df.columns = df.columns.str.strip().str.lower()

        for _, row in df.iterrows():
            try:
                name = str(row.get("name of donor", "")).strip()
                address = str(row.get("contract address", "")).strip()
                district = str(row.get("district", "")).strip()
                blood = str(row.get("blood group", "")).strip()
                phone = str(row.get("contactno", "")).strip()

                if not name or name.lower() in ["nan", "name of donor"]:
                    continue

                if not blood or blood.lower() == "nan":
                    continue

                location_parts = []
                if address and address.lower() != "nan":
                    location_parts.append(address)
                if district and district.lower() != "nan":
                    location_parts.append(district)

                location = ", ".join(location_parts)

                email = name.replace(" ", "").lower() + "@test.com"

                cursor.execute("SELECT * FROM donors WHERE email=?", (email,))
                if cursor.fetchone():
                    continue

                cursor.execute("""
                INSERT INTO donors 
                (name,email,phone,address,blood_group,availability,password,coins)
                VALUES (?,?,?,?,?,?,?,?)
                """, (name, email, phone, location, blood, "Available", "123", 0))

                total_inserted += 1

            except Exception as e:
                print("ERROR:", e)
                continue

    conn.commit()
    conn.close()

    return f"Inserted {total_inserted} donors from all sheets!"
# ---------------- FEEDBACK PAGE ----------------
@app.route("/feedback")
def feedback():
    return render_template("feedback.html")
# ---------------- SUBMIT FEEDBACK ----------------
@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():

    message = request.form["message"]

    # Handle optional image
    file = request.files.get("image")

    filename = None
    if file and file.filename != "":
        if not os.path.exists("static/uploads"):
            os.makedirs("static/uploads")

        filepath = os.path.join("static/uploads", file.filename)
        file.save(filepath)
        filename = file.filename

    # Save into database
    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS feedback(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT,
        image TEXT
    )
    """)

    cursor.execute("INSERT INTO feedback (message, image) VALUES (?,?)",
                   (message, filename))

    conn.commit()
    conn.close()

    return redirect("/dashboard")
# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)