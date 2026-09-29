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

ALLOWED_ACADEMIC_TYPES = ("program", "branch", "lecture")
