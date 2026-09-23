from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http import cookies
from pathlib import Path
import hashlib
import json
import mimetypes
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).parent
DATABASE = ROOT / "jpounds.db"
SESSIONS = {}
ROOMS = {
    1: {"name": "Room 1", "beds": ["A1", "A2", "B1", "B2"]},
    2: {"name": "Room 2", "beds": ["A1", "A2", "B1", "B2"]},
    3: {"name": "Room 3", "beds": ["A1", "A2", "B1", "B2"]},
    4: {"name": "Room 4", "beds": ["A1", "A2", "B1", "B2"]},
    5: {"name": "Room 5", "beds": ["A1", "A2", "B1", "B2"]},
    8: {"name": "Room A", "beds": ["A1", "B1"]},
    9: {"name": "Room B", "beds": ["A1", "B1"]},
}


def connect_database():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with connect_database() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guest_name TEXT NOT NULL,
                guest_email TEXT NOT NULL,
                room INTEGER NOT NULL,
                beds TEXT NOT NULL,
                check_in TEXT NOT NULL,
                check_out TEXT NOT NULL,
                payment_method TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );

            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                token TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000
    ).hex()
    return salt, password_hash


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    try:
        return json.loads(handler.rfile.read(length) or b"{}")
    except (json.JSONDecodeError, ValueError):
        return {}


class JpoundsHandler(BaseHTTPRequestHandler):
    def send_json(self, status, payload, extra_headers=None):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def get_session(self):
        header = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie()
        jar.load(header)
        session_id = jar.get("jpounds_session")
        return SESSIONS.get(session_id.value) if session_id else None

    def do_POST(self):
        route = urlparse(self.path).path
        data = read_json(self)

        if route == "/api/signup":
            self.signup(data)
        elif route == "/api/login":
            self.login(data)
        elif route == "/api/logout":
            self.logout()
        elif route == "/api/forgot-password":
            self.forgot_password(data)
        elif route == "/api/reset-password":
            self.reset_password(data)
        elif route == "/api/bookings":
            self.create_booking(data)
        else:
            self.send_json(404, {"error": "Endpoint not found."})

    def signup(self, data):
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        if not name or not email or len(password) < 6:
            self.send_json(400, {"error": "Enter a name, valid email, and password of at least 6 characters."})
            return
        if "@" not in email or "." not in email.split("@")[-1]:
            self.send_json(400, {"error": "Please enter a valid email address."})
            return

        salt, password_hash = hash_password(password)
        try:
            with connect_database() as connection:
                connection.execute(
                    "INSERT INTO users (name, email, password_hash, password_salt) VALUES (?, ?, ?, ?)",
                    (name, email, password_hash, salt),
                )
            self.send_json(201, {"message": "Account created. You can now log in."})
        except sqlite3.IntegrityError:
            self.send_json(409, {"error": "This email is already in use. Please use a different email."})

    def login(self, data):
        email = str(data.get("email", "")).strip().lower()
        password = str(data.get("password", ""))
        with connect_database() as connection:
            account = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if not account:
            self.send_json(401, {"error": "The email or password is incorrect."})
            return

        _, password_hash = hash_password(password, account["password_salt"])
        if not secrets.compare_digest(password_hash, account["password_hash"]):
            self.send_json(401, {"error": "The email or password is incorrect."})
            return

        session_id = secrets.token_urlsafe(32)
        SESSIONS[session_id] = {"id": account["id"], "name": account["name"], "email": account["email"]}
        self.send_json(
            200,
            {"user": SESSIONS[session_id]},
            {"Set-Cookie": f"jpounds_session={session_id}; HttpOnly; SameSite=Lax; Path=/"},
        )

    def logout(self):
        header = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie()
        jar.load(header)
        session_id = jar.get("jpounds_session")
        if session_id:
            SESSIONS.pop(session_id.value, None)
        self.send_json(
            200,
            {"message": "Logged out."},
            {"Set-Cookie": "jpounds_session=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/"},
        )

    def forgot_password(self, data):
        email = str(data.get("email", "")).strip().lower()
        if not email:
            self.send_json(400, {"error": "Please enter your email address."})
            return

        with connect_database() as connection:
            account = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if account:
                token = secrets.token_urlsafe(32)
                expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
                connection.execute(
                    "DELETE FROM password_resets WHERE email = ?",
                    (email,),
                )
                connection.execute(
                    "INSERT INTO password_resets (email, token, expires_at) VALUES (?, ?, ?)",
                    (email, token, expires_at),
                )
                print(f"Password reset link for {email}: http://127.0.0.1:8000/reset-password?token={token}&email={email}")

        self.send_json(200, {"message": "If that email is registered, a reset link has been prepared. In local mode, the reset token is shown in the server terminal."})

    def reset_password(self, data):
        email = str(data.get("email", "")).strip().lower()
        token = str(data.get("token", "")).strip()
        password = str(data.get("password", ""))

        if not email or not token or len(password) < 6:
            self.send_json(400, {"error": "Please enter a valid email, reset token, and new password with at least 6 characters."})
            return

        with connect_database() as connection:
            reset_row = connection.execute(
                "SELECT * FROM password_resets WHERE email = ? AND token = ? ORDER BY created_at DESC LIMIT 1",
                (email, token),
            ).fetchone()

            if not reset_row:
                self.send_json(400, {"error": "Invalid or expired reset token."})
                return

            expires_at = datetime.fromisoformat(reset_row["expires_at"])
            if expires_at < datetime.now(timezone.utc):
                connection.execute("DELETE FROM password_resets WHERE email = ?", (email,))
                self.send_json(400, {"error": "This reset token has expired. Please request a new one."})
                return

            salt, password_hash = hash_password(password)
            connection.execute(
                "UPDATE users SET password_hash = ?, password_salt = ? WHERE email = ?",
                (password_hash, salt, email),
            )
            connection.execute("DELETE FROM password_resets WHERE email = ?", (email,))

        self.send_json(200, {"message": "Your password has been reset successfully."})

    def create_booking(self, data):
        session = self.get_session()
        if not session:
            self.send_json(401, {"error": "Please log in before booking a room."})
            return

        fields = ["guest_name", "guest_email", "room", "beds", "check_in", "check_out", "payment_method"]
        if any(not data.get(field) for field in fields):
            self.send_json(400, {"error": "Please complete all booking details."})
            return

        try:
            room = int(data["room"])
        except (TypeError, ValueError):
            self.send_json(400, {"error": "Please select a valid room."})
            return

        beds = data["beds"]
        if room not in ROOMS or not isinstance(beds, list) or not beds:
            self.send_json(400, {"error": "Please select a valid room and at least one bed."})
            return
        if len(set(beds)) != len(beds) or any(bed not in ROOMS[room]["beds"] for bed in beds):
            self.send_json(400, {"error": "One or more selected beds are invalid for this room."})
            return
        if data["check_in"] >= data["check_out"]:
            self.send_json(400, {"error": "Check-out must be after check-in."})
            return

        with connect_database() as connection:
            connection.execute("BEGIN IMMEDIATE")
            occupied = self.get_occupied_beds(connection, room, data["check_in"], data["check_out"])
            conflicts = sorted(set(beds) & occupied)
            if conflicts:
                self.send_json(409, {"error": "These beds are no longer available: " + ", ".join(conflicts)})
                return

            connection.execute(
                """INSERT INTO bookings
                (user_id, guest_name, guest_email, room, beds, check_in, check_out, payment_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (session["id"], data["guest_name"], data["guest_email"], room,
                 json.dumps(beds), data["check_in"], data["check_out"], data["payment_method"]),
            )
        self.send_json(201, {"message": "Booking request saved successfully."})

    @staticmethod
    def get_occupied_beds(connection, room, check_in, check_out):
        rows = connection.execute(
            """SELECT beds FROM bookings
            WHERE room = ? AND check_in < ? AND check_out > ?""",
            (room, check_out, check_in),
        ).fetchall()
        occupied = set()
        for row in rows:
            occupied.update(json.loads(row["beds"]))
        return occupied

    def get_availability(self, query):
        check_in = query.get("check_in", [""])[0]
        check_out = query.get("check_out", [""])[0]
        if not check_in or not check_out or check_in >= check_out:
            self.send_json(400, {"error": "Choose a valid check-in and check-out date."})
            return

        with connect_database() as connection:
            rooms = []
            for room_id, room in ROOMS.items():
                occupied = self.get_occupied_beds(connection, room_id, check_in, check_out)
                available_beds = [bed for bed in room["beds"] if bed not in occupied]
                if available_beds:
                    rooms.append({
                        "id": room_id,
                        "name": room["name"],
                        "capacity": len(room["beds"]),
                        "beds": room["beds"],
                        "available_beds": available_beds,
                    })
        self.send_json(200, {"rooms": rooms})

    def do_GET(self):
        parsed_url = urlparse(self.path)
        route = parsed_url.path
        if route == "/api/session":
            self.send_json(200, {"user": self.get_session()})
            return
        if route == "/api/availability":
            self.get_availability(parse_qs(parsed_url.query))
            return

        requested = unquote(route.lstrip("/")) or "index.html"
        file_path = (ROOT / requested).resolve()
        if ROOT not in file_path.parents and file_path != ROOT:
            self.send_json(403, {"error": "Access denied."})
            return
        if not file_path.is_file():
            self.send_json(404, {"error": "File not found."})
            return

        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(file_path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format_string, *args):
        print(f"{self.address_string()} - {format_string % args}")


if __name__ == "__main__":
    initialize_database()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), JpoundsHandler)
    print("Jpound's Hostel is running at http://127.0.0.1:8000")
    print(f"Database: {DATABASE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()
