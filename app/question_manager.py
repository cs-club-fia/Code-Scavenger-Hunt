"""
Question Manager for School Hackathon
Handles question access, timers, and submission logic.
Compatible with Python 3.10+
"""
import os
import json
import time
from threading import Lock
import logging

# Initialize logging
logging.basicConfig(filename='app/logs/errors.log', level=logging.ERROR, format='%(asctime)s - %(levelname)s - %(message)s')

class QuestionManager:
    def __init__(self, questions_dir, submissions_dir, logins_path, db_path):
        self.questions_dir = questions_dir
        self.submissions_dir = submissions_dir
        self.logins_path = logins_path
        self.db_path = db_path
        self.lock = Lock()
        self.timers = {
            "question1": 20,   # 20 seconds (changed for testing)
            "question2": 900,  # 15 min
            "question3": 1200, # 20 min
            "question4": 900,  # 15 min
            "question5": 600   # 10 min
        }
        # Single overall test duration (sum of per-question defaults)
        self.total_time = sum(self.timers.values())
        self.load_logins()
        self.load_answers()
        self.load_hints()
        self._init_db()

    def load_logins(self):
        with open(self.logins_path, 'r') as f:
            self.logins = json.load(f)

    def load_answers(self):
        """Load answers from answers.json file."""
        answers_path = os.path.join(self.questions_dir, 'answers.json')
        try:
            with open(answers_path, 'r') as f:
                self.answers = json.load(f)
        except Exception:
            self.answers = {}

    def load_hints(self):
        """Load hints from hints.json file."""
        hints_path = os.path.join(self.questions_dir, 'hints.json')
        try:
            with open(hints_path, 'r') as f:
                self.hints = json.load(f)
        except Exception:
            self.hints = {}
            self.logins = json.load(f)

    def _init_db(self):
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS submissions (
                username TEXT,
                question TEXT,
                submitted INTEGER,
                start_time REAL,
                PRIMARY KEY (username, question)
            )''')
            # Table for student metrics such as leave counts
            c.execute('''CREATE TABLE IF NOT EXISTS student_metrics (
                username TEXT PRIMARY KEY,
                leave_count INTEGER DEFAULT 0
            )''')
            # Add a column to store the last leave timestamp (to debounce rapid events)
            try:
                c.execute("ALTER TABLE student_metrics ADD COLUMN last_leave_ts REAL DEFAULT 0")
            except Exception:
                # SQLite will raise if the column already exists; ignore
                pass
            # Table to track when the student started the overall test session
            c.execute('''CREATE TABLE IF NOT EXISTS test_sessions (
                username TEXT PRIMARY KEY,
                start_time REAL
            )''')
            # Global test control table (single row) for admin-started test
            c.execute('''CREATE TABLE IF NOT EXISTS global_test (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                start_time REAL,
                duration INTEGER
            )''')
            conn.commit()

    def get_question_text(self, qname):
        qpath = os.path.join(self.questions_dir, f"{qname}.txt")
        if os.path.exists(qpath):
            with open(qpath, 'r') as f:
                return f.read()
        return None

    def start_timer(self, username, qname):
        # Deprecated: per-question timers replaced by a single overall test timer.
        # Keep the function for backward compatibility but do nothing.
        return

    def start_test(self, username):
        """Start the overall test timer for `username`. Only sets once."""
        # Deprecated: per-user start; kept for compatibility but forward to global start
        return

    # --- Global test control ---
    def start_global_test(self, duration=None):
        """Start the global test timer. duration in seconds. Writes a single-row global_test record."""
        import sqlite3, time
        if duration is None:
            duration = int(self.total_time)
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            # Insert or ignore if already started
            c.execute("SELECT start_time FROM global_test WHERE id=1")
            row = c.fetchone()
            if not row:
                c.execute("INSERT INTO global_test (id, start_time, duration) VALUES (1, ?, ?)", (time.time(), int(duration)))
                conn.commit()

    def reset_global_test(self):
        import sqlite3
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM global_test WHERE id=1")
            conn.commit()

    def get_time_left(self, username, qname):
        # Return remaining time for the global test session
        import sqlite3, time
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT start_time, duration FROM global_test WHERE id=1")
            row = c.fetchone()
            if row and row[0] and row[1]:
                start_ts, duration = row[0], row[1]
                elapsed = time.time() - start_ts
                left = int(duration - elapsed)
                return max(0, left)
            # If global test hasn't started, return full configured total_time
            return int(self.total_time)

    def get_global_time_left(self):
        """Return remaining seconds for the global timer (same as get_time_left but without username)."""
        return self.get_time_left(None, None)

    def is_global_started(self):
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT start_time FROM global_test WHERE id=1")
            row = c.fetchone()
            return bool(row and row[0])

    def can_access(self, username, qname):
        left = self.get_time_left(username, qname)
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT submitted FROM submissions WHERE username=? AND question=?", (username, qname))
            row = c.fetchone()
            submitted = bool(row and row[0])
        return left > 0 and not submitted

    def submit_answer(self, username, qname, file_path):
        import sqlite3
        with self.lock:
            try:
                # Do not store files; only record submission in database
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    c.execute("""
                        INSERT OR REPLACE INTO submissions 
                        (username, question, submitted, start_time)
                        VALUES (?, ?, 1, COALESCE(
                            (SELECT start_time FROM submissions WHERE username=? AND question=?),
                            ?
                        ))
                    """, (username, qname, username, qname, time.time()))
                    conn.commit()
            except Exception as e:
                logging.error(f"Error in submit_answer: {str(e)}")
                raise

    def mark_submitted(self, username, qname):
        """Mark a question as submitted without uploading a file (used for key verification)."""
        import sqlite3, time
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            # Preserve any existing start_time for the question if present
            c.execute("""
                INSERT OR REPLACE INTO submissions (username, question, submitted, start_time)
                VALUES (?, ?, 1, COALESCE((SELECT start_time FROM submissions WHERE username=? AND question=?), ?))
            """, (username, qname, username, qname, time.time()))
            conn.commit()

    def has_started(self, username):
        """Return True if the user has started the overall test session."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT start_time FROM test_sessions WHERE username=?", (username,))
            row = c.fetchone()
            return bool(row and row[0])

    def get_expected_key(self, qname):
        """Get the expected answer from answers.json."""
        return self.answers.get(qname)

    def get_hint(self, qname):
        """Get the hint for a question from hints.json."""
        return self.hints.get(qname)

    def has_submitted(self, username, qname):
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT submitted FROM submissions WHERE username=? AND question=?", (username, qname))
            row = c.fetchone()
            return row and row[0]

    def get_all_submissions(self):
        import sqlite3
        result = {}
        
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT username, question, submitted FROM submissions")
            rows = c.fetchall()
            
            # Initialize result with all students from logins (so admins see every student)
            try:
                students = [s['username'] for s in self.logins.get('students', [])]
            except Exception:
                students = []
            for username in students:
                result[username] = {q: False for q in self.timers.keys()}

            # Also include any users recorded in the submissions DB that might not be in logins
            for username, _, _ in rows:
                if username not in result:
                    result[username] = {q: False for q in self.timers.keys()}
            
            # Update with actual submission status
            for username, question, submitted in rows:
                result[username][question] = bool(submitted)
                
            # No file-system backup: rely solely on DB records
        
        return result

    def reset(self):
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("DELETE FROM submissions")
            conn.commit()

    # --- Leave count metrics ---
    def increment_leave_count(self, username):
        import sqlite3
        import time
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            # Ensure a row exists
            c.execute("INSERT OR IGNORE INTO student_metrics (username, leave_count, last_leave_ts) VALUES (?, 0, 0)", (username,))
            # Read last leave timestamp
            c.execute("SELECT last_leave_ts FROM student_metrics WHERE username = ?", (username,))
            row = c.fetchone()
            last_ts = float(row[0]) if row and row[0] is not None else 0.0
            now = time.time()
            # Debounce rapid events: only count if at least 3 seconds since last recorded leave
            if now - last_ts >= 3.0:
                c.execute("UPDATE student_metrics SET leave_count = leave_count + 1, last_leave_ts = ? WHERE username = ?", (now, username))
                conn.commit()
            else:
                # Update last_leave_ts to the latest time to avoid repeated near-simultaneous events
                c.execute("UPDATE student_metrics SET last_leave_ts = ? WHERE username = ?", (now, username))
                conn.commit()

    def get_leave_counts(self):
        import sqlite3
        result = {}
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT username, leave_count FROM student_metrics")
            rows = c.fetchall()
            for username, leave_count in rows:
                result[username] = leave_count

        # Ensure all students are present with at least 0
        try:
            students = [s['username'] for s in self.logins.get('students', [])]
        except Exception:
            students = []
        for s in students:
            result.setdefault(s, 0)

        return result

# Usage example:
# qm = QuestionManager('app/questions', 'app/submissions', 'app/logins.json')
# qm.start_timer('student1', 'question1')
# print(qm.get_time_left('student1', 'question1'))
