"""
Academic defaults — BioSecure AI (COER University, Roorkee).

Central list of Programs, Branches and Lectures used ONLY as a
fallback / seed so dropdowns are never empty on a fresh database.

Backend behaviour is unchanged: live Supabase rows always win;
these defaults are merged in when the `academic_structure` table
is empty or unreachable, and are offered via the
"Restore defaults" button on /admin/academics.
"""

DEFAULT_PROGRAMS = [
    "B.Tech",
    "M.Tech",
    "BCA",
    "MCA",
    "B.Sc",
    "M.Sc",
    "BBA",
    "MBA",
    "Diploma",
    "Ph.D",
]

DEFAULT_BRANCHES = [
    "CSE",
    "IT",
    "ECE",
    "EEE",
    "ME",
    "CE",
    "AI & ML",
    "Data Science",
    "Cyber Security",
    "Biotechnology",
]

DEFAULT_BATCHES = [
    "2026",
    "2025",
    "2024",
    "2023",
    "2022",
    "2021",
    "2020",
]

# Generic starter lectures — admin can add/rename these on /admin/academics.
# Kept deliberately generic so every department can reuse them.
DEFAULT_LECTURES = [
    "Mathematics",
    "Physics",
    "Programming in C",
    "Data Structures",
    "DBMS",
    "Operating Systems",
    "Computer Networks",
    "Machine Learning",
    "General Session",
]

ALLOWED_ACADEMIC_TYPES = ("program", "branch", "lecture", "batch")

import os
import json

_BATCH_FILE = os.path.join(os.path.dirname(__file__), 'academic_batches.json')

def get_saved_batches():
    """Retrieve saved batches merged with built-in defaults."""
    batches = set(str(y) for y in DEFAULT_BATCHES)
    if os.path.exists(_BATCH_FILE):
        try:
            with open(_BATCH_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if item and str(item).strip():
                            batches.add(str(item).strip())
        except Exception:
            pass
    def sort_key(v):
        try:
            return (0, int(v))
        except ValueError:
            return (1, v)
    return sorted(list(batches), key=sort_key, reverse=True)

def save_custom_batch(val: str):
    """Save a custom batch to local storage."""
    val = str(val).strip()
    if not val:
        return
    batches = set(get_saved_batches())
    batches.add(val)
    try:
        with open(_BATCH_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorted(list(batches)), f, indent=2)
    except Exception:
        pass

def delete_custom_batch(val: str):
    """Delete a custom batch from local storage."""
    val = str(val).strip()
    batches = [b for b in get_saved_batches() if b != val]
    try:
        with open(_BATCH_FILE, 'w', encoding='utf-8') as f:
            json.dump(batches, f, indent=2)
    except Exception:
        pass
