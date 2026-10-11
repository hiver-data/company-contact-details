"""Company websites in, one CSV row per company: emails, phones, social profiles and postal address.
Uses the hiver/company-contact-details Actor on Apify.

    pip install -r requirements.txt
    export APIFY_TOKEN=...   # Apify Console > Settings > API & Integrations
    python contacts_to_csv.py plausible.io posthog.com hetzner.com
    python contacts_to_csv.py --file domains.txt --out leads.csv

A domain list file has one company website per line (blank lines and lines starting with # are skipped).
"""
import argparse
import csv
import os
import sys
from decimal import Decimal

from apify_client import ApifyClient

ACTOR = "hiver/company-contact-details"
NETWORKS = ["linkedin", "x", "facebook", "instagram", "youtube", "github", "tiktok"]
COLUMNS = (["domain", "companyName", "status", "reviewFirst", "emails", "emailTypes", "emailFoundVia", "phones",
            "phoneFoundVia", "address", "addressSourceUrl", "addressFoundVia", "contactPageUrl"]
           + NETWORKS + ["website", "failureReason", "input"])

# How each value was read (the Actor's foundVia):
#   structured_data      the site's JSON-LD / schema.org data
#   link                 a mailto: or tel: link
#   address_tag          an HTML <address> element
#   decoded_obfuscation  hidden from bots: Cloudflare email protection or "info [at] example [dot] com"
#   page_text            plain text on the page
# reviewFirst = "yes" when any value in the row was read in one of these ways. This is an example rule, not a
# measured confidence score: edit the set to match how much checking your list needs.
REVIEW_IF = {"page_text", "decoded_obfuscation"}


def read_domains(args) -> list[str]:
    domains = list(args.domains)
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            domains += [line.strip() for line in f if line.strip() and not line.lstrip().startswith("#")]
    seen, out = set(), []
    for d in domains:
        if d.lower() not in seen:
            seen.add(d.lower())
            out.append(d)
    return out


def flatten(row: dict) -> dict:
    """One flat CSV row per company. Lists are joined with '; ' in the order the Actor returns them."""
    emails = row.get("emails") or []
    phones = row.get("phones") or []
    socials = row.get("socials") or {}
    flat = {k: row.get(k) for k in ("domain", "companyName", "status", "address", "addressSourceUrl",
                                     "contactPageUrl", "website", "failureReason", "input")}
    flat["emails"] = "; ".join(e["email"] for e in emails)
    flat["emailTypes"] = "; ".join(e.get("type") or "" for e in emails)
    flat["emailFoundVia"] = "; ".join(e.get("foundVia") or "" for e in emails)
    flat["phones"] = "; ".join(p.get("e164") or p.get("number") or "" for p in phones)
    flat["phoneFoundVia"] = "; ".join(p.get("foundVia") or "" for p in phones)
    flat["addressFoundVia"] = row.get("addressFoundVia")
    methods = [v.get("foundVia") for v in emails + phones] + [row.get("addressFoundVia")]
    flat["reviewFirst"] = "yes" if REVIEW_IF.intersection(methods) else ""
    for net in NETWORKS:
        flat[net] = socials.get(net)
    return flat


def main() -> None:
    p = argparse.ArgumentParser(description="Contact details from company websites to one CSV row per company.")
    p.add_argument("domains", nargs="*", help="company domains or URLs, e.g. plausible.io https://posthog.com")
    p.add_argument("--file", help="text file with one company website per line")
    p.add_argument("--max-pages", type=int, default=5, help="pages read per website, 1-12 (default 5)")
    p.add_argument("--country", help="default phone country for numbers without +code, e.g. US or DE")
    p.add_argument("--max-charge", type=Decimal, default=Decimal("1.00"),
                   help="stop the run once it has cost this many USD (default 1.00)")
    p.add_argument("--out", default="contacts.csv")
    args = p.parse_args()

    domains = read_domains(args)
    if not domains:
        sys.exit("Give at least one company website, or --file domains.txt")
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        sys.exit("Set APIFY_TOKEN (Apify Console > Settings > API & Integrations).")

    run_input = {"domains": domains, "maxPagesPerSite": args.max_pages}
    if args.country:
        run_input["defaultCountry"] = args.country

    # APIFY_API_BASE_URL is only for testing against a mock server; leave it unset.
    client = ApifyClient(token, api_url=os.environ.get("APIFY_API_BASE_URL", "https://api.apify.com"))
    run = client.actor(ACTOR).call(run_input=run_input, max_total_charge_usd=args.max_charge)
    if run is None or run.status != "SUCCEEDED":
        sys.exit(f"Run did not succeed: {run.status if run else 'not started'} {run.status_message if run else ''}")

    counts: dict[str, int] = {}
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in client.dataset(run.default_dataset_id).iterate_items():
            writer.writerow(flatten(row))
            counts[row.get("status") or "unknown"] = counts.get(row.get("status") or "unknown", 0) + 1
    total = sum(counts.values())
    summary = ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
    print(f"{total} companies -> {args.out} ({summary})")
    print("Failed sites are listed with a failureReason and are not charged.")


if __name__ == "__main__":
    main()
