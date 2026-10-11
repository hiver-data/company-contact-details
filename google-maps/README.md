# Google Maps results to emails

`maps_to_emails.py` turns Google Maps places into a CSV with one row per place: the place's own Google Maps fields (name, category, address, phone, Maps URL) next to the emails, phones, social profiles and postal address published on its website.

It uses [hiver/company-contact-details](https://apify.com/hiver/company-contact-details?utm_source=github&utm_campaign=google-maps-emails) on Apify, which reads a Google Maps Scraper dataset directly (input `datasetId`).

## Run it

You need an Apify account (the free plan includes $5 of usage a month) and its API token from Apify Console > Settings > API & Integrations. Python 3.11+:

```bash
cd google-maps
pip install -r requirements.txt
export APIFY_TOKEN=your_token

# You already ran a Google Maps scraper: pass the run's dataset ID
python maps_to_emails.py --dataset-id YOUR_DATASET_ID

# Or search Google Maps first (runs Apify's compass/crawler-google-places), then enrich what it finds
python maps_to_emails.py --search "dentist" --location "Austin, Texas, USA" --max-places 50
```

It writes `places_with_contacts.csv` (or `--out`). Options: `--website-field` (the field holding the website, default `website`; nested paths such as `contact.website` work), `--max-pages` (pages read per website, 1-12, default 5), `--max-charge` (each run stops once it has cost this many dollars; default $1.00).

## What you pay

The contacts Actor charges $2 per 1,000 websites where it found at least one contact detail ($1.70 to $1.90 on paid Apify plans). Places with no website, places whose website is only a Facebook or Instagram page, unreachable sites and sites with nothing found get a row and cost nothing. Places that share a website (chain locations) keep their own rows, and the website is charged once. If you use `--search`, the Google Maps Scraper run is billed separately at its own Store price.

## What the output looks like

These 5 rows come from the board's test run of build 0.2.10 on 2026-10-11 (a 5-place test dataset; the place names and addresses are test fixtures, the contacts are real), shortened:

```
placeTitle,website,status,emails,address,addressSourceUrl,linkedin,x
TEST FIXTURE place A: plausible.io (first place on this domain),https://plausible.io,ok,hello@plausible.io,"Västriku tn 2, 50403 Tartu",https://plausible.io/imprint,https://www.linkedin.com/company/plausible-analytics,https://x.com/PlausibleHQ
TEST FIXTURE place B: plausible.io (second place, same domain),https://plausible.io,ok,hello@plausible.io,"Västriku tn 2, 50403 Tartu",https://plausible.io/imprint,https://www.linkedin.com/company/plausible-analytics,https://x.com/PlausibleHQ
TEST FIXTURE place C: ...,https://...,ok,...
TEST FIXTURE place D: no website,,no_website,,,,,
TEST FIXTURE place E: Facebook page as website,https://www.facebook.com/AnchorBrewing,website_is_social_profile,,,,,
```

Apify recorded 2 charges for that run: one per distinct website with contacts found. Places A and B share plausible.io, so it was read and charged once; D and E were free.

## No code: run it after every Maps run

In your Google Maps scraper's Integrations tab in Apify Console, add hiver/company-contact-details as a run-Actor integration with this input, and Apify fills in each Maps run's dataset ID:

```json
{
  "datasetId": "{{resource.defaultDatasetId}}",
  "websiteField": "website",
  "maxItems": 100
}
```

## Limits

It reads each business's own website (home page plus contact, about, imprint/legal and support pages), not Google Maps itself. Company channels only: role mailboxes such as info@ and sales@, and business mailboxes the site publishes in its own structured data. No personal emails, guessing or verification. The first usable URL for a website is the one read, so chain locations get company-level contacts, not branch contacts. Use the data lawfully (GDPR, CAN-SPAM, PECR and similar).

The script was tested against a mock Apify API serving the real rows of that board test run; both modes (`--dataset-id` and `--search`) produced the same 5-row CSV.
