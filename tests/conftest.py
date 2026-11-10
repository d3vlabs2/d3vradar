import os,tempfile,base64
os.environ['RADAR_DATA']=tempfile.mkdtemp(prefix='radar-tests-')
os.environ['RADAR_ENCRYPTION_KEY']=base64.urlsafe_b64encode(b'test-key-for-radar-only-32-bytes!!'[:32]).decode()
os.environ['RADAR_AUTH_MODE']='local'
os.environ['RADAR_LOCAL_TOKEN']='test-token-for-fixtures-only-32-chars'
os.environ['RADAR_ORIGIN']='http://testserver'
os.environ['RADAR_SCHEDULER']='false'
