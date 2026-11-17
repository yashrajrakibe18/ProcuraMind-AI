"""Create a demo workspace in a RUNNING API using the synthetic samples, then run the analysis.

Usage: python scripts/seed_demo_data.py [--api-url http://localhost:8000/api/v1]
Demo account: demo@procureai.local / DemoPassw0rd!   (local development only; change/remove for any shared deployment)
"""

import argparse
import time

import httpx

from procureai.samples.generate import all_samples

EMAIL, PASSWORD = "demo@procureai.local", "DemoPassw0rd!"


def main(base: str) -> None:
    with httpx.Client(base_url=base, timeout=60) as c:
        c.post("/auth/register", json={"email": EMAIL, "full_name": "Demo User", "password": PASSWORD})
        r = c.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        r.raise_for_status()
        c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
        pid = c.post(
            "/projects",
            json={"title": "Demo: 50 business laptops (synthetic)", "description": "Synthetic documents only."},
        ).json()["id"]
        for name, blob in all_samples().items():
            c.post(
                f"/projects/{pid}/documents", files={"file": (name, blob)}, data={"document_type": "auto"}
            ).raise_for_status()
        for _ in range(60):
            docs = c.get(f"/projects/{pid}/documents").json()
            if all(d["processing_status"] != "pending" for d in docs):
                break
            time.sleep(1)
        print("requirements:", c.post(f"/projects/{pid}/requirements/extract").json()["created"])
        c.post(f"/projects/{pid}/requirements/confirm-all")
        run = c.post(f"/projects/{pid}/analysis-runs", json={"auto_confirm": False}).json()
        while run["status"] in ("queued", "running"):
            time.sleep(1)
            run = c.get(f"/analysis-runs/{run['id']}").json()
        print("run status:", run["status"], "| open review items:", run["summary"].get("open_review_items"))
        print(f"Sign in as {EMAIL} and open the project 'Demo: 50 business laptops (synthetic)'.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", default="http://localhost:8000/api/v1")
    main(ap.parse_args().api_url)
