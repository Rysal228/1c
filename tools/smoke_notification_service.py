"""Read-only checks of an installed 1C notification API (no MAX messages).

Run on the backend host with ONEC_NOTIFICATIONS_SERVICE_KEY in the environment.
No key, payload, MAX ID or HTTP response body is printed.
"""
import argparse
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Private 1C API, ending in /hs/api")
    args = parser.parse_args()
    key = os.environ.get("ONEC_NOTIFICATIONS_SERVICE_KEY", "")
    if not key:
        parser.error("Set ONEC_NOTIFICATIONS_SERVICE_KEY in the environment")
    base = args.base_url.rstrip("/") + "/notifications/orders"
    opener = build_opener(NoRedirect())

    def read(url, token=None):
        headers = {"Accept": "application/json"}
        if token is not None:
            headers["X-ServiceCar-Notifications-Key"] = token
        try:
            with opener.open(Request(url, headers=headers), timeout=30) as r:
                return r.status, json.load(r)
        except HTTPError as exc:
            return exc.code, None

    wrong = ("A" if key[0] != "A" else "B") + key[1:]
    for label, url, token in (
        ("missing key", base, None),
        ("wrong key", base, wrong),
        ("actor is not authentication", base + "?actorId=00000000-0000-0000-0000-000000000000&actorRole=admin", None),
        ("key in query is not authentication", base + "?key=not-a-real-key", None),
    ):
        status, _ = read(url, token)
        if status != 401:
            raise RuntimeError(f"{label}: expected 401, got {status}")
        print(f"PASS {label}")
    # Header names are case-insensitive; secret values must be case-sensitive.
    if key.swapcase() != key:
        status, _ = read(base, key.swapcase())
        if status != 401:
            raise RuntimeError("Changed-case key was accepted")
        print("PASS case-sensitive secret")
    status, rows = read(base, key)
    if status != 200 or not isinstance(rows, list):
        raise RuntimeError(f"Service feed failed: HTTP {status}")
    allowed = {"id", "car", "ownerId", "orderNumber", "carName", "status", "workStatus"}
    for row in rows:
        if not isinstance(row, dict) or set(row) != allowed:
            raise RuntimeError("Unexpected feed fields")
        UUID(row["id"]); UUID(row["car"])
        if row["ownerId"] is not None:
            UUID(row["ownerId"])
    print(f"PASS service feed: {len(rows)} orders")
    identifier = rows[0]["id"] if rows else "00000000-0000-0000-0000-000000000000"
    url = base + f"/{identifier}/recipient"
    status, _ = read(url, wrong)
    if status != 401:
        raise RuntimeError("Recipient endpoint accepted wrong key")
    status, recipient = read(url, key)
    if rows:
        if status != 200 or recipient.get("id") != identifier:
            raise RuntimeError("Recipient endpoint returned incorrect order")
        if set(recipient) != {"id", "car", "ownerId", "eligible", "messengerUserId"}:
            raise RuntimeError("Unexpected recipient fields")
    elif status != 404:
        raise RuntimeError("Missing order must return 404")
    print("PASS recipient endpoint")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, URLError):
        raise SystemExit("FAIL notification service check (no credentials or payload logged)") from None
