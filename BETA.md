# Private beta workspaces (Radar 2.8)

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
updating. Health should show 2.8.0.

The first upgrade can infer the owner if exactly one email is allowed. If more than
one is allowed and no owner was configured or persisted, startup fails closed.
The owner binding is persisted encrypted. Changing allowlist order or signing in
first cannot take ownership. Changing RADAR_OWNER_EMAIL to somebody else fails;
this is not an account transfer tool.

## Invite a friend

For Radar 2.8, use the Users screen described below. The environment-variable
steps here remain available for initial/server configuration.

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

## Manage users in Radar (2.8+)

After upgrading, the signed-in owner sees **Users** in the sidebar. Enter a friend's
sign-in email and click **Add user**. This saves encrypted membership immediately;
no .env edits or application restart are needed. The new workspace is created on
their first successful login. No invitation email is sent.

Cloudflare remains a separate gate. Add that same email to the existing Access
Allow policy. **Copy approved emails for Cloudflare** copies the enabled list so you
can paste it there. Radar does not change the Cloudflare policy or verify its state.
Keep the current email policy; do not replace it with Everyone.

Use **Disable** to deny the user's subsequent Radar API requests immediately while
retaining their workspace, including when their email is still in the old .env
allowlist. Also remove them from Cloudflare. **Enable** restores access to the same
workspace. These changes survive restarts and are included in the encrypted registry
backup. The owner cannot be disabled, reassigned, or created through this screen.
Only the owner can view this email list or change access; other users cannot see it.

For UI-managed users, use **Disable** to revoke app access; removing an email from
RADAR_ALLOWED_EMAILS alone does not remove an explicit active UI membership. Keep
the existing owner in RADAR_ALLOWED_EMAILS and preserve RADAR_OWNER_EMAIL and the
encryption key. Local-token development mode does not offer multiuser management.

## Default home address

In **Profile → Home address for directions**, save your street address, city, state,
and ZIP (or a less precise ZIP/city). Every **Map & commute → Directions from home**
dialog prefills this saved address in **Starting address**. If it is empty, Radar
uses your profile's general home location. You can edit the starting address for
one trip without changing the saved profile, or use **Edit saved home address in
Profile** to update the default. Address-only input is never inserted into generated
resumes or letters. It stays encrypted in your own workspace and is shared with
Google only when you choose to open/load a route.

## One-dialog imports

Click **Import job**, paste the URL, fetch/review the fields in that dialog, and
optionally add notes. **Save to Saved jobs** commits the job and its bookmark
together and returns to Saved jobs without opening another dialog. Saving is not
applying. Open the saved role later to prepare documents or mark it applied. If
the same job already has an application, importing it again preserves its status,
applied/follow-up dates, and notes and returns to Applications instead.

### Applied date default (2.8.1)

Opening a role fills Applied date with today's local calendar date when no applied
date has been recorded. Existing dates and your edits are preserved. The helper
text says “Change this date if you applied on a different day.” Saving a role with
New, Saved, or Hidden status does not record that suggested date as an application.
