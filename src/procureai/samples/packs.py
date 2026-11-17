"""SYNTHETIC sample files for the HR, Support and Operations platforms (used by tests and demos). Not real people or data."""

from __future__ import annotations

from pathlib import Path

JOB_DESCRIPTION = """Job Description: Backend Engineer

We are hiring a backend engineer to build internal data services.

Responsibilities
- Design and maintain REST APIs
- Review code and mentor juniors

Requirements:
- Python, SQL, Docker
- Experience with REST APIs and PostgreSQL
- 3+ years of professional experience

Nice to have:
- Kubernetes, AWS, Redis
"""

RESUMES = {
    "resume_arjun.txt": "Arjun Mehta\nBackend developer, 5 years of experience.\nSkills: Python, SQL, Docker, PostgreSQL, REST APIs, Redis, AWS\nProfessional experience: built REST APIs at a fintech startup.\nEducation: B.Tech Computer Science\n",
    "resume_neha.txt": "Neha Iyer\nSoftware engineer with 2 years of experience.\nSkills: Python, Flask, SQL, Git\nWork experience: maintained internal tools.\nEducation: B.Sc Computer Science\n",
    "resume_kabir.txt": "Kabir Shah\nData analyst, 4 years of experience.\nSkills: Excel, Tableau, SQL\nWork experience: dashboards and reporting.\nEducation: MBA\n",
}

KNOWLEDGE_BASE = """Help Center: Refunds and Billing

Refund policy. Customers can request a refund within 30 days of purchase. Refunds are returned to the original payment method within 5 to 7 business days.

Duplicate charges. If you were charged twice for the same order, contact support with your order number. The duplicate charge is refunded in full within 5 to 7 business days after verification.

Password reset. Use the Forgot password link on the login page. A reset link is emailed and expires after 60 minutes.

Support hours. Support is available Monday to Friday, 9am to 6pm.
"""

MEETING_NOTES = """Meeting notes: Project Falcon weekly sync
Attendees: Asha, Ravi, Meera
Agenda: release plan, vendor delivery, budget

Decision: we agreed to move the release to 2026-12-15.
Action: Ravi will confirm the vendor delivery date by 2026-12-01
Meera to update the budget forecast by 2026-11-20
Action: send the test report to the client
The vendor delivery is delayed by two weeks and the release is blocked on the new server.
There is a risk that the budget will overrun because of extra testing.
Who owns the security review? TBD
"""


def tickets_csv() -> str:
    rows = [
        (1, "Charged twice for my order", "I was charged twice for order 1042. This is unacceptable, please refund me"),
        (2, "Cannot login", "I cannot access my account, password reset email never arrives. Urgent"),
        (3, "Where is my package", "My delivery is late and tracking has not updated for a week"),
        (4, "Feature idea", "It would be great if you could add dark mode"),
        (5, "Website is down", "The checkout page shows an error and the site is down for all our staff. Critical"),
        (6, "Charged twice", "I was charged twice for order 1042. Unacceptable, refund me please"),
        (7, "Thanks", "Thank you, the support team was helpful and the problem is resolved"),
        (8, "Invoice copy", "Could you send me a copy of my last invoice"),
    ]
    return "ticket_id,subject,description\n" + "\n".join(f'{i},"{s}","{d}"' for i, s, d in rows) + "\n"


def write_pack_samples(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    files = {"job_description.txt": JOB_DESCRIPTION, "knowledge_base_support.txt": KNOWLEDGE_BASE, "meeting_notes.txt": MEETING_NOTES, "tickets.csv": tickets_csv(), **RESUMES}
    out = []
    for name, text in files.items():
        p = directory / name
        p.write_text(text, encoding="utf-8")
        out.append(p)
    return out


if __name__ == "__main__":
    for f in write_pack_samples(Path("data/samples/platforms")):
        print(f)
