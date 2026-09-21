"""Small post-start smoke test. Run while the app is running locally."""
from __future__ import annotations
import http.cookiejar, json, os, urllib.request, urllib.error
BASE=os.getenv('STEINBACH_TEST_BASE','http://127.0.0.1:8000').rstrip('/')
jar=http.cookiejar.CookieJar(); opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def call(path, method='GET', payload=None, csrf=None):
    data=json.dumps(payload).encode() if payload is not None else None
    headers={'Content-Type':'application/json'} if payload is not None else {}
    if csrf: headers['X-CSRF-Token']=csrf
    req=urllib.request.Request(BASE+'/api'+path,data=data,method=method,headers=headers)
    with opener.open(req,timeout=10) as r:
        return json.loads(r.read().decode())

h=call('/health'); assert h['ok']; print('health:',h['version'])
login=call('/auth/login','POST',{'email':'kunde@steinbach.local','password':'Kunde!2026Demo'})
csrf=login['csrf']; print('login:',login['user']['role'])
objs=call('/objects'); assert objs; print('objects:',len(objs))
tickets=call('/tickets'); print('tickets:',len(tickets))
appts=call('/appointments'); print('appointments:',len(appts))
call('/auth/logout','POST',{},csrf=csrf); print('logout: ok')
print('SMOKE TEST OK')
