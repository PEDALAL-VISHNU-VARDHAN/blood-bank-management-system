from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
from datetime import datetime, timedelta
from flask import flash
from datetime import datetime
app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- DATABASE ----------------
if not os.path.exists("database"):
    os.makedirs("database")

conn = sqlite3.connect("database/database.db")
cursor = conn.cursor()

# Donor Table
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
last_donation TEXT,
report TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS feedback(
id INTEGER PRIMARY KEY AUTOINCREMENT,
user_email TEXT,
message TEXT,
image TEXT,
date TEXT
)
""")
# Donation History
cursor.execute("""
CREATE TABLE IF NOT EXISTS donations(
id INTEGER PRIMARY KEY AUTOINCREMENT,
donor_name TEXT,
date TEXT,
status TEXT
)
""")

# Admin Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS admin(
id INTEGER PRIMARY KEY AUTOINCREMENT,
username TEXT,
password TEXT
)
""")

cursor.execute("INSERT OR IGNORE INTO admin VALUES (1,'admin','admin123')")

# System Settings
cursor.execute("""
CREATE TABLE IF NOT EXISTS system_settings(
id INTEGER PRIMARY KEY,
coin_per_donation INTEGER,
interval_days INTEGER
)
""")

cursor.execute("INSERT OR IGNORE INTO system_settings VALUES (1,200,90)")

# Health Reports
cursor.execute("""
CREATE TABLE IF NOT EXISTS health_reports(
id INTEGER PRIMARY KEY AUTOINCREMENT,
donor_name TEXT,
hemoglobin REAL,
report_date TEXT,
status TEXT
)
""")

conn.commit()
conn.close()

# ---------------- DB UPGRADE (NEW FEATURES) ----------------
try:
    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("ALTER TABLE donors ADD COLUMN custom_interval INTEGER DEFAULT 0")
    cursor.execute("ALTER TABLE donors ADD COLUMN health_status TEXT DEFAULT 'Pending'")
    cursor.execute("ALTER TABLE donors ADD COLUMN next_eligible TEXT")
    conn.commit()
    conn.close()
except:
    pass

# ---------------- HELPER ----------------
def get_settings():
    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT coin_per_donation, interval_days FROM system_settings WHERE id=1")
    data = cursor.fetchone()
    conn.close()
    return data
#-----------is eligible function------------
def is_eligible(last_donation, email=None):

    coin_value, default_interval = get_settings()

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT custom_interval, next_eligible 
    FROM donors WHERE email=?
    """, (email,))
    
    row = cursor.fetchone()
    conn.close()

    custom_interval = row[0] if row else 0
    next_eligible = row[1] if row else None

    # 🔥 PRIORITY 1 → ADMIN CONTROL
    if next_eligible:
        next_date = datetime.strptime(next_eligible, "%Y-%m-%d")
        return datetime.now() >= next_date

    # 🔥 PRIORITY 2 → CUSTOM INTERVAL
    interval = custom_interval if custom_interval > 0 else default_interval

    if not last_donation:
        return True

    last = datetime.strptime(last_donation, "%Y-%m-%d")
    return datetime.now() >= last + timedelta(days=interval)
# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("home.html")

# ---------------- ABOUT ----------------
@app.route("/about")
def about():
    return render_template("about.html")
#-----------------ADMIN home route------------
@app.route("/admin_home")
def admin_home():

    if "admin" not in session:
        return redirect("/admin_login")

    return render_template("admin_home.html")
# ---------------- ADMIN LOGIN ----------------
@app.route("/admin_login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = sqlite3.connect("database/database.db")
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM admin WHERE username=? AND password=?", (u,p))
        admin = cursor.fetchone()
        conn.close()

        if admin:
            session["admin"] = u
            return redirect("/admin_home")

        return "Invalid Admin Login ❌"

    return render_template("admin_login.html")

# ---------------- ADMIN DASHBOARD ----------------
@app.route("/admin_dashboard")
def admin_dashboard():

    if "admin" not in session:
        return redirect("/admin_login")

    search = request.args.get("search", "")

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    if search:
        if search:
         cursor.execute("""
            SELECT name,phone,blood_group,coins,last_donation,health_status 
            FROM donors WHERE name LIKE ?
          """, ('%' + search + '%',))
    else:
        cursor.execute("""
        SELECT name,phone,blood_group,coins,last_donation,health_status FROM donors
        """)

    donors = cursor.fetchall()

    cursor.execute("SELECT coin_per_donation,interval_days FROM system_settings WHERE id=1")
    settings = cursor.fetchone()

    conn.close()

    return render_template("admin_dashboard.html", donors=donors, settings=settings, search=search)

# ---------------- UPDATE SETTINGS ----------------
@app.route("/update_settings", methods=["POST"])
def update_settings():
    coins = request.form["coins"]
    interval = request.form["interval"]

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE system_settings SET coin_per_donation=?,interval_days=? WHERE id=1",(coins,interval))

    conn.commit()
    conn.close()
    return redirect("/admin_dashboard")
# ---------------- ADMIN VERIFY ----------------
@app.route("/admin_verify/<phone>", methods=["POST"])
def admin_verify(phone):
    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT coin_per_donation FROM system_settings WHERE id=1")
    coins = cursor.fetchone()[0]

    # calculate next eligible date automatically
    interval_days = get_settings()[1]
    next_date = datetime.now() + timedelta(days=interval_days)

    cursor.execute("""
        UPDATE donors 
        SET coins = coins + ?, 
            last_donation = ?, 
            availability = 'Unavailable',
            next_eligible = ?
        WHERE phone = ?
        """, (coins, today, next_date.strftime("%Y-%m-%d"), phone))

    conn.commit()
    conn.close()

    return redirect("/admin_dashboard")

# ---------------- HEALTH VERIFY ----------------
@app.route("/verify_health/<donor_phone>/<status>", methods=["POST"])
def verify_health(donor_phone, status):

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE donors SET health_status=? WHERE phone=?", (status, donor_phone))

    conn.commit()
    conn.close()

    return redirect("/health_dashboard")
#------------------HEALTH DASHBOARD-------------
@app.route("/health_dashboard")
def health_dashboard():

    if "admin" not in session:
        return redirect("/admin_login")

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
SELECT name,phone,health_status,report 
FROM donors
""")
    donors = cursor.fetchall()

    conn.close()

    return render_template("health_dashboard.html", donors=donors)
# ---------------- COIN CONTROL ----------------
@app.route("/update_coins/<phone>")
def update_coins(donor_phone):

    action = request.form["action"]
    amount = int(request.form["amount"])

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    if action == "add":
        cursor.execute("UPDATE donors SET coins = coins + ? WHERE name=?", (amount, donor_name))
    else:
        cursor.execute("UPDATE donors SET coins = coins - ? WHERE name=?", (amount, donor_name))

    conn.commit()
    conn.close()

    return redirect("/admin_dashboard")

# ---------------- INTERVAL CONTROL ----------------
@app.route("/update_interval/<donor_phone>", methods=["POST"])
def update_interval(donor_phone):

    days = int(request.form["days"])

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("UPDATE donors SET custom_interval=? WHERE name=?", (days, donor_name))

    conn.commit()
    conn.close()

    return redirect("/admin_dashboard")
# ---------------- ADMIN NEXT DATE CONTROL ---------------- 
@app.route("/set_next_date/<phone>", methods=["POST"])
def set_next_date(phone):

    date = request.form["next_date"]

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE donors SET next_eligible=? WHERE phone=?
    """, (date, phone))

    conn.commit()
    conn.close()

    return redirect("/admin_dashboard")
# ---------------- SIGNUP ----------------
@app.route("/signup")
def signup():
    return render_template("signup.html")


@app.route("/register", methods=["GET","POST"])
def register():

    # =========================
    # OPEN SIGNUP PAGE
    # =========================

    if request.method == "GET":

        return render_template("signup.html")

    # =========================
    # FORM DATA
    # =========================

    data = request.form

    name = data.get("name")
    email = data.get("email")
    phone = data.get("phone")
    address = data.get("address")

    blood_group = data.get("blood_group")

    password = data.get("password")

    confirm_password = data.get("confirm_password")

    age = int(data.get("age"))

    weight = int(data.get("weight"))

    gender = data.get("gender")

    report_date = data.get("report_date")

    report = request.files["report"]

    # =========================
    # VALID BLOOD GROUPS
    # =========================

    valid_blood_groups = [
        "A+","A-",
        "B+","B-",
        "AB+","AB-",
        "O+","O-"
    ]

    # =========================
    # NAME VALIDATION
    # =========================

    if len(name) < 3:

        flash("Name must contain at least 3 characters")

        return redirect("/register")

    # =========================
    # PHONE VALIDATION
    # =========================

    if len(phone) != 10 or not phone.isdigit():

        flash("Phone number must contain 10 digits")

        return redirect("/register")

    # =========================
    # AGE VALIDATION
    # =========================

    if age < 18 or age > 60:

        flash("Donor age must be between 18 and 60 years")

        return redirect("/register")

    # =========================
    # GENDER VALIDATION
    # =========================

    if gender not in ["Male", "Female", "Other"]:

        flash("Please select valid gender")

        return redirect("/register")

    # =========================
    # WEIGHT VALIDATION
    # =========================

    if weight < 50:

        flash("Weight must be above 50kg")

        return redirect("/register")

    # =========================
    # PASSWORD VALIDATION
    # =========================

    if len(password) < 6:

        flash("Password must contain at least 6 characters")

        return redirect("/register")

    # =========================
    # PASSWORD MATCH CHECK
    # =========================

    if password != confirm_password:

        flash("Passwords do not match")

        return redirect("/register")

    # =========================
    # BLOOD GROUP VALIDATION
    # =========================

    if blood_group not in valid_blood_groups:

        flash("Invalid blood group selected")

        return redirect("/register")

    # =========================
    # REPORT VALIDATION
    # =========================

    if report.filename == "":

        flash("Please upload blood report")

        return redirect("/register")

    # =========================
    # REPORT DATE VALIDATION
    # =========================

    today = datetime.today()

    report_date_obj = datetime.strptime(
        report_date,
        "%Y-%m-%d"
    )

    difference = (today - report_date_obj).days

    if difference > 10:

        flash("Blood report must be within 10 days")

        return redirect("/register")

    # =========================
    # ALLOWED FILE TYPES
    # =========================

    allowed_extensions = [
        ".png",
        ".jpg",
        ".jpeg",
        ".pdf"
    ]

    file_ext = os.path.splitext(
        report.filename
    )[1].lower()

    if file_ext not in allowed_extensions:

        flash("Only PNG, JPG, JPEG and PDF files allowed")

        return redirect("/register")

    # =========================
    # CREATE UPLOAD FOLDER
    # =========================

    if not os.path.exists("static/uploads"):

        os.makedirs("static/uploads")

    # =========================
    # SAVE FILE
    # =========================

    filename = report.filename

    report.save(
        "static/uploads/" + filename
    )

    # =========================
    # DATABASE CONNECTION
    # =========================

    conn = sqlite3.connect(
        "database/database.db"
    )

    cursor = conn.cursor()

    # =========================
    # EMAIL CHECK
    # =========================

    cursor.execute("""
    SELECT * FROM donors
    WHERE email=?
    """, (email,))

    existing_email = cursor.fetchone()

    if existing_email:

        conn.close()

        flash("Email already registered")

        return redirect("/register")

    # =========================
    # PHONE CHECK
    # =========================

    cursor.execute("""
    SELECT * FROM donors
    WHERE phone=?
    """, (phone,))

    existing_phone = cursor.fetchone()

    if existing_phone:

        conn.close()

        flash("Phone number already registered")

        return redirect("/register")

    # =========================
    # INSERT DONOR
    # =========================

    cursor.execute("""
    INSERT INTO donors (
    name,
    email,
    phone,
    address,
    blood_group,
    availability,
    password,
    coins,
    report,
    health_status
    )
    VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        name,
        email,
        phone,
        address,
        blood_group,
        "Unavailable",
        password,
        0,
        filename,
        "Pending"
    ))

    conn.commit()

    conn.close()

    # =========================
    # SUCCESS MESSAGE
    # =========================

    flash(
    "Registration successful. Waiting for admin verification"
    )

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

    return render_template("login.html")

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
     SELECT name,availability,coins,last_donation,next_eligible,health_status 
     FROM donors WHERE email=?
     """, (session["user"],))
    user = cursor.fetchone()
    eligible = is_eligible(user[3], session["user"])

    if eligible:
      if user[1] == "Available":
        status = "Available"
      else:
        status = "Eligible"
    else:
     status = "Not Eligible"

    return render_template("dashboard.html",
                       name=user[0],
                       availability=status,
                       coins=user[2],
                       health_status=user[5]) 
# ---------------- TOGGLE ----------------
@app.route("/toggle_status", methods=["POST"])
def toggle_status():

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT availability,last_donation,next_eligible 
    FROM donors WHERE email=?
    """, (session["user"],))

    data = cursor.fetchone()

    if not is_eligible(data[1], session["user"]):
        return "Not eligible"

    new = "Unavailable" if data[0] == "Available" else "Available"

    cursor.execute("""
    UPDATE donors SET availability=? WHERE email=?
    """, (new, session["user"]))

    conn.commit()
    conn.close()

    return redirect("/dashboard")
# ---------------- MATCH ----------------
@app.route("/submit_request", methods=["POST"])
def submit_request():

    blood = request.form["blood_group"]
    location = request.form["location"].lower()
    req_type = request.form["type"]

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT name,blood_group,phone,address,availability,last_donation FROM donors")
    donors = cursor.fetchall()
    conn.close()

    valid = []

    for d in donors:
        if blood.lower() not in d[1].lower():
            continue
        if d[4]=="Available" and is_eligible(d[5], d[0]):
            valid.append(d)

    donors = sorted(valid, key=lambda d: location in d[3].lower(), reverse=True)

    return render_template("matched_donors.html", donors=donors, blood_group=blood, type=req_type)

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
# ---------------- PROFILE ----------------
@app.route("/profile")
def profile():

    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT name,email,phone,address,blood_group,availability,coins,last_donation
    FROM donors WHERE email=?
    """,(session["user"],))

    user = cursor.fetchone()
    conn.close()

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT next_eligible FROM donors WHERE email=?
    """, (session["user"],))

    data = cursor.fetchone()
    conn.close()

    next_date = data[0]
    days_left = None

    if next_date:
        next_obj = datetime.strptime(next_date, "%Y-%m-%d")
        days_left = (next_obj - datetime.now()).days
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


# ---------------- FEEDBACK ----------------
@app.route("/feedback")
def feedback():
    return render_template("feedback.html")

@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():

    if "user" not in session:
        return redirect("/login")

    message = request.form["message"]

    image = request.files["image"]

    filename = ""

    if image and image.filename != "":

        if not os.path.exists("static/uploads"):
            os.makedirs("static/uploads")

        filename = image.filename

        image.save("static/uploads/" + filename)

    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO feedback(user_email,message,image,date)
    VALUES(?,?,?,?)
    """, (
        session["user"],
        message,
        filename,
        today
    ))

    conn.commit()
    conn.close()

    return redirect("/feedback")
# ---------------- TEMP DB FIX ROUTE ----------------
@app.route("/fix_db")
def fix_db():
    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE donors ADD COLUMN next_eligible TEXT")
        msg = "Column added successfully ✅"
    except Exception as e:
        msg = f"Already exists or error: {e}"

    conn.commit()
    conn.close()

    return msg  
#-----------------admin_report--------------
@app.route("/add_report_column")
def add_report_column():

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE donors ADD COLUMN report TEXT")
        msg = "Report column added successfully"

    except Exception as e:
        msg = str(e)

    conn.commit()
    conn.close()

    return msg
#----------------admin feedback page--------------
@app.route("/admin_feedback")
def admin_feedback():

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("""
    SELECT user_email,message,image,date
    FROM feedback
    ORDER BY id DESC
    """)

    feedbacks = cursor.fetchall()

    conn.close()

    return render_template(
        "admin_feedback.html",
        feedbacks=feedbacks
    )
@app.route("/reset_feedback_table")
def reset_feedback_table():

    conn = sqlite3.connect("database/database.db")
    cursor = conn.cursor()

    cursor.execute("DROP TABLE IF EXISTS feedback")

    cursor.execute("""
    CREATE TABLE feedback(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_email TEXT,
    message TEXT,
    image TEXT,
    date TEXT
    )
    """)

    conn.commit()
    conn.close()

    return "Feedback table recreated successfully"
# ---------------- ADMIN LOGOUT ----------------
@app.route("/admin_logout")
def admin_logout():

    session.clear()

    return redirect("/")
# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)