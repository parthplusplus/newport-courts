#!/usr/bin/env python3
"""
Newport Racquet Club – Pickleball Court Availability Scraper
No third-party dependencies — uses only Python's built-in urllib.
"""

import json
import ssl
import urllib.request
import urllib.parse
from datetime import date, timedelta, datetime

ssl._create_default_https_context = ssl._create_unverified_context

# ── Config ────────────────────────────────────────────────────────────────────
MERCHANT_ID  = "860dcffb-7bd4-4332-8600-f7b0021b722c"
LOCATION_ID  = "e2d2d26e-f054-4694-afac-0aa0421600a4"
EVENT_ID     = "7fe27a8a-22a1-4282-9a07-07fc144ae0b2"
CDT          = "2026-05-30T12:59:08-04:00"

BASE_URL = "https://api-partners.waivermaster.com/wmreservations/book"
QS       = f"{MERCHANT_ID}|{LOCATION_ID}|{EVENT_ID}"

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:145.0) Gecko/20100101 Firefox/145.0",
    "Accept":          "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Origin":          "https://reservations.waivermaster.com",
    "Referer":         "https://reservations.waivermaster.com/",
}

ALL_SLOTS = [
    "09:00", "10:00", "11:00", "12:00", "13:00",
    "14:00", "15:00", "16:00", "17:00", "18:00", "19:00",
]

SLOT_LABELS = {
    "09:00": "9:00am-10:00am",
    "10:00": "10:00am-11:00am",
    "11:00": "11:00am-12:00pm",
    "12:00": "12:00pm-1:00pm",
    "13:00": "1:00pm-2:00pm",
    "14:00": "2:00pm-3:00pm",
    "15:00": "3:00pm-4:00pm",
    "16:00": "4:00pm-5:00pm",
    "17:00": "5:00pm-6:00pm",
    "18:00": "6:00pm-7:00pm",
    "19:00": "7:00pm-8:00pm",
}

COURT_NAMES = {
    "mtg79cscgepn1-eqdapa9rhhwxw": "Court 1",
    "mtg79cscgepn1-zkb73w3m0epj2": "Court 2",
    "mtg79cscgepn1-3akr76e0mw9xp": "Court 3",
    "mtg79cscgepn1-4crbzx9j5yrp8": "Court 4",
}

# ── Scraper ───────────────────────────────────────────────────────────────────

def get_slot_availability(target_date, timeslot):
    # Build URL manually — urlencode encodes | as %7C which breaks the qs param
    other = urllib.parse.urlencode({
        "cdt":      CDT,
        "act":      "get_products",
        "date":     target_date.strftime("%Y-%m-%d"),
        "timeslot": timeslot,
    })
    url = f"{BASE_URL}?qs={QS}&{other}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def get_reservable_end(data):
    """Read reservable_to from the API response and return it as a date."""
    try:
        reservable_to = data["success"]["data"]["event"]["status"]["reservable_to"]
        return datetime.strptime(reservable_to, "%Y-%m-%d").date()
    except (KeyError, TypeError, ValueError):
        # Fall back to 7 days if field is missing
        return date.today() + timedelta(days=6)


def parse_availability(data):
    results = []
    try:
        products = data["success"]["data"]["event"]["products"]
    except (KeyError, TypeError):
        return results

    for p in products:
        p_id  = p.get("p_id", "")
        name  = COURT_NAMES.get(p_id, p.get("p_name", p_id))
        limit = p.get("qty_limit", {})
        cap   = limit.get("slot", 0)
        sold  = limit.get("slot_sold_qty", 0)
        avail = cap - sold if cap is not None else None
        results.append({
            "court":     name,
            "capacity":  cap,
            "sold":      sold,
            "available": avail,
            "free":      avail > 0 if avail is not None else False,
        })
    return results


def slots_to_scrape(target_date):
    dow = target_date.weekday()  # 0=Mon, 6=Sun
    if dow < 5:  # weekday: 5pm-8pm
        return [s for s in ALL_SLOTS if int(s.split(":")[0]) >= 17]
    else:        # weekend: 10am-12pm and 4pm-8pm
        return [s for s in ALL_SLOTS if 10 <= int(s.split(":")[0]) <= 11 or 16 <= int(s.split(":")[0]) <= 19]


def scrape_date_range(start, end):
    rows = []
    current = start
    while current <= end:
        slots = slots_to_scrape(current)
        print(f"Scraping {current} ({len(slots)} slots) ...", end=" ", flush=True)
        for slot in slots:
            try:
                data   = get_slot_availability(current, slot)
                courts = parse_availability(data)
                for c in courts:
                    rows.append({
                        "date":       current.strftime("%Y-%m-%d"),
                        "slot":       slot,
                        "slot_label": SLOT_LABELS[slot],
                        **c,
                    })
            except Exception as e:
                print(f"\n  WARNING {current} {slot}: {e}")
        print("done")
        current += timedelta(days=1)
    return rows


def print_summary(rows):
    print("\n" + "=" * 70)
    print(f"{'DATE':<12} {'SLOT':<22} {'COURT':<10} {'AVAIL':<8} STATUS")
    print("=" * 70)
    for r in rows:
        status = "Open" if r["free"] else "Full"
        print(f"{r['date']:<12} {r['slot_label']:<22} {r['court']:<10} "
              f"{r['available']:<8} {status}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    today = date.today()

    # Fetch one slot just to read the reservable_to date from the API
    print("Checking booking window from API...")
    try:
        probe = get_slot_availability(today, "17:00")
        end   = get_reservable_end(probe)
        print(f"API reservable window: {today} to {end}\n")
    except Exception as e:
        end = today + timedelta(days=6)
        print(f"Could not read window from API ({e}), defaulting to 7 days\n")

    rows = scrape_date_range(today, end)

    open_slots = [r for r in rows if r["free"]]
    print_summary(open_slots)

    with open("availability.json", "w") as f:
        json.dump(rows, f, indent=2)
    print(f"\nSaved to availability.json")
    print(f"Found {len(open_slots)} open court-slots out of {len(rows)} total.")
