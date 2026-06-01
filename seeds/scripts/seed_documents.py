"""Seed demo documents through the real API pipeline.

Unlike `seed_dev.py` (which writes rows directly), this script drives the
actual HTTP endpoints so the demo data is produced by the same code path a
user exercises: upload -> OCR -> classify -> extract -> human approve ->
workflow transition -> tasks + outreach. That keeps the inbox, review queue,
task board, outreach log, and analytics all populated with believable data.

What it produces (against the default seed clinic, steel-city-cardiology):

  - 8 referrals + 4 discharges uploaded   -> Inbox
  - some extractions left unapproved       -> Review queue
  - 5 referrals approved; 3 of them moved  -> Referral workflow
      to ready_to_schedule                   (emits tasks + outreach)
  - 3 discharges approved -> patient_contacted (closed loop: tasks + outreach)

Prerequisites:
  - The API must be running (`make api` or `make dev`) on API_URL.
  - Ollama must be running with the extraction model pulled
    (`ollama serve`; medgemma1.5 by default).
  - A fresh `make seed` (so the clinic + login exist). Intended to run once on
    a clean seed; re-running skips files already uploaded (resume-friendly).

Run with: make seed-documents
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import httpx

# ─── Config ────────────────────────────────────────────────────────────

API_URL = os.getenv("API_URL", "http://localhost:8000")
ADMIN_EMAIL = "admin@steel-city-cardiology.example.com"
ADMIN_PASSWORD = "suture_dev_123"

_DOCS_DIR = Path(__file__).resolve().parent.parent / "documents"

# Which synthetic PDFs to push through the pipeline.
REFERRAL_FILES = [f"REF-{n:03d}" for n in range(1, 9)]  # REF-001..008
DISCHARGE_FILES = [f"DIS-{n:03d}" for n in range(1, 5)]  # DIS-001..004

# How far to drive each stream. The rest stay as raw documents / pending
# extractions so the inbox + review queue are not empty.
APPROVE_REFERRALS = 5  # approve the first N referral extractions
READY_REFERRALS = 3  # of those approved, move N to ready_to_schedule
APPROVE_DISCHARGES = 3  # approve the first N discharges (-> patient_contacted)

# Upload + extract is slow (OCR + local LLM). Give each call generous headroom.
_TIMEOUT = httpx.Timeout(300.0)


# ─── HTTP helpers ──────────────────────────────────────────────────────


async def _login(client: httpx.AsyncClient) -> dict[str, Any]:
    resp = await client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    resp.raise_for_status()
    return resp.json()


async def _existing_doc_names(client: httpx.AsyncClient, headers: dict[str, str]) -> set[str]:
    resp = await client.get("/api/documents?limit=200", headers=headers)
    resp.raise_for_status()
    return {item["file_name"] for item in resp.json().get("items", [])}


async def _upload(
    client: httpx.AsyncClient, headers: dict[str, str], pdf_path: Path
) -> dict[str, Any] | None:
    with pdf_path.open("rb") as fh:
        files = {"file": (pdf_path.name, fh, "application/pdf")}
        resp = await client.post("/api/documents/upload", headers=headers, files=files)
    if resp.status_code != 201:
        print(f"  ! upload {pdf_path.name} failed: {resp.status_code} {resp.text[:140]}")
        return None
    return resp.json()


async def _extraction_map(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """document_id -> extraction list item."""
    resp = await client.get("/api/extractions/?limit=200", headers=headers)
    resp.raise_for_status()
    return {item["document_id"]: item for item in resp.json().get("items", [])}


async def _approve(
    client: httpx.AsyncClient, headers: dict[str, str], ext_id: str
) -> dict[str, Any] | None:
    resp = await client.post(f"/api/extractions/{ext_id}/approve", headers=headers)
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 409:  # already approved on a prior run
        return None
    print(f"  ! approve {ext_id[:8]} failed: {resp.status_code} {resp.text[:140]}")
    return None


async def _transition_referral(
    client: httpx.AsyncClient, headers: dict[str, str], referral_id: str, target: str
) -> bool:
    resp = await client.post(
        f"/api/referrals/{referral_id}/transition",
        headers=headers,
        json={"target": target},
    )
    if resp.status_code == 200:
        return True
    print(f"  ! transition {referral_id[:8]} -> {target} failed: "
          f"{resp.status_code} {resp.text[:140]}")
    return False


# ─── Pipeline ──────────────────────────────────────────────────────────


async def _upload_set(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    label: str,
    subdir: str,
    stems: list[str],
    already: set[str],
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for stem in stems:
        name = f"{stem}.pdf"
        path = _DOCS_DIR / subdir / name
        if not path.exists():
            print(f"  ! missing {path} — skipping")
            continue
        if name in already:
            print(f"  · {name} already uploaded — skipping")
            continue
        print(f"  ↑ uploading {name} ({label}) — OCR + classify + extract ...")
        doc = await _upload(client, headers, path)
        if doc is not None:
            print(f"    → {doc['status']} / {doc['classification']} "
                  f"(conf {doc['classification_confidence']})")
            docs.append(doc)
    return docs


async def seed_documents() -> None:
    async with httpx.AsyncClient(base_url=API_URL, timeout=_TIMEOUT) as client:
        session = await _login(client)
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        print(f"Authenticated as {ADMIN_EMAIL} (clinic {session['active_clinic_id']})\n")

        already = await _existing_doc_names(client, headers)

        print("── Uploading referrals ──")
        referral_docs = await _upload_set(
            client, headers, label="referral", subdir="referrals",
            stems=REFERRAL_FILES, already=already,
        )
        print("\n── Uploading discharges ──")
        discharge_docs = await _upload_set(
            client, headers, label="discharge", subdir="discharges",
            stems=DISCHARGE_FILES, already=already,
        )

        # Map documents -> extractions (covers this run's uploads).
        ext_map = await _extraction_map(client, headers)

        # ── Drive referrals: approve, then push a few to ready_to_schedule ──
        print("\n── Approving referrals + advancing workflow ──")
        ready_done = 0
        approved_refs = 0
        for doc in referral_docs[:APPROVE_REFERRALS]:
            ext = ext_map.get(doc["id"])
            if ext is None:
                continue
            result = await _approve(client, headers, ext["id"])
            if result is None or not result.get("referral_id"):
                continue
            approved_refs += 1
            print(f"  ✓ approved {doc['file_name']} -> referral {result['referral_id'][:8]} "
                  f"(needs_review)")
            if ready_done < READY_REFERRALS:
                if await _transition_referral(
                    client, headers, result["referral_id"], "ready_to_schedule"
                ):
                    ready_done += 1
                    print("    ⇒ ready_to_schedule (tasks + outreach emitted)")

        # ── Drive discharges: approve -> patient_contacted (closed loop) ──
        print("\n── Approving discharges (closed loop) ──")
        approved_dis = 0
        for doc in discharge_docs[:APPROVE_DISCHARGES]:
            ext = ext_map.get(doc["id"])
            if ext is None:
                continue
            result = await _approve(client, headers, ext["id"])
            if result is None or not result.get("discharge_summary_id"):
                continue
            approved_dis += 1
            print(f"  ✓ approved {doc['file_name']} -> discharge "
                  f"{result['discharge_summary_id'][:8]} (patient_contacted; "
                  f"tasks + outreach emitted)")

        await _print_summary(
            client, headers,
            referrals_ready=ready_done,
            referrals_approved=approved_refs,
            discharges_approved=approved_dis,
        )


async def _count(client: httpx.AsyncClient, headers: dict[str, str], path: str) -> int:
    resp = await client.get(path, headers=headers)
    resp.raise_for_status()
    body = resp.json()
    return int(body.get("total", len(body.get("items", []))))


async def _print_summary(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    referrals_ready: int,
    referrals_approved: int,
    discharges_approved: int,
) -> None:
    docs = await _count(client, headers, "/api/documents?limit=1")
    needs_review = await _count(client, headers, "/api/extractions/?needs_review=true&limit=1")
    tasks = await _count(client, headers, "/api/tasks/?limit=1")
    # /api/outreach has no `total` field — fetch the page and count items.
    outreach = await _count(client, headers, "/api/outreach?limit=200")

    dash = await client.get("/api/analytics/dashboard", headers=headers)
    leakage_line = ""
    if dash.status_code == 200:
        lk = dash.json().get("leakage") or {}
        scored = len(lk.get("rows") or [])
        leakage_line = (
            f"  leakage: {scored} scored / {lk.get('at_risk_count', '?')} at-risk"
        )

    print()
    print("┌────────────────────────────────────────────────────┐")
    print("│ Suture demo documents seeded (via API pipeline)    │")
    print("├────────────────────────────────────────────────────┤")
    print(f"│ Documents in inbox:        {docs:>3}                     │")
    print(f"│ Extractions needs_review:  {needs_review:>3}  (review queue)     │")
    print(f"│ Referrals approved:        {referrals_approved:>3}                     │")
    print(f"│   → ready_to_schedule:     {referrals_ready:>3}                     │")
    print(f"│ Discharges -> contacted:   {discharges_approved:>3}                     │")
    print(f"│ Tasks generated:           {tasks:>3}                     │")
    print(f"│ Outreach attempts:         {outreach:>3}                     │")
    print("├────────────────────────────────────────────────────┤")
    if leakage_line:
        print(f"│ analytics ready —{leakage_line:<35}│")
    print("│ Open http://localhost:3000 to walk the screens.    │")
    print("└────────────────────────────────────────────────────┘")


if __name__ == "__main__":
    asyncio.run(seed_documents())
