"""Require successful push CI for this exact public main-branch commit."""
import json
import re
import sys
import urllib.request


def passed(runs, sha):
    matching = [r for r in runs if r.get('head_sha') == sha and r.get('head_branch') == 'main' and r.get('event') == 'push']
    latest = max(matching, key=lambda r: r['id'], default=None)
    return bool(latest and latest.get('status') == 'completed' and latest.get('conclusion') == 'success')


if __name__ == '__main__':
    sha = sys.argv[1]
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise SystemExit('Invalid commit SHA')
    url = 'https://api.github.com/repos/d3vlabs2/d3vradar/actions/workflows/ci.yml/runs?event=push&head_sha=' + sha
    try:
        request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'D3V-Radar-Updater'})
        with urllib.request.urlopen(request, timeout=30) as response:
            runs = json.load(response)['workflow_runs']
    except Exception as error:
        raise SystemExit('Cannot verify GitHub CI; installation unchanged. Retry later. ' + str(error))
    if not passed(runs, sha):
        raise SystemExit('This commit has not passed Radar CI yet. Installation unchanged. Check GitHub Actions and retry.')
    print('Radar CI passed for ' + sha[:12])
