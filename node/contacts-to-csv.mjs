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
const COLUMNS = ['domain', 'companyName', 'status', 'emails', 'emailTypes', 'phones', 'address', 'addressSourceUrl',
    'contactPageUrl', ...NETWORKS, 'website', 'failureReason', 'input'];

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
    const socials = row.socials ?? {};
    return {
        ...row,
        emails: emails.map((e) => e.email).join('; '),
        emailTypes: emails.map((e) => e.type ?? '').join('; '),
        phones: (row.phones ?? []).map((p) => p.e164 ?? p.number ?? '').join('; '),
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
