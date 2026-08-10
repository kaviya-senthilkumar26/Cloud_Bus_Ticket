from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import re

app = Flask(__name__)
import os

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "dev-secret-key-change-in-production"
)

DATABASE = "bus_pass.db"
BUS_SEAT_COUNT = 50


# ================= DATABASE =================

def get_db():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS buses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bus_number TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            destination TEXT NOT NULL,
            fare REAL NOT NULL,
            total_seats INTEGER NOT NULL DEFAULT 50,
            available_seats INTEGER NOT NULL DEFAULT 50
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            bus_id INTEGER NOT NULL,
            passenger_name TEXT NOT NULL,
            seats INTEGER NOT NULL,
            seat_numbers TEXT DEFAULT '',
            total_fare REAL NOT NULL,
            booking_status TEXT DEFAULT 'Confirmed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(bus_id) REFERENCES buses(id)
        )
    """)

    # Migrate older databases that do not have seat_numbers/created_at.
    booking_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(bookings)").fetchall()
    }

    if "seat_numbers" not in booking_columns:
        conn.execute(
            "ALTER TABLE bookings ADD COLUMN seat_numbers TEXT DEFAULT ''"
        )

    if "created_at" not in booking_columns:
        conn.execute(
            "ALTER TABLE bookings ADD COLUMN created_at TIMESTAMP"
        )

    # Standardize all buses to exactly 50 seats.
    conn.execute("""
        UPDATE buses
        SET total_seats = 50,
            available_seats = CASE
                WHEN available_seats > 50 THEN 50
                WHEN available_seats < 0 THEN 0
                ELSE available_seats
            END
    """)

    count = conn.execute("SELECT COUNT(*) FROM buses").fetchone()[0]

    if count == 0:
        buses = [
            ("CB001", "Chennai", "Coimbatore", 450, 50, 50),
            ("CB002", "Chennai", "Madurai", 350, 50, 50),
            ("CB003", "Chennai", "Bangalore", 500, 50, 50),
            ("CB004", "Madurai", "Coimbatore", 300, 50, 50),
            ("CB005", "Chennai", "Salem", 250, 50, 50)
        ]

        conn.executemany("""
            INSERT INTO buses
            (bus_number, source, destination, fare, total_seats, available_seats)
            VALUES (?, ?, ?, ?, ?, ?)
        """, buses)

    conn.commit()
    conn.close()


# ================= HELPERS =================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))

        if session.get("role") != "admin":
            flash("Administrator access required.", "danger")
            return redirect(url_for("buses"))

        return f(*args, **kwargs)
    return decorated


def get_booked_seats(conn, bus_id):
    rows = conn.execute("""
        SELECT seat_numbers
        FROM bookings
        WHERE bus_id = ?
        AND booking_status = 'Confirmed'
    """, (bus_id,)).fetchall()

    booked = set()

    for row in rows:
        value = row["seat_numbers"] or ""
        for item in value.split(","):
            item = item.strip()
            if item.isdigit():
                number = int(item)
                if 1 <= number <= BUS_SEAT_COUNT:
                    booked.add(number)

    return booked


def refresh_available_seats(conn, bus_id):
    booked_count = len(get_booked_seats(conn, bus_id))
    available = max(0, BUS_SEAT_COUNT - booked_count)

    conn.execute("""
        UPDATE buses
        SET total_seats = 50,
            available_seats = ?
        WHERE id = ?
    """, (available, bus_id))

    return available


def parse_selected_seats(value):
    if not value:
        return []

    result = []

    for item in value.split(","):
        item = item.strip()
        if not item:
            continue

        if not item.isdigit():
            continue

        number = int(item)

        if 1 <= number <= BUS_SEAT_COUNT:
            result.append(number)

    return sorted(set(result))


# ================= HOME =================

@app.route("/")
def home():
    return render_template("index.html")


# ================= REGISTER =================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # Required fields
        if not name or not email or not password:
            flash(
                "All fields are required.",
                "danger"
            )
            return redirect(url_for("register"))

        # Name validation
        if (
            len(name) < 2
            or len(name) > 100
            or not re.fullmatch(r"[A-Za-z ]+", name)
        ):
            flash(
                "Please enter a valid name.",
                "danger"
            )
            return redirect(url_for("register"))

        # Email validation
        if not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            email
        ):
            flash(
                "Please enter a valid email address.",
                "danger"
            )
            return redirect(url_for("register"))

        # Password validation
        if len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "danger"
            )
            return redirect(url_for("register"))

        # Create account
        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO users
                (name, email, password)
                VALUES (?, ?, ?)
            """, (
                name,
                email,
                generate_password_hash(password)
            ))

            conn.commit()

            flash(
                "Account created successfully!",
                "success"
            )

            return redirect(
                url_for("login")
            )

        except sqlite3.IntegrityError:

            flash(
                "Email already registered.",
                "danger"
            )

        finally:

            conn.close()

    return render_template("register.html")

# ================= LOGIN =================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["role"] = user["role"]

            flash("Login successful!", "success")

            if user["role"] == "admin":
                return redirect(url_for("admin"))

            return redirect(url_for("buses"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


# ================= LOGOUT =================

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


# ================= BUS SEARCH =================

@app.route("/buses")
@login_required
def buses():
    source = request.args.get("source", "").strip()
    destination = request.args.get("destination", "").strip()

    conn = get_db()

    # Keep availability synchronized with confirmed seat records.
    all_bus_ids = conn.execute("SELECT id FROM buses").fetchall()
    for row in all_bus_ids:
        refresh_available_seats(conn, row["id"])
    conn.commit()

    if source and destination:
        buses = conn.execute("""
            SELECT *
            FROM buses
            WHERE LOWER(source) = LOWER(?)
            AND LOWER(destination) = LOWER(?)
            ORDER BY bus_number
        """, (source, destination)).fetchall()
    elif source:
        buses = conn.execute("""
            SELECT *
            FROM buses
            WHERE LOWER(source) = LOWER(?)
            ORDER BY bus_number
        """, (source,)).fetchall()
    elif destination:
        buses = conn.execute("""
            SELECT *
            FROM buses
            WHERE LOWER(destination) = LOWER(?)
            ORDER BY bus_number
        """, (destination,)).fetchall()
    else:
        buses = conn.execute("""
            SELECT *
            FROM buses
            ORDER BY bus_number
        """).fetchall()

    conn.close()

    return render_template(
        "buses.html",
        buses=buses,
        source=source,
        destination=destination
    )


# ================= BOOK =================

@app.route("/book/<int:bus_id>", methods=["GET", "POST"])
@login_required
def book(bus_id):
    conn = get_db()

    bus = conn.execute("""
        SELECT *
        FROM buses
        WHERE id = ?
    """, (bus_id,)).fetchone()

    if not bus:
        conn.close()
        flash("Bus not found.", "danger")
        return redirect(url_for("buses"))

    booked_seats = get_booked_seats(conn, bus_id)
    available_seats = BUS_SEAT_COUNT - len(booked_seats)

    conn.execute("""
        UPDATE buses
        SET total_seats = 50, available_seats = ?
        WHERE id = ?
    """, (available_seats, bus_id))
    conn.commit()

    if request.method == "POST":
        passenger_name = request.form.get("passenger_name", "").strip()
        selected_value = request.form.get("selected_seats", "")

        selected_seats = parse_selected_seats(selected_value)

        if not passenger_name:
            conn.close()
            flash("Passenger name is required.", "danger")
            return redirect(url_for("book", bus_id=bus_id))

        if not re.fullmatch(r"[A-Za-z .'-]+", passenger_name):
            conn.close()
            flash("Please enter a valid passenger name.", "danger")
            return redirect(url_for("book", bus_id=bus_id))

        if not selected_seats:
            conn.close()
            flash("Please select at least one seat.", "danger")
            return redirect(url_for("book", bus_id=bus_id))

        # Lock the database transaction before checking seats.
        try:
            conn.execute("BEGIN IMMEDIATE")

            current_booked = get_booked_seats(conn, bus_id)
            unavailable = set(selected_seats) & current_booked

            if unavailable:
                conn.rollback()
                conn.close()
                seats_text = ", ".join(f"{n:02d}" for n in sorted(unavailable))
                flash(
                    f"Seat(s) {seats_text} were just booked. Please select different seats.",
                    "danger"
                )
                return redirect(url_for("book", bus_id=bus_id))

            seat_count = len(selected_seats)
            total_fare = bus["fare"] * seat_count
            seat_text = ",".join(str(n) for n in selected_seats)

            cursor = conn.execute("""
                INSERT INTO bookings
                (user_id, bus_id, passenger_name, seats, seat_numbers, total_fare, booking_status)
                VALUES (?, ?, ?, ?, ?, ?, 'Confirmed')
            """, (
                session["user_id"],
                bus_id,
                passenger_name,
                seat_count,
                seat_text,
                total_fare
            ))

            booking_id = cursor.lastrowid

            refresh_available_seats(conn, bus_id)
            conn.commit()
            conn.close()

            return redirect(url_for("confirmation", booking_id=booking_id))

        except sqlite3.Error:
            conn.rollback()
            conn.close()
            flash("Booking could not be completed. Please try again.", "danger")
            return redirect(url_for("book", bus_id=bus_id))

    seat_rows = [
        {
            "seat_number": number,
            "booking_id": None if number not in booked_seats else True
        }
        for number in range(1, BUS_SEAT_COUNT + 1)
    ]

    conn.close()

    return render_template(
        "booking.html",
        bus=bus,
        seat_rows=seat_rows,
        booked_seats=sorted(booked_seats)
    )


# ================= CONFIRMATION =================

@app.route("/confirmation/<int:booking_id>")
@login_required
def confirmation(booking_id):

    conn = get_db()

    booking = conn.execute("""
        SELECT
            bookings.*,
            buses.bus_number,
            buses.source,
            buses.destination,
            buses.fare
        FROM bookings
        JOIN buses
        ON bookings.bus_id = buses.id
        WHERE bookings.id = ?
        AND bookings.user_id = ?
    """, (
        booking_id,
        session["user_id"]
    )).fetchone()

    conn.close()

    if not booking:

        flash(
            "Booking not found.",
            "danger"
        )

        return redirect(
            url_for("my_bookings")
        )

    return render_template(
        "confirmation.html",
        booking=booking
    )

# ================= MY BOOKINGS =================

@app.route("/my-bookings")
@login_required
def my_bookings():
    conn = get_db()

    bookings = conn.execute("""
        SELECT
            bookings.*,
            buses.bus_number,
            buses.source,
            buses.destination
        FROM bookings
        JOIN buses ON bookings.bus_id = buses.id
        WHERE bookings.user_id = ?
        ORDER BY bookings.id DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template("my_bookings.html", bookings=bookings)


# ================= CANCEL BOOKING =================

@app.route("/cancel/<int:booking_id>", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    conn = get_db()

    booking = conn.execute("""
        SELECT *
        FROM bookings
        WHERE id = ?
        AND user_id = ?
        AND booking_status = 'Confirmed'
    """, (booking_id, session["user_id"])).fetchone()

    if not booking:
        conn.close()
        flash("Booking cannot be cancelled.", "danger")
        return redirect(url_for("my_bookings"))

    conn.execute("""
        UPDATE bookings
        SET booking_status = 'Cancelled'
        WHERE id = ?
    """, (booking_id,))

    refresh_available_seats(conn, booking["bus_id"])

    conn.commit()
    conn.close()

    flash(
        "Booking cancelled successfully. Your seats are available again.",
        "success"
    )

    return redirect(url_for("my_bookings"))


# ================= ADMIN DASHBOARD =================

@app.route("/admin")
@admin_required
def admin():
    conn = get_db()

    bus_rows = conn.execute("SELECT id FROM buses").fetchall()
    for row in bus_rows:
        refresh_available_seats(conn, row["id"])
    conn.commit()

    total_users = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    total_buses = conn.execute(
        "SELECT COUNT(*) FROM buses"
    ).fetchone()[0]

    total_bookings = conn.execute(
        "SELECT COUNT(*) FROM bookings"
    ).fetchone()[0]

    active_bookings = conn.execute("""
        SELECT COUNT(*)
        FROM bookings
        WHERE booking_status = 'Confirmed'
    """).fetchone()[0]

    revenue = conn.execute("""
        SELECT COALESCE(SUM(total_fare), 0)
        FROM bookings
        WHERE booking_status = 'Confirmed'
    """).fetchone()[0]

    buses = conn.execute("""
        SELECT *
        FROM buses
        ORDER BY bus_number
    """).fetchall()

    bookings = conn.execute("""
        SELECT
            bookings.*,
            users.name,
            users.email,
            buses.bus_number
        FROM bookings
        JOIN users ON bookings.user_id = users.id
        JOIN buses ON bookings.bus_id = buses.id
        ORDER BY bookings.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        total_users=total_users,
        total_buses=total_buses,
        total_bookings=total_bookings,
        active_bookings=active_bookings,
        revenue=revenue,
        buses=buses,
        bookings=bookings
    )


# ================= ADD BUS =================

@app.route("/admin/add-bus", methods=["POST"])
@admin_required
def add_bus():
    bus_number = request.form.get("bus_number", "").strip().upper()
    source = request.form.get("source", "").strip()
    destination = request.form.get("destination", "").strip()

    try:
        fare = float(request.form.get("fare", "0"))
    except ValueError:
        fare = 0

    if not bus_number or not source or not destination:
        flash("All bus details are required.", "danger")
        return redirect(url_for("admin"))

    if fare <= 0:
        flash("Fare must be greater than zero.", "danger")
        return redirect(url_for("admin"))

    conn = get_db()

    try:
        conn.execute("""
            INSERT INTO buses
            (bus_number, source, destination, fare, total_seats, available_seats)
            VALUES (?, ?, ?, ?, 50, 50)
        """, (bus_number, source, destination, fare))

        conn.commit()
        flash("50-seat bus added successfully.", "success")

    except sqlite3.IntegrityError:
        flash("Bus number already exists.", "danger")

    finally:
        conn.close()

    return redirect(url_for("admin"))


# ================= DELETE BUS =================

@app.route("/admin/delete-bus/<int:bus_id>", methods=["POST"])
@admin_required
def delete_bus(bus_id):
    conn = get_db()

    booking_count = conn.execute("""
        SELECT COUNT(*)
        FROM bookings
        WHERE bus_id = ?
        AND booking_status = 'Confirmed'
    """, (bus_id,)).fetchone()[0]

    if booking_count > 0:
        conn.close()
        flash("Cannot delete a bus with active bookings.", "danger")
        return redirect(url_for("admin"))

    conn.execute("DELETE FROM bookings WHERE bus_id = ?", (bus_id,))
    conn.execute("DELETE FROM buses WHERE id = ?", (bus_id,))

    conn.commit()
    conn.close()

    flash("Bus removed successfully.", "success")
    return redirect(url_for("admin"))


# ================= USER DASHBOARD =================

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()

    total_bookings = conn.execute("""
        SELECT COUNT(*)
        FROM bookings
        WHERE user_id = ?
    """, (session["user_id"],)).fetchone()[0]

    active_bookings = conn.execute("""
        SELECT COUNT(*)
        FROM bookings
        WHERE user_id = ?
        AND booking_status = 'Confirmed'
    """, (session["user_id"],)).fetchone()[0]

    cancelled_bookings = conn.execute("""
        SELECT COUNT(*)
        FROM bookings
        WHERE user_id = ?
        AND booking_status = 'Cancelled'
    """, (session["user_id"],)).fetchone()[0]

    recent_bookings = conn.execute("""
        SELECT
            bookings.id,
            bookings.seats,
            bookings.seat_numbers,
            bookings.total_fare,
            bookings.booking_status,
            buses.bus_number,
            buses.source,
            buses.destination
        FROM bookings
        JOIN buses ON bookings.bus_id = buses.id
        WHERE bookings.user_id = ?
        ORDER BY bookings.id DESC
        LIMIT 5
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        total_bookings=total_bookings,
        active_bookings=active_bookings,
        cancelled_bookings=cancelled_bookings,
        recent_bookings=recent_bookings
    )


# ================= START =================

init_db()

if __name__ == "__main__":
    app.run(debug=True)
