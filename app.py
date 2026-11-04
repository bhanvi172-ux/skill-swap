from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change-this-secret-key-for-your-project"
DB_NAME = "skill_swap.db"

def db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            bio TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            skill_name TEXT NOT NULL,
            skill_type TEXT NOT NULL CHECK(skill_type IN ('offer','want')),
            level TEXT DEFAULT 'Beginner',
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS exchanges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            offered_skill TEXT NOT NULL,
            requested_skill TEXT NOT NULL,
            message TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(sender_id) REFERENCES users(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exchange_id INTEGER NOT NULL UNIQUE,
            reviewer_id INTEGER NOT NULL,
            reviewee_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            comment TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY(exchange_id) REFERENCES exchanges(id),
            FOREIGN KEY(reviewer_id) REFERENCES users(id),
            FOREIGN KEY(reviewee_id) REFERENCES users(id)
        );
        """)
        # A few sample members make the project useful immediately.
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count == 0:
            samples = [
                ("Aarav Sharma", "aarav@example.com", "Python", "Graphic Design", "Intermediate", "Beginner", "I enjoy automation and helping beginners."),
                ("Meera Kapoor", "meera@example.com", "Graphic Design", "Public Speaking", "Intermediate", "Beginner", "Designing posters, logos, and social posts."),
                ("Kabir Singh", "kabir@example.com", "Video Editing", "Python", "Beginner", "Beginner", "I make short videos and want to learn coding."),
                ("Isha Verma", "isha@example.com", "Excel", "Web Development", "Advanced", "Beginner", "Good with spreadsheets and data organization.")
            ]
            for name, email, offer, want, level1, level2, bio in samples:
                cur = con.execute("INSERT INTO users(name,email,password,bio,created_at) VALUES(?,?,?,?,?)",
                    (name, email, generate_password_hash("demo123"), bio, datetime.now().isoformat(timespec="seconds")))
                uid = cur.lastrowid
                con.execute("INSERT INTO skills(user_id,skill_name,skill_type,level) VALUES(?,?,?,?)", (uid, offer, "offer", level1))
                con.execute("INSERT INTO skills(user_id,skill_name,skill_type,level) VALUES(?,?,?,?)", (uid, want, "want", level2))

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_user():
    if session.get("user_id"):
        with db() as con:
            user = con.execute("SELECT id,name,email FROM users WHERE id=?", (session["user_id"],)).fetchone()
        return {"current_user": user}
    return {"current_user": None}

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    with db() as con:
        if q:
            members = con.execute("""
                SELECT u.*, GROUP_CONCAT(CASE WHEN s.skill_type='offer' THEN s.skill_name END, ', ') AS offers,
                       GROUP_CONCAT(CASE WHEN s.skill_type='want' THEN s.skill_name END, ', ') AS wants
                FROM users u LEFT JOIN skills s ON s.user_id=u.id
                WHERE u.id != COALESCE(?, -1) AND
                (u.name LIKE ? OR u.bio LIKE ? OR s.skill_name LIKE ?)
                GROUP BY u.id ORDER BY u.name
            """, (session.get("user_id"), f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
        else:
            members = con.execute("""
                SELECT u.*, GROUP_CONCAT(CASE WHEN s.skill_type='offer' THEN s.skill_name END, ', ') AS offers,
                       GROUP_CONCAT(CASE WHEN s.skill_type='want' THEN s.skill_name END, ', ') AS wants
                FROM users u LEFT JOIN skills s ON s.user_id=u.id
                WHERE u.id != COALESCE(?, -1)
                GROUP BY u.id ORDER BY u.id DESC
            """, (session.get("user_id"),)).fetchall()
        offers_count = con.execute("SELECT COUNT(*) FROM skills WHERE skill_type='offer'").fetchone()[0]
        members_count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        exchanges_count = con.execute("SELECT COUNT(*) FROM exchanges").fetchone()[0]
    return render_template("index.html", members=members, q=q, offers_count=offers_count,
                           members_count=members_count, exchanges_count=exchanges_count)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 6:
            flash("Enter your name, a valid email, and a password of at least 6 characters.", "danger")
            return render_template("register.html")
        try:
            with db() as con:
                cur = con.execute("INSERT INTO users(name,email,password,created_at) VALUES(?,?,?,?)",
                    (name, email, generate_password_hash(password), datetime.now().isoformat(timespec="seconds")))
                uid = cur.lastrowid
            session["user_id"] = uid
            flash("Welcome! Add your skills to complete your profile.", "success")
            return redirect(url_for("profile"))
        except sqlite3.IntegrityError:
            flash("That email is already registered. Please log in.", "danger")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with db() as con:
            user = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            flash("You are now logged in.", "success")
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    uid = session["user_id"]
    with db() as con:
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            bio = request.form.get("bio", "").strip()
            if name:
                con.execute("UPDATE users SET name=?, bio=? WHERE id=?", (name, bio, uid))
                flash("Profile updated.", "success")
                return redirect(url_for("profile"))
            flash("Name cannot be empty.", "danger")
        user = con.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        skills = con.execute("SELECT * FROM skills WHERE user_id=? ORDER BY skill_type, skill_name", (uid,)).fetchall()
    return render_template("profile.html", user=user, skills=skills)

@app.route("/skills/add", methods=["POST"])
@login_required
def add_skill():
    skill = request.form.get("skill_name", "").strip()
    kind = request.form.get("skill_type", "offer")
    level = request.form.get("level", "Beginner")
    if not skill or kind not in ("offer", "want") or level not in ("Beginner", "Intermediate", "Advanced"):
        flash("Please enter a valid skill and level.", "danger")
    else:
        with db() as con:
            exists = con.execute("SELECT id FROM skills WHERE user_id=? AND lower(skill_name)=lower(?) AND skill_type=?",
                                 (session["user_id"], skill, kind)).fetchone()
            if exists:
                flash("That skill is already in your list.", "warning")
            else:
                con.execute("INSERT INTO skills(user_id,skill_name,skill_type,level) VALUES(?,?,?,?)",
                            (session["user_id"], skill, kind, level))
                flash("Skill added to your profile.", "success")
    return redirect(url_for("profile"))

@app.route("/skills/delete/<int:skill_id>", methods=["POST"])
@login_required
def delete_skill(skill_id):
    with db() as con:
        con.execute("DELETE FROM skills WHERE id=? AND user_id=?", (skill_id, session["user_id"]))
    flash("Skill removed.", "info")
    return redirect(url_for("profile"))

@app.route("/request/<int:member_id>", methods=["GET", "POST"])
@login_required
def request_exchange(member_id):
    if member_id == session["user_id"]:
        return redirect(url_for("index"))
    with db() as con:
        member = con.execute("SELECT * FROM users WHERE id=?", (member_id,)).fetchone()
        my_offers = con.execute("SELECT * FROM skills WHERE user_id=? AND skill_type='offer'", (session["user_id"],)).fetchall()
        their_offers = con.execute("SELECT * FROM skills WHERE user_id=? AND skill_type='offer'", (member_id,)).fetchall()
        if not member:
            flash("Member not found.", "danger")
            return redirect(url_for("index"))
        if request.method == "POST":
            offered = request.form.get("offered_skill", "").strip()
            wanted = request.form.get("requested_skill", "").strip()
            message = request.form.get("message", "").strip()
            valid_my = [s["skill_name"] for s in my_offers]
            valid_their = [s["skill_name"] for s in their_offers]
            if offered not in valid_my or wanted not in valid_their:
                flash("Choose skills from the available lists.", "danger")
            else:
                con.execute("""INSERT INTO exchanges(sender_id,receiver_id,offered_skill,requested_skill,message,created_at)
                    VALUES(?,?,?,?,?,?)""", (session["user_id"], member_id, offered, wanted, message, datetime.now().isoformat(timespec="seconds")))
                flash("Exchange request sent!", "success")
                return redirect(url_for("dashboard"))
    return render_template("request.html", member=member, my_offers=my_offers, their_offers=their_offers)

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    with db() as con:
        sent = con.execute("""SELECT e.*, u.name AS other_name FROM exchanges e JOIN users u ON u.id=e.receiver_id
                              WHERE e.sender_id=? ORDER BY e.id DESC""", (uid,)).fetchall()
        received = con.execute("""SELECT e.*, u.name AS other_name FROM exchanges e JOIN users u ON u.id=e.sender_id
                                  WHERE e.receiver_id=? ORDER BY e.id DESC""", (uid,)).fetchall()
        my_offers = con.execute("SELECT COUNT(*) FROM skills WHERE user_id=? AND skill_type='offer'", (uid,)).fetchone()[0]
        reviews = con.execute("SELECT COUNT(*) FROM reviews WHERE reviewee_id=?", (uid,)).fetchone()[0]
    return render_template("dashboard.html", sent=sent, received=received, my_offers=my_offers, reviews=reviews)

@app.route("/exchange/<int:exchange_id>/<action>", methods=["POST"])
@login_required
def exchange_action(exchange_id, action):
    if action not in ("accept", "decline", "complete"):
        return redirect(url_for("dashboard"))
    uid = session["user_id"]
    new_status = {"accept": "Accepted", "decline": "Declined", "complete": "Completed"}[action]
    with db() as con:
        ex = con.execute("SELECT * FROM exchanges WHERE id=?", (exchange_id,)).fetchone()
        if not ex or (uid not in (ex["sender_id"], ex["receiver_id"])):
            flash("Exchange not found.", "danger")
        elif action in ("accept", "decline") and ex["receiver_id"] != uid:
            flash("Only the receiver can respond to this request.", "danger")
        elif action == "complete" and ex["status"] != "Accepted":
            flash("Only accepted exchanges can be completed.", "warning")
        else:
            con.execute("UPDATE exchanges SET status=? WHERE id=?", (new_status, exchange_id))
            flash(f"Exchange marked {new_status.lower()}.", "success")
    return redirect(url_for("dashboard"))

@app.route("/review/<int:exchange_id>", methods=["GET", "POST"])
@login_required
def review(exchange_id):
    uid = session["user_id"]
    with db() as con:
        ex = con.execute("""SELECT e.*, s.name AS sender_name, r.name AS receiver_name FROM exchanges e
                            JOIN users s ON s.id=e.sender_id JOIN users r ON r.id=e.receiver_id WHERE e.id=?""",
                         (exchange_id,)).fetchone()
        if not ex or ex["status"] != "Completed" or uid not in (ex["sender_id"], ex["receiver_id"]):
            flash("Reviews are available to participants after completion.", "warning")
            return redirect(url_for("dashboard"))
        if con.execute("SELECT id FROM reviews WHERE exchange_id=?", (exchange_id,)).fetchone():
            flash("A review has already been submitted for this exchange.", "info")
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            rating = request.form.get("rating", "5")
            comment = request.form.get("comment", "").strip()
            try:
                rating = int(rating)
                if rating < 1 or rating > 5:
                    raise ValueError()
                reviewee = ex["receiver_id"] if uid == ex["sender_id"] else ex["sender_id"]
                con.execute("INSERT INTO reviews(exchange_id,reviewer_id,reviewee_id,rating,comment,created_at) VALUES(?,?,?,?,?,?)",
                            (exchange_id, uid, reviewee, rating, comment, datetime.now().isoformat(timespec="seconds")))
                flash("Thanks for sharing your feedback!", "success")
                return redirect(url_for("dashboard"))
            except (ValueError, sqlite3.IntegrityError):
                flash("Please choose a rating from 1 to 5.", "danger")
    other_name = ex["receiver_name"] if uid == ex["sender_id"] else ex["sender_name"]
    return render_template("review.html", exchange=ex, other_name=other_name)

@app.route("/member/<int:member_id>")
def member_detail(member_id):
    with db() as con:
        member = con.execute("SELECT id,name,bio,created_at FROM users WHERE id=?", (member_id,)).fetchone()
        skills = con.execute("SELECT * FROM skills WHERE user_id=? ORDER BY skill_type, skill_name", (member_id,)).fetchall()
        reviews = con.execute("""SELECT r.*, u.name AS reviewer_name FROM reviews r JOIN users u ON u.id=r.reviewer_id
                                 WHERE r.reviewee_id=? ORDER BY r.id DESC""", (member_id,)).fetchall()
        avg = con.execute("SELECT AVG(rating) FROM reviews WHERE reviewee_id=?", (member_id,)).fetchone()[0]
    if not member:
        flash("Member not found.", "danger")
        return redirect(url_for("index"))
    return render_template("member.html", member=member, skills=skills, reviews=reviews, avg=avg)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
