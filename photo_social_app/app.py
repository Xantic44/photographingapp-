"""
Beginner Flask app with SQLite.

What this file does:
1) Starts your web server
2) Creates a database + table (if missing)
3) Serves the homepage
4) Exposes one API endpoint for JavaScript
"""
from flask import Flask, jsonify, render_template, request
import sqlite3

# Create Flask app object
app = Flask(__name__)

# Name of the SQLite database file
DB_NAME = "photo_social.db"


def init_db():
    """
    Create the database table if it doesn't exist.
    This runs once when the app starts.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Simple table to store messages/notes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL
        )
    """)

    # If table is empty, insert one starter row
    cur.execute("SELECT COUNT(*) FROM notes")
    count = cur.fetchone()[0]
    if count == 0:
        cur.execute(
            "INSERT INTO notes (text) VALUES (?)",
            ("Welcome to your first Flask app!",)
        )

    conn.commit()
    conn.close()


@app.route("/")
def home():
    """
    Show index.html from templates folder.
    """
    return render_template("index.html")


@app.route("/api/hello")
def hello():
    """
    Return JSON data for frontend JavaScript.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Get latest note text
    cur.execute("SELECT text FROM notes ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()

    conn.close()

    message = row[0] if row else "Hello from Flask + SQLite!"
    return jsonify({"message": message})


@app.route("/api/notes", methods=["GET"])
def list_notes():
    """
    Return latest notes as JSON list.
    Frontend uses this to render note cards.
    """
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # Get latest 10 notes (newest first).
    cur.execute("SELECT id, text FROM notes ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()
    conn.close()

    # Convert SQL rows into JSON-friendly dictionaries.
    notes = [{"id": row[0], "text": row[1]} for row in rows]
    return jsonify({"notes": notes})



@app.route("/api/notes", methods=["POST"])
def create_note():
    """
    Create a new note from JSON body.
    Expected JSON:
    {
      "text": "your note text"
    }
    """
    # Read JSON data sent from frontend.
    data = request.get_json()

    # Get "text" value safely and clean extra spaces.
    text = (data.get("text") if data else "").strip()

    # Basic validation: empty text is not allowed.
    if not text:
        return jsonify({"error": "Text is required"}), 400

    # Save the new note into SQLite database.
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO notes (text) VALUES (?)", (text,))
    conn.commit()
    conn.close()

    # 201 = resource created successfully.
    return jsonify({"message": "Note created successfully"}), 201


if __name__ == "__main__":
    # Make sure DB exists before server starts
    init_db()

    # Start local development server
    app.run(debug=True)
