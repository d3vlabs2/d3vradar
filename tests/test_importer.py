import json,socket
import pytest
from fastapi.testclient import TestClient
from radar import importer
from radar.app import app
from test_app import HEADERS

DESCRIPTION='<h2>Responsibilities</h2><p>Support Windows workstations, Microsoft 365 and Active Directory. Diagnose network issues and document resolutions for users.</p>'
def page(data):return '<html><head><title>Support role</title><script type="application/ld+json">'+json.dumps(data)+'</script></head><body>Navigation</body></html>'
def posting(**kw):return {'@type':'JobPosting','title':'IT Support','hiringOrganization':{'name':'Example'},'description':DESCRIPTION,**kw}

def test_structured_description_and_fields():
 result=importer.extract_page(page({'@graph':[posting(jobLocationType='TELECOMMUTE',jobLocation={'address':{'addressLocality':'Albany','addressRegion':'NY'}},baseSalary={'currency':'USD','value':{'minValue':50000,'maxValue':70000,'unitText':'YEAR'}})]}),'https://example.com/job')
 assert result['title']=='IT Support' and result['company']=='Example'
 assert result['workplace']=='remote' and result['location']=='Albany, NY'
 assert '50000' in result['salary'] and '<h2>' not in result['description']
 assert 'Diagnose network issues' in result['description']
 assert result['reviewRequired'] is True

def test_fallback_skips_navigation_forms_scripts_and_footer():
 html='<html><head><title>Support role</title></head><body><nav><div>Not job text</div></nav><main><h1>IT Support</h1><h2>Responsibilities</h2><p>Support users with Windows, Microsoft 365 and network troubleshooting. Document tickets and resolve issues for business users.</p><form>SECRET FORM<script>bad</script></form></main><footer>Footer data</footer></body></html>'
 result=importer.extract_page(html,'https://example.com/job')
 for excluded in ['Not job text','SECRET FORM','Footer data','bad']:assert excluded not in result['description']
 assert result['title']=='IT Support' and result['workplace']=='unknown'

@pytest.mark.parametrize('html',[page([posting(),posting(title='Other')]),'<main>Please sign in</main>','<body>'+('Content '*100)+'</body>',page(posting(description='Short'))])
def test_refuses_ambiguous_or_unreadable_pages(html):
 with pytest.raises(ValueError):importer.extract_page(html,'https://example.com/job')

@pytest.mark.parametrize('url',['http://example.com/job','https://user:pass@example.com/job','https://localhost/job','https://router.lan/job','https://example.com:8443/job','https://example.com/\r\nX:header'])
def test_rejects_private_or_unsafe_url_shapes(url):
 with pytest.raises(ValueError):importer.public_target(url)

@pytest.mark.parametrize('ip',['127.0.0.1','10.0.0.1','192.168.1.1','100.64.0.1','169.254.169.254','::1','fc00::1','224.0.0.1'])
def test_rejects_private_dns_answers(monkeypatch,ip):
 monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443))])
 with pytest.raises(ValueError):importer.public_target('https://public-looking.example/job')

def test_resolved_ip_is_pinned_and_hostname_retained(monkeypatch):
 monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))])
 p,host,ip=importer.public_target('https://EXAMPLE.com/job')
 assert host=='example.com' and ip=='93.184.216.34'
 connection=importer.PinnedHTTPS(host,ip,8)
 assert connection.host=='example.com' and connection.pinned_ip=='93.184.216.34'

class Response:
 def __init__(self,status=200,headers=None,data=None):self.status=status;self.headers=headers or {'Content-Type':'text/html; charset=utf-8'};self.data=data if data is not None else page(posting()).encode()
 def getheader(self,key,default=None):return self.headers.get(key,default)
 def read(self,n):chunk=self.data[:n];self.data=self.data[n:];return chunk

def setup_network(monkeypatch,responses):
 calls=[]
 monkeypatch.setattr(importer,'public_target',lambda url:(importer.urlsplit(url),importer.urlsplit(url).hostname,'93.184.216.34'))
 class Connection:
  def __init__(self,*args,**kw):pass
  def request(self,method,target,headers):calls.append((method,target,headers))
  def getresponse(self):return responses.pop(0)
  def close(self):pass
 monkeypatch.setattr(importer,'PinnedHTTPS',Connection)
 return calls

def test_fetch_is_read_only_without_credentials(monkeypatch):
 calls=setup_network(monkeypatch,[Response()]);result=importer.fetch_details('https://example.com/job?id=1')
 assert result['title']=='IT Support'
 assert calls[0][0]=='GET' and calls[0][1]=='/job?id=1'
 assert 'Cookie' not in calls[0][2] and 'Authorization' not in calls[0][2]

@pytest.mark.parametrize('response',[Response(status=403),Response(headers={'Content-Type':'application/pdf'}),Response(data=b'x'*(importer.MAX_PAGE+1))])
def test_provider_errors_and_limits(monkeypatch,response):
 setup_network(monkeypatch,[response])
 with pytest.raises(ValueError):importer.fetch_page('https://example.com/job')

def test_redirect_destination_is_rechecked(monkeypatch):
 setup_network(monkeypatch,[Response(status=302,headers={'Location':'https://127.0.0.1/private'})])
 seen=[]
 def validate(url):
  seen.append(url)
  if '127.0.0.1' in url:raise ValueError('Private address')
  return importer.urlsplit(url),'example.com','93.184.216.34'
 monkeypatch.setattr(importer,'public_target',validate)
 with pytest.raises(ValueError):importer.fetch_page('https://example.com/job')
 assert seen==['https://example.com/job','https://127.0.0.1/private']

def test_endpoint_auth_origin_and_no_persistence(monkeypatch):
 monkeypatch.setattr('radar.app.fetch_details',lambda url:importer.extract_page(page(posting()),url))
 with TestClient(app,headers=HEADERS) as c:
  before=c.get('/api/workspace').json();url='https://example.com/job'
  assert c.post('/api/import/fetch',headers={'Authorization':''},json={'url':url}).status_code==401
  assert c.post('/api/import/fetch',headers={'Origin':'https://evil.example'},json={'url':url}).status_code==403
  r=c.post('/api/import/fetch',json={'url':url});assert r.status_code==200 and r.json()['title']=='IT Support'
  after=c.get('/api/workspace').json()
  assert before['jobs']==after['jobs'] and before['applications']==after['applications']

def test_entity_encoded_description_is_readable():
 result=importer.extract_page(page(posting(description=DESCRIPTION.replace('<','&lt;').replace('>','&gt;'))),'https://example.com/job')
 assert '<p>' not in result['description'] and 'Support Windows' in result['description']

def test_mixed_public_private_dns_is_rejected(monkeypatch):
 monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,443)) for ip in ['93.184.216.34','127.0.0.1']])
 with pytest.raises(ValueError):importer.public_target('https://example.com/job')

def test_connection_uses_pinned_ip_and_hostname_for_tls(monkeypatch):
 connection=importer.PinnedHTTPS('example.com','93.184.216.34',8);seen={}
 raw=object();wrapped=object()
 def connect(address,timeout):seen['address']=address;return raw
 class Context:
  def wrap_socket(self,sock,server_hostname):seen['hostname']=server_hostname;assert sock is raw;return wrapped
 monkeypatch.setattr(socket,'create_connection',connect);connection._context=Context();connection.connect()
 assert seen=={'address':('93.184.216.34',443),'hostname':'example.com'}
 assert connection.sock is wrapped


def test_metadata_fills_missing_fields_and_hybrid():
 html='<meta name="company" content="Example IT"><meta name="job:location" content="Albany, NY"><meta name="salary" content="$60,000"><main><h1>Support Technician</h1><h2>Requirements</h2><p>This hybrid position supports Windows workstations, handles tickets and assists users with troubleshooting and network access.</p></main>'
 result=importer.extract_page(html,'https://example.com/job')
 assert result['company']=='Example IT'
 assert result['location']=='Albany, NY'
 assert result['salary']=='$60,000'
 assert result['workplace']=='hybrid'
