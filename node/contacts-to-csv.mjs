// Company websites in, one CSV row per company: emails, phones, social profiles and postal address.
// Uses the hiver/company-contact-details Actor on Apify.
//
//   npm install
//   export APIFY_TOKEN=...   # Apify Console > Settings > API & Integrations
//   node contacts-to-csv.mjs plausible.io posthog.com hetzner.com
//   node contacts-to-csv.mjs --file domains.txt --out leads.csv
//
// A domain list file has one company website per line (blank lines and lines starting with # are skipped).
import { readFileSync, writeFileSync } from 'node:fs';
import { parseArgs } from 'node:util';
import { ApifyClient } from 'apify-client';

const ACTOR = 'hiver/company-contact-details';
const NETWORKS = ['linkedin', 'x', 'facebook', 'instagram', 'youtube', 'github', 'tiktok'];
const COLUMNS = ['domain', 'companyName', 'status', 'reviewFirst', 'emails', 'emailTypes', 'emailFoundVia', 'phones',
    'phoneFoundVia', 'address', 'addressSourceUrl', 'addressFoundVia', 'contactPageUrl', ...NETWORKS, 'website',
    'failureReason', 'input'];

// How each value was read (the Actor's foundVia):
//   structured_data      the site's JSON-LD / schema.org data
//   link                 a mailto: or tel: link
//   address_tag          an HTML <address> element
//   decoded_obfuscation  hidden from bots: Cloudflare email protection or "info [at] example [dot] com"
//   page_text            plain text on the page
// reviewFirst = "yes" when any value in the row was read in one of these ways. This is an example rule, not a
// measured confidence score: edit the set to match how much checking your list needs.
const REVIEW_IF = new Set(['page_text', 'decoded_obfuscation']);

const { values: opt, positionals } = parseArgs({
    allowPositionals: true,
    options: {
        file: { type: 'string' }, // one company website per line
        'max-pages': { type: 'string', default: '5' }, // pages read per website, 1-12
        country: { type: 'string' }, // default phone country, e.g. US or DE
        'max-charge': { type: 'string', default: '1.00' }, // stop the run once it has cost this many USD
        out: { type: 'string', default: 'contacts.csv' },
    },
});

let domains = [...positionals];
if (opt.file) {
    domains.push(...readFileSync(opt.file, 'utf8').split(/\r?\n/).map((l) => l.trim())
        .filter((l) => l && !l.startsWith('#')));
}
const seen = new Set();
domains = domains.filter((d) => !seen.has(d.toLowerCase()) && seen.add(d.toLowerCase()));
if (!domains.length) throw new Error('Give at least one company website, or --file domains.txt');
if (!process.env.APIFY_TOKEN) throw new Error('Set APIFY_TOKEN (Apify Console > Settings > API & Integrations).');

const input = {
    domains,
    maxPagesPerSite: Number(opt['max-pages']),
    ...(opt.country && { defaultCountry: opt.country }),
};

// APIFY_API_BASE_URL is only for testing against a mock server; leave it unset.
const client = new ApifyClient({ token: process.env.APIFY_TOKEN, baseUrl: process.env.APIFY_API_BASE_URL });
const run = await client.actor(ACTOR).call(input, { maxTotalChargeUsd: Number(opt['max-charge']) });
if (run.status !== 'SUCCEEDED') throw new Error(`Run did not succeed: ${run.status} ${run.statusMessage ?? ''}`);

// One flat CSV row per company. Lists are joined with '; ' in the order the Actor returns them.
const flatten = (row) => {
    const emails = row.emails ?? [];
    const phones = row.phones ?? [];
    const socials = row.socials ?? {};
    const methods = [...emails, ...phones].map((v) => v.foundVia).concat(row.addressFoundVia);
    return {
        ...row,
        reviewFirst: methods.some((m) => REVIEW_IF.has(m)) ? 'yes' : '',
        emails: emails.map((e) => e.email).join('; '),
        emailTypes: emails.map((e) => e.type ?? '').join('; '),
        emailFoundVia: emails.map((e) => e.foundVia ?? '').join('; '),
        phones: phones.map((p) => p.e164 ?? p.number ?? '').join('; '),
        phoneFoundVia: phones.map((p) => p.foundVia ?? '').join('; '),
        ...Object.fromEntries(NETWORKS.map((n) => [n, socials[n]])),
    };
};
const cell = (v) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

const { items } = await client.dataset(run.defaultDatasetId).listItems();
const rows = items.map(flatten);
writeFileSync(opt.out, `${[COLUMNS.join(','), ...rows.map((r) => COLUMNS.map((c) => cell(r[c])).join(','))].join('\r\n')}\r\n`);

const counts = {};
for (const r of items) counts[r.status ?? 'unknown'] = (counts[r.status ?? 'unknown'] ?? 0) + 1;
const summary = Object.entries(counts).sort().map(([s, n]) => `${n} ${s}`).join(', ');
console.log(`${items.length} companies -> ${opt.out} (${summary})`);
console.log('Failed sites are listed with a failureReason and are not charged.');
