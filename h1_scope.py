"""Export HackerOne program policy and complete structured scope for Strix."""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

BASE = 'https://api.hackerone.com/v1/hackers/programs/'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, username, token):
        self.auth = 'Basic ' + base64.b64encode(f'{username}:{token}'.encode()).decode()
        self.opener = build_opener(NoRedirect())
        self.last = 0

    def get(self, url):
        parsed = urlparse(url)
        if (parsed.scheme != 'https' or parsed.netloc != 'api.hackerone.com'
                or not parsed.path.startswith('/v1/hackers/programs/')):
            raise RuntimeError('Refused pagination URL outside the HackerOne program API.')
        for attempt in range(4):
            time.sleep(max(0, 1.3 - (time.monotonic() - self.last)))
            self.last = time.monotonic()
            req = Request(url, headers={'Authorization': self.auth, 'Accept': 'application/json',
                                        'User-Agent': 'H1ScopeExporter/1.0'})
            try:
                with self.opener.open(req, timeout=40) as response:
                    result = json.load(response)
                    # Some program responses return the resource without a data envelope.
                    if isinstance(result, dict) and 'data' not in result and 'attributes' in result:
                        result = {'data': result}
                    return result
            except HTTPError as exc:
                if exc.code in (429, 502, 503) and attempt < 3:
                    delay = exc.headers.get('Retry-After', '')
                    time.sleep(min(60, int(delay)) if delay.isdigit() else 2 ** (attempt + 1))
                    continue
                messages = {401: 'Invalid API username/token.', 403: 'Program access denied.',
                            404: 'Program or endpoint not found.'}
                raise RuntimeError(f'HackerOne HTTP {exc.code}: ' + messages.get(exc.code, 'Request failed.')) from None
        raise RuntimeError('API retries exhausted.')

    def listing(self, url):
        items, seen = [], set()
        while url:
            if url in seen:
                raise RuntimeError('Pagination loop detected; no partial export written.')
            seen.add(url)
            result = self.get(url)
            if not isinstance(result.get('data'), list):
                raise RuntimeError('Unexpected API list response.')
            items.extend(result['data'])
            following = result.get('links', {}).get('next')
            if isinstance(following, dict):
                following = following.get('href')
            url = urljoin(url, following) if following else None
        return items


def render(snapshot):
    attrs = snapshot['program']['data']['attributes']
    handle = snapshot['handle']
    lines = [f'# {attrs.get("name", handle)} — Strix scope instructions', '',
             f'- Source: https://hackerone.com/{handle}',
             f'- Retrieved (UTC): {snapshot["retrieved_at"]}',
             f'- Submission state: {attrs.get("submission_state", "not provided")}',
             f'- Open scope flag: {attrs.get("open_scope", "not provided")}', '',
             '## Operating instructions', '',
             'Read the complete original policy below before testing. Asset eligibility is not blanket permission for every testing method.',
             'Apply explicit exclusions and asset instructions. Do not expand wildcards, paths, or third-party ownership beyond the policy.',
             'If the policy, asset list, or referenced documents conflict or are incomplete, pause the affected testing and request clarification.',
             'This is a dated snapshot. Re-export before a new engagement. Do not treat missing rules as unrestricted permission.', '',
             '## In-Scope — assets eligible for submission', '']
    groups = [('in', '## Out-of-Scope — assets not eligible for submission'),
              ('out', '## Assets with unspecified eligibility')]
    def asset(a):
        return [f'### {a.get("asset_identifier", "unspecified asset")}', '',
                f'- Asset type: {a.get("asset_type", "not provided")}',
                f'- Eligible for submission: {a.get("eligible_for_submission", "not provided")}',
                f'- Eligible for bounty: {a.get("eligible_for_bounty", "not provided")}',
                f'- Maximum severity: {a.get("max_severity", "not provided")}', '',
                '**Original asset instructions:**', '', a.get('instruction') or '(No asset-specific instructions returned.)', '']
    buckets = {'in': [], 'out': [], 'unknown': []}
    for item in snapshot['structured_scopes']:
        a = item['attributes']
        eligible = a.get('eligible_for_submission')
        buckets['in' if eligible is True else 'out' if eligible is False else 'unknown'].append(a)
    for category, title in [('in', None), ('out', groups[0][1]), ('unknown', groups[1][1])]:
        if title:
            lines.extend([title, ''])
        if not buckets[category]:
            lines.extend(['No assets in this category were returned by the API. This does not override policy exclusions.', ''])
        for a in buckets[category]:
            lines.extend(asset(a))
    lines.extend(['## Exclusions and out-of-scope vulnerabilities', '',
                  'These API exclusions concern reward eligibility; distinguish them from prohibited testing in the original policy.', ''])
    for item in snapshot['scope_exclusions']:
        a = item['attributes']
        lines.extend([f'### {a.get("category", "Exclusion")}', '', a.get('details') or '(No details returned.)', ''])
    if not snapshot['scope_exclusions']:
        lines.extend(['No structured exclusions returned. Read the policy and linked core-ineligible-finding rules.', ''])
    lines.extend(['## Rate limits and testing windows', '',
                  'The exporter does not infer these rules from asset eligibility. Follow the exact requirements in the original policy and asset instructions below/above. If absent or ambiguous, obtain clarification before automated testing.', '',
                  '## Special engagement rules — headers and test accounts', '',
                  'Use only the headers, account procedures, and engagement conditions stated in the original policy and asset instructions. The exporter does not invent requirements. Review referenced documents before starting.', '',
                  '## Original program policy — complete text', '', attrs['policy'], ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('program', help='Program handle or https://hackerone.com/<handle>')
    parser.add_argument('--username', default=os.getenv('H1_API_USERNAME'))
    parser.add_argument('--output-dir', type=Path, default=Path('.'))
    args = parser.parse_args()
    handle = args.program.strip().rstrip('/').split('/')[-1]
    if not re.fullmatch(r'[A-Za-z0-9_-]+', handle):
        parser.error('Invalid program handle.')
    username = args.username or input('HackerOne API username: ').strip()
    token = os.getenv('H1_API_TOKEN') or getpass.getpass('HackerOne API token: ')
    if not username or not token:
        parser.error('Both API username and API token are required.')
    client = Client(username, token)
    base = BASE + handle
    try:
        program = client.get(base)
        if not program.get('data', {}).get('attributes', {}).get('policy', '').strip():
            raise RuntimeError('Program policy missing. No instruction file generated.')
        scopes = client.listing(base + '/structured_scopes?page[size]=100')
        exclusions = client.listing(base + '/scope_exclusions')
        snapshot = {'handle': handle, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                    'program': program, 'structured_scopes': scopes, 'scope_exclusions': exclusions}
        markdown = render(snapshot)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for suffix, content in [('scope.json', json.dumps(snapshot, ensure_ascii=False, indent=2)),
                                ('scope.md', markdown)]:
            path = args.output_dir / f'{handle}-{suffix}'
            temp = path.with_suffix(path.suffix + '.tmp')
            temp.write_text(content, encoding='utf-8')
            temp.replace(path)
        print(f'Exported {len(scopes)} assets and {len(exclusions)} exclusions.')
        print(args.output_dir / f'{handle}-scope.md')
    except (RuntimeError, URLError, ValueError, KeyError, OSError) as exc:
        parser.exit(1, f'Export failed: {exc}\n')


if __name__ == '__main__':
    main()

