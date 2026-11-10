# Working on Radar

Use feature branches and reviewable pull requests for changes after initial setup.
Never commit .env, encryption keys, access tokens, profiles, resumes, documents,
databases, backups, or migration.json. Use fictional fixtures in tests.
Keep the application loopback-bound and preserve existing Docker volume names,
.env settings, and encrypted user data during upgrades.
Keep source attribution and application review intact. Never invent job details,
resume qualifications, applicant counts, or claim an application succeeded without confirmation.
Use authorized public source interfaces; do not bypass login, CAPTCHA, or site restrictions.
Run `python -m pytest -q`, `npm test`, and `python deploy/check_public_tree.py`.
CI builds the Docker image on GitHub-hosted runners. Do not add homelab credentials
or a public pull-request self-hosted deployment runner.
