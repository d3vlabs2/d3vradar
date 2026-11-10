# Private beta workspaces (Radar 2.7)

Each approved Cloudflare Access login email has its own workspace. Radar verifies
JWT signature, issuer, audience, expiry, and email before selecting a database.
It does not trust an email header, profile contact email, URL parameter, or a
workspace ID sent by a browser. Approved accounts are created on first login.
Email matching is case-insensitive. Different email aliases are separate accounts.
Token validation follows the [Cloudflare Access validation guidance](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/).

## Upgrade your existing installation first

Keep your existing Cloudflare Access application restricted to you during upgrade.
Set these values in `~/jobradar/.env`, using your actual existing owner email:

```dotenv
RADAR_OWNER_EMAIL=owner@example.com
RADAR_ALLOWED_EMAILS=owner@example.com
```

Keep every other existing setting, especially RADAR_ENCRYPTION_KEY, unchanged.
Then run the normal updater:

```bash
bash ~/d3vradar-source/deploy/update-homelab.sh ~/jobradar
curl --fail http://127.0.0.1:3740/health
```

The updater now snapshots all workspace databases before changing code. The old
container must be running for this snapshot. The database archive is written to
`~/jobradar/backups`; .env must be backed up separately. Do not commit either backup.
The owner still uses the existing `/data/radar.sqlite`; it is not renamed or copied
into a friend's database. Verify your profile, documents, and applications after
updating. Health should show 2.7.0.

The first upgrade can infer the owner if exactly one email is allowed. If more than
one is allowed and no owner was configured or persisted, startup fails closed.
The owner binding is persisted encrypted. Changing allowlist order or signing in
first cannot take ownership. Changing RADAR_OWNER_EMAIL to somebody else fails;
this is not an account transfer tool.

## Invite a friend

1. Add the friend's exact sign-in email to RADAR_ALLOWED_EMAILS, preserving your
   own email and RADAR_OWNER_EMAIL:

   ```dotenv
   RADAR_ALLOWED_EMAILS=owner@example.com,friend@example.com
   ```

2. Recreate the application so it reads the changed environment:

   ```bash
   cd ~/jobradar
   sudo docker compose up -d --force-recreate --wait
   ```

3. In the existing Cloudflare Access application's Allow policy, add that same
   email to the allowed Emails rule. Keep it an explicit email allowlist.
4. Your friend opens your normal Radar hostname and signs in with that email.
   No separate subdomain, manual account creation, or local token is needed.
5. They review and save their own Profile answers before exporting an answer pack,
   upload their own documents, set their search preferences, and scan sources.

Both allowlists must permit a user. Don't enable an Everyone policy. RADAR_OWNER_EMAIL
only binds the legacy workspace; it does not grant an application-wide data browser.
The app has no interface for reading another person's documents or records.

## What is private and what is shared

Each workspace keeps its own profile, contact and commute addresses, application
answers, search settings, imported/edited jobs, saved statuses, application dates,
notes, resume and cover-letter uploads, drafts, queue, and scan history. Documents,
profile/settings, notes, and drafts remain encrypted at rest. A newly approved
friend does not inherit the owner's settings or answer pack.

Public connector responses are cached for 12 hours and reused for matching feed
queries. Each workspace gets its own listing records and application statuses;
editing a listing in one workspace does not alter another. Manual imports and
personal records never enter the shared feed cache. Provider API keys, server
settings, hardware, and upstream API quotas are shared by the installation.

This is application-level isolation in a homelab beta. The server operator controls
the database files and encryption key; this is not end-to-end encryption against
the host administrator. Keep the application on loopback behind the same protected
Cloudflare Tunnel. Local-token development mode is one workspace, not multiuser.

## Sign out, revoke access, and back up

Use **Sign out** in Radar for Cloudflare sessions. Use separate browser profiles
when testing two accounts. Clear any extension answer pack before switching users;
the Chrome extension has its own browser-session storage.

To revoke access, remove the friend's email from both the Cloudflare policy and
RADAR_ALLOWED_EMAILS, then recreate Radar. Their stored workspace remains for a
possible future re-invite; revocation is not deletion. Their background maintenance
is skipped when they are not allowed. Identity/email changes require a deliberate
migration; do not reassign the legacy owner variable.

After upgrading, back up every workspace with:

```bash
cd ~/jobradar
sudo bash deploy/backup.sh
```

Backup staging uses the persistent data volume instead of the container's small
/tmp filesystem so multiuser archives are not limited to its 64 MB tmpfs.
The tar.gz includes consistent SQLite snapshots of the legacy owner database,
encrypted workspace registry, and friend databases under hashed filenames. Keep
its matching .env/encryption key privately. Snapshots are consistent per database;
the backup is not a transaction spanning all users' databases. Do not run old 2.6
code against a multiuser installation; it does not enforce workspace isolation.
