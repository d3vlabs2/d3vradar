# Contributing

Create a feature branch, make focused changes, and open a pull request to main.
Run `pip install -r requirements-dev.txt`, `python -m pytest -q`, and `npm test`.
Radar CI runs tests and builds Docker for pushes to main and pull requests.
Use fictional profiles and mocked source responses in tests. Do not upload resumes,
application records, .env files, encryption keys, or databases to issues or commits.
After merging and successful CI, update the homelab using deploy/update-homelab.sh.
