**Project Overview**
- **What:** Code Scavenger Hunt — a Flask-based timed quiz/mission platform with admin dashboard, global timer, and per-mission keys.
- **Key features:** Admin dashboard, start/reset global timer, reset database, question pages with preserved formatting, in-page key verification, hint popup per question, answers/hints stored centrally.

**Quick Start (Windows, PowerShell)**
- Prerequisites: Python 3.10+, virtualenv recommended. Install dependencies from `requirements.txt`.

```powershell
# create & activate venv (optional)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# install deps
pip install -r requirements.txt

# start the app
python startup.py

# Open in browser: http://localhost:5000
```

**Project Layout**
- `app/` — Flask app code and templates
- `app/questions/` — question text files plus `answers.json` and `hints.json`
- `app/templates/` — HTML templates (see `question.html`, `admin.html`)
- `app/static/` — CSS/JS assets (timer.js, style.css)
- `submissions/` — (optional) file uploads (not used for key-verified submissions)
- `submissions.db` — SQLite DB used for submissions/metrics/global timer

**Where data lives**
- Timer initial values: defined in `app/question_manager.py` as `self.timers` (per-question defaults). `total_time` is the sum.
- Mission answers: `app/questions/answers.json` (keys are `question1`, `question2`, ...).
- Mission hints: `app/questions/hints.json`.
- Runtime state (who submitted, global start time, metrics): `submissions.db` (SQLite).

**How the question flow works**
- Students open a mission at `/question?qname=question1` (links from dashboard).
- The page displays the question exactly as in the `.txt` file (uses a `<pre>` block to preserve formatting).
- The page includes an input and Submit button to verify the mission key — verification occurs on POST to `/question`.
- If correct: server records submission (`submissions` table) and redirects to next mission or `success.html`.
- If incorrect: user is shown the `lost.html` retry flow.
- Hints: click the **Show Hint** button on the question page to open a modal with the hint text for that mission (hint drawn from `hints.json`).

**Admin features**
- Admin dashboard: `/admin` — shows submissions table, system stats, and admin controls.
- Start global test (button) → triggers `qm.start_global_test()` (route `/admin/start_test`).
- Reset global timer only: `Reset Global Timer Only` button posts to `/admin/reset_timer` and clears the global test row in DB (no submission deletions).
- Reset database (dangerous): `Reset All Submissions` deletes `submissions`, `test_sessions`, and `global_test` rows (route `/admin/reset`).

**Editing questions, answers, and hints**
- Edit textual content of missions in `app/questions/questionN.txt`.
- Update or correct answers in `app/questions/answers.json` (JSON format: keys are `question1`, ...).
- Update hints in `app/questions/hints.json`.

Example `answers.json`:
```json
{
  "question1": "721",
  "question2": "AETDL"
}
```

Example `hints.json`:
```json
{
  "question1": "Start from the smallest number and climb back up.",
  "question2": "Check even/odd lengths of file names."
}
```

**Git / Deployment notes**
- If you want to replace the remote repo contents with this workspace, follow one of the GUI or CLI flows described in the project or use the commands below.

CLI quick replace (careful: may overwrite remote history):
```powershell
# stage everything (including deletions)
git add -A
git commit -m "Replace repo with updated Code Scavenger Hunt workspace"

# push (normal push) - replace "main" with your target branch
git push origin HEAD:main

# if remote rejects and you intentionally want to overwrite
git push --force origin HEAD:main
```

If you prefer a GUI workflow, use GitHub Desktop or VS Code Source Control to stage all changes and push. Create a remote backup branch first if you plan to force-push.

**Troubleshooting**
- If you see weird characters (like `â€“` or `â†’`) in question pages, ensure the `.txt` files are UTF-8 and/or replace special punctuation with ASCII equivalents (we store plain text `.txt` files in `app/questions/`).
- If admin page shows routing errors after edits, restart the server so Flask loads the latest routes.

**Contact / Next steps**
- If you'd like, I can: create a small admin-only page for editing `answers.json` and `hints.json` from the browser; or add an audit log for hint views. Tell me which you'd prefer.

---
Generated README for the current workspace.
