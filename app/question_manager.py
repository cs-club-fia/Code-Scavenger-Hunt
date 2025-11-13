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
        # Total test time: by default sum of per-question timers, can be overridden later
        self.total_time = sum(self.timers.values())
        self.load_logins()
        self._init_db()

    def load_logins(self):
        with open(self.logins_path, 'r') as f:
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
            # Table for global test sessions (single timer per user)
            c.execute('''CREATE TABLE IF NOT EXISTS test_sessions (
                username TEXT PRIMARY KEY,
                start_time REAL
            )''')
            # Add a column to store the last leave timestamp (to debounce rapid events)
            try:
                c.execute("ALTER TABLE student_metrics ADD COLUMN last_leave_ts REAL DEFAULT 0")
            except Exception:
                # SQLite will raise if the column already exists; ignore
                pass
            conn.commit()

    # --- Global timer/session methods ---
    def start_global_timer(self, username):
        """Start a single global timer for the user if not already started."""
        import sqlite3, time
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT start_time FROM test_sessions WHERE username = ?", (username,))
            row = c.fetchone()
            if not row:
                c.execute("INSERT INTO test_sessions (username, start_time) VALUES (?, ?)", (username, time.time()))
                conn.commit()

    def has_global_started(self, username):
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT start_time FROM test_sessions WHERE username = ?", (username,))
            row = c.fetchone()
            return bool(row and row[0])

    def get_global_time_left(self, username):
        import sqlite3, time
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT start_time FROM test_sessions WHERE username = ?", (username,))
            row = c.fetchone()
            if row and row[0]:
                elapsed = time.time() - row[0]
                left = self.total_time - elapsed
                return max(0, int(left))
            return int(self.total_time)

    def get_question_text(self, qname):
        qpath = os.path.join(self.questions_dir, f"{qname}.txt")
        if os.path.exists(qpath):
            with open(qpath, 'r') as f:
                return f.read()
        return None

    def verify_key(self, qname, key):
        """Verify the provided key string against the question's declared Answer: line.
        Returns True/False. Comparison is case-insensitive and strips whitespace."""
        text = self.get_question_text(qname)
        if not text:
            return False
        for line in text.splitlines():
            if line.strip().lower().startswith('answer:'):
                expected = line.split(':', 1)[1].strip()
                return expected.lower() == key.strip().lower()
        return False

    def start_timer(self, username, qname):
        # Deprecated per-question start - preserved for compatibility but not used when global timer is enabled
        import sqlite3, time
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT start_time FROM submissions WHERE username=? AND question=?", (username, qname))
            row = c.fetchone()
            if not row:
                c.execute("INSERT INTO submissions (username, question, submitted, start_time) VALUES (?, ?, 0, ?)", (username, qname, 0, time.time()))
                conn.commit()

    def get_time_left(self, username, qname):
        # Deprecated: use global timer instead
        return self.get_global_time_left(username)

    def can_access(self, username, qname):
        # Access allowed only if global timer still has time and question not yet verified/submitted
        left = self.get_global_time_left(username)
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
                # Save submission file
                user_dir = os.path.join(self.submissions_dir, username)
                os.makedirs(user_dir, exist_ok=True)
                dest = os.path.join(user_dir, f"{qname}.py")
                os.replace(file_path, dest)
                # For compatibility, mark as submitted (legacy). Prefer using save_submission_file + mark_submission_verified flow.
                with sqlite3.connect(self.db_path) as conn:
                    c = conn.cursor()
                    c.execute("INSERT OR REPLACE INTO submissions (username, question, submitted, start_time) VALUES (?, ?, 1, COALESCE((SELECT start_time FROM submissions WHERE username=? AND question=?), ?))",
                              (username, qname, 1, username, qname, time.time()))
                    conn.commit()
            except Exception as e:
                logging.error(f"Error in submit_answer: {str(e)}")
                raise

    def save_submission_file(self, username, qname, file_path):
        """Save the uploaded file to the user's submissions directory without marking the question as verified/submitted."""
        with self.lock:
            try:
                user_dir = os.path.join(self.submissions_dir, username)
                os.makedirs(user_dir, exist_ok=True)
                dest = os.path.join(user_dir, f"{qname}.py")
                os.replace(file_path, dest)
            except Exception as e:
                logging.error(f"Error in save_submission_file: {str(e)}")
                raise

    def mark_submission_verified(self, username, qname):
        """Mark a saved submission as verified/submitted (used after key verification)."""
        import sqlite3, time
        with self.lock, sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            # Attempt to use the test_sessions start_time as the canonical start
            c.execute("SELECT start_time FROM submissions WHERE username=? AND question=?", (username, qname))
            existing = c.fetchone()
            if existing and existing[0]:
                start_ts = existing[0]
            else:
                c.execute("SELECT start_time FROM test_sessions WHERE username=?", (username,))
                row = c.fetchone()
                start_ts = row[0] if row and row[0] else time.time()
            c.execute("INSERT OR REPLACE INTO submissions (username, question, submitted, start_time) VALUES (?, ?, 1, ?)", (username, qname, 1, start_ts))
            conn.commit()

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
                
            # Check file system for submissions as backup
            for username in result.keys():
                user_dir = os.path.join(self.submissions_dir, username)
                if os.path.exists(user_dir):
                    for qname in self.timers.keys():
                        if os.path.exists(os.path.join(user_dir, f"{qname}.py")):
                            result[username][qname] = True
        
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
