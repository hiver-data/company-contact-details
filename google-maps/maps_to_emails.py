"""Google Maps results in, emails out: one CSV row per place with its emails, phones, socials and address.

Uses two Apify Actors:
  hiver/company-contact-details      reads each place's website (this repo's Actor)
  compass/crawler-google-places      Apify's Google Maps Scraper (only if you ask this script to search Maps)

    pip install -r requirements.txt
    export APIFY_TOKEN=...   # Apify Console > Settings > API & Integrations

    # You already have a Google Maps Scraper run: pass its dataset ID (Storage > Datasets, or the run's Output tab)
    python maps_to_emails.py --dataset-id YOUR_DATASET_ID

    # Or search Google Maps first, then enrich the places it finds
    python maps_to_emails.py --search "dentist" --location "Austin, Texas, USA" --max-places 50
"""
import argparse
import csv
import os
import sys
from decimal import Decimal

from apify_client import ApifyClient

CONTACTS_ACTOR = "hiver/company-contact-details"
MAPS_ACTOR = "compass/crawler-google-places"
NETWORKS = ["linkedin", "x", "facebook", "instagram", "youtube", "github", "tiktok"]
COLUMNS = (["placeTitle", "placeCategory", "placeAddress", "placePhone", "placeUrl", "website", "status",
            "emails", "emailTypes", "phones", "address", "addressSourceUrl", "contactPageUrl"]
           + NETWORKS + ["failureReason", "placeId"])


def flatten(row: dict) -> dict:
    """One CSV row per place: the place's own Google Maps fields first, then what its website publishes."""
    place = row.get("place") or {}
    emails = row.get("emails") or []
    phones = row.get("phones") or []
    socials = row.get("socials") or {}
    flat = {
        "placeTitle": place.get("title"),
        "placeCategory": place.get("categoryName"),
        "placeAddress": place.get("address"),
        "placePhone": place.get("phone"),
        "placeUrl": place.get("url"),
        "placeId": place.get("placeId"),
        "emails": "; ".join(e["email"] for e in emails),
        "emailTypes": "; ".join(e.get("type") or "" for e in emails),
        "phones": "; ".join(p.get("e164") or p.get("number") or "" for p in phones),
    }
    for key in ("website", "status", "address", "addressSourceUrl", "contactPageUrl", "failureReason"):
        flat[key] = row.get(key)
    for net in NETWORKS:
        flat[net] = socials.get(net)
    return flat


def run_maps(client: ApifyClient, args) -> str:
    """Run Apify's Google Maps Scraper and return its dataset ID."""
    maps_input = {
        "searchStringsArray": [args.search],
        "locationQuery": args.location,
        "maxCrawledPlacesPerSearch": args.max_places,
        "language": "en",
    }
    print(f"Searching Google Maps: {args.search!r} in {args.location!r} (up to {args.max_places} places)...")
    run = client.actor(MAPS_ACTOR).call(run_input=maps_input, max_total_charge_usd=args.max_charge)
    if run is None or run.status != "SUCCEEDED":
        sys.exit(f"Maps run did not succeed: {run.status if run else 'not started'}")
    print(f"Maps dataset: {run.default_dataset_id}")
    return run.default_dataset_id


def main() -> None:
    p = argparse.ArgumentParser(description="Google Maps places to one CSV row per place with emails and phones.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--dataset-id", help="ID of an existing Google Maps Scraper dataset (or any dataset with a website field)")
    src.add_argument("--search", help="search Google Maps first, e.g. 'dentist' (needs --location)")
    p.add_argument("--location", help="where to search, e.g. 'Austin, Texas, USA'")
    p.add_argument("--max-places", type=int, default=50, help="places to collect from Google Maps (default 50)")
    p.add_argument("--website-field", default="website", help="field holding the website (default: website)")
    p.add_argument("--max-pages", type=int, default=5, help="pages read per website, 1-12 (default 5)")
    p.add_argument("--max-charge", type=Decimal, default=Decimal("1.00"),
                   help="stop each run once it has cost this many USD (default 1.00)")
    p.add_argument("--out", default="places_with_contacts.csv")
    args = p.parse_args()
    if args.search and not args.location:
        p.error("--search needs --location")

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        sys.exit("Set APIFY_TOKEN (Apify Console > Settings > API & Integrations).")
    # APIFY_API_BASE_URL is only for testing against a mock server; leave it unset.
    client = ApifyClient(token, api_url=os.environ.get("APIFY_API_BASE_URL", "https://api.apify.com"))

    dataset_id = args.dataset_id or run_maps(client, args)
    run_input = {"datasetId": dataset_id, "websiteField": args.website_field, "maxPagesPerSite": args.max_pages}
    print("Reading the websites of those places...")
    run = client.actor(CONTACTS_ACTOR).call(run_input=run_input, max_total_charge_usd=args.max_charge)
    if run is None or run.status != "SUCCEEDED":
        sys.exit(f"Contacts run did not succeed: {run.status if run else 'not started'} {run.status_message if run else ''}")

    counts: dict[str, int] = {}
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in client.dataset(run.default_dataset_id).iterate_items():
            writer.writerow(flatten(row))
            status = row.get("status") or "unknown"
            counts[status] = counts.get(status, 0) + 1
    total = sum(counts.values())
    summary = ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
    print(f"{total} places -> {args.out} ({summary})")
    print("Charged: one event per distinct website with status ok. Places without a website, social-only "
          "websites, unreachable sites and sites with nothing found are free.")


if __name__ == "__main__":
    main()
