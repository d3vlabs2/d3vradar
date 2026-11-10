"""Photo source catalog, combined without duplicating existing source identifiers."""
import json
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).parent/'assets'

def expand_boards(existing):
    boards=[dict(b) for b in existing]
    known={b['id']:b for b in boards}
    reviews={r['id']:r for r in json.loads((ROOT/'source_review.json').read_text())} if (ROOT/'source_review.json').exists() else {}
    for line in (ROOT/'source_catalog.txt').read_text().splitlines():
        ident,name,url=line.split('|')
        if ident not in known:
            b={'id':ident,'name':name,'url':url,'mode':'indexed','domain':urlsplit(url).hostname.removeprefix('www.'),'about':'Search links and job import; automated indexed discovery requires your Brave Search API key. Employer application route varies by listing.'}
            known[ident]=b;boards.append(b)
        b=known[ident];r=reviews.get(ident,{})
        b['kind']='Company careers' if int(next(i for i,l in enumerate((ROOT/'source_catalog.txt').read_text().splitlines()) if l.startswith(ident+'|')))>=50 else 'Job board / marketplace'
        if ident in ('ycombinator','aws','dropbox') and r.get('url'):
            b['url']=r['url'];b['domain']=urlsplit(r['url']).hostname.removeprefix('www.')
        if ident=='otta' and r.get('status')==200:
            b['domain']='welcometothejungle.com';b['domains']=['welcometothejungle.com'];b['about']='Otta now redirects to Welcome to the Jungle. Original source identity is retained; discovery targets its current domain.'
        if ident in ('invision','hired'):
            b['mode']='manual';b['about']='Original source redirects to a different product/corporate page; no current job feed verified. Retained as a historical source with manual import.'
        b['photoNumber']=next(i+1 for i,l in enumerate((ROOT/'source_catalog.txt').read_text().splitlines()) if l.startswith(ident+'|'))
        b['review']={k:r[k] for k in ('checked','status','finalUrl','title','error') if k in r}
        if r.get('status') in (404,410) and b['mode']=='indexed':
            b['mode']='manual';b['about']='Source URL was unavailable during review. Original link and manual job import retained; automatic discovery is paused.'
    for b in boards:
        if b['id']=='weworkremotely':b.update(mode='wwr',about='Official public RSS feed. Original listing links and source credit are preserved.')
        if b['id']=='remoteok':b.update(mode='remoteok',about='Public JSON API. Remote OK links and source credit are preserved.')
        if b['id']=='lever':b.update(domain='jobs.lever.co',domains=['jobs.lever.co','jobs.eu.lever.co'],about='Discover public employer Lever boards using indexed search; Lever itself is an ATS, not a single cross-company public feed.')
        if b['id']=='workable':b.update(domain='apply.workable.com',about='Discover public employer Workable boards using indexed search; Workable itself is an ATS.')
    # Only provider/board mappings verified against a public feed are included.
    config=ROOT/'verified_boards.json'
    for ident,settings in (json.loads(config.read_text()).items() if config.exists() else []):
        if ident in known:known[ident].update(settings)
    return boards
