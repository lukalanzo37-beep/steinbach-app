from __future__ import annotations
import http.cookiejar, json, os, urllib.request, urllib.error

BASE=os.getenv('STEINBACH_TEST_BASE','http://127.0.0.1:8000').rstrip('/')

class Client:
    def __init__(self):
        self.jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf=None
    def call(self,path,method='GET',payload=None,expected=200):
        data=json.dumps(payload).encode() if payload is not None else None
        headers={}
        if payload is not None: headers['Content-Type']='application/json'
        if self.csrf and method not in ('GET','HEAD'): headers['X-CSRF-Token']=self.csrf
        req=urllib.request.Request(BASE+path,data=data,method=method,headers=headers)
        try:
            with self.opener.open(req,timeout=10) as r:
                status=r.status; raw=r.read().decode(); out=json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            status=e.code; raw=e.read().decode();
            try: out=json.loads(raw)
            except: out=raw
        assert status==expected, (path,status,expected,out)
        return out
    def login(self,email,pw,expected=200):
        out=self.call('/api/auth/login','POST',{'email':email,'password':pw},expected)
        if expected==200: self.csrf=out['csrf']
        return out

admin=Client(); emp1=Client(); cust1=Client()
health=admin.call('/api/health'); assert health['ok'] and health['version']=='16.0-prelaunch'
admin.login('admin@steinbach.local','Admin!2026Demo')
emp1.login('mitarbeiter@steinbach.local','Mitarbeiter!2026Demo')
cust1.login('kunde@steinbach.local','Kunde!2026Demo')

# Create second customer through the real invitation flow.
inv=admin.call('/api/admin/invitations','POST',{'email':'kunde2@steinbach.local','role':'customer','name':'Kunde Zwei','phone':''})
assert inv.get('dev_invite_token'), inv
cust2=Client(); cust2.call('/api/auth/accept-invite','POST',{'token':inv['dev_invite_token'],'new_password':'Kunde2!2026Demo'})
cust2.login('kunde2@steinbach.local','Kunde2!2026Demo')
obj2=cust2.call('/api/objects','POST',{'name':'Objekt Zwei','type':'Wohnhaus','address':'Test 2','city':'Baden-Baden','postal_code':'76530'})['id']
t2=cust2.call('/api/tickets','POST',{'object_id':obj2,'category':'Technik','urgency':'Dringend','location':'Keller','description':'Testmeldung zweiter Kunde','preferred_contact':'Portal','phone':''})

# Customer isolation: customer 1 must not attach messages/services to customer 2 data.
cust1.call('/api/messages','POST',{'ticket_id':t2['id'],'body':'Fremder Ticketversuch'},403)
cust1.call('/api/service-requests','POST',{'object_id':obj2,'service_code':'gartenpflege','action':'add','note':'fremdes Objekt'},400)
cust1.call(f"/api/tickets/{t2['id']}",expected=403)

# Create a second employee and assign customer-2 ticket to employee 2.
inv2=admin.call('/api/admin/invitations','POST',{'email':'mitarbeiter2@steinbach.local','role':'employee','name':'Mitarbeiter Zwei','phone':''})
emp2=Client(); emp2.call('/api/auth/accept-invite','POST',{'token':inv2['dev_invite_token'],'new_password':'Mitarbeiter2!2026Demo'}); emp2.login('mitarbeiter2@steinbach.local','Mitarbeiter2!2026Demo')
users=admin.call('/api/team/users'); emp2_id=next(u['id'] for u in users if u['email']=='mitarbeiter2@steinbach.local')
admin.call(f"/api/tickets/{t2['id']}",'PATCH',{'assignee_user_id':emp2_id,'status':'Übernommen'})

# Employee 1 cannot view or edit employee 2's assigned ticket.
emp1.call(f"/api/tickets/{t2['id']}",expected=403)
emp1.call(f"/api/tickets/{t2['id']}",'PATCH',{'status':'In Arbeit'},403)
ids=[x['id'] for x in emp1.call('/api/tickets')]
assert t2['id'] not in ids, ids
# Employee 2 can access it.
assert emp2.call(f"/api/tickets/{t2['id']}")['id']==t2['id']
emp2.call(f"/api/tickets/{t2['id']}",'PATCH',{'status':'In Arbeit'})

# CSRF enforcement.
csrf_saved=cust1.csrf; cust1.csrf=None
cust1.call('/api/objects','POST',{'name':'Soll scheitern','type':'','address':'','city':'','postal_code':''},403)
cust1.csrf=csrf_saved

# Bad priorities and invalid dates rejected.
objs=cust1.call('/api/objects'); oid=objs[0]['id']
cust1.call('/api/tickets','POST',{'object_id':oid,'category':'Test','urgency':'SOFORT','location':'','description':'Ungültige Priorität','preferred_contact':'Portal','phone':''},400)
cust1.call('/api/appointments','POST',{'object_id':oid,'title':'Termin','appointment_date':'2026-99-99','time_start':'10:00','time_end':'11:00','note':''},400)


# Positive customer workflow: own ticket, appointment, service request and referral.
own=cust1.call('/api/tickets','POST',{'object_id':oid,'category':'Hausmeisterservice','urgency':'Normal','location':'Eingang','description':'Türgriff bitte prüfen','preferred_contact':'Portal','phone':''})
assert own['ticket_no'].startswith('ST-')
appt=cust1.call('/api/appointments','POST',{'object_id':oid,'ticket_id':own['id'],'title':'Besichtigung Türgriff','appointment_date':'2026-10-01','time_start':'09:00','time_end':'10:00','note':'Bitte klingeln'})
assert appt['status']=='Angefragt'
sr=cust1.call('/api/service-requests','POST',{'object_id':oid,'service_code':'gartenpflege','action':'add','note':'Bitte Angebot'})
refs=cust1.call('/api/referrals','POST',{'referred_name':'Empfehlung Test','referred_contact':'test@example.invalid','reward_type':'discount','note':''})
admin.call(f"/api/service-requests/{sr['id']}",'PATCH',{'status':'approved'})
admin.call(f"/api/referrals/{refs['id']}",'PATCH',{'status':'approved','reward_value_cents':2500})
notes=cust1.call('/api/notifications'); assert any(n['kind']=='service' for n in notes)
# Admin-only endpoint isolation.
cust1.call('/api/admin/audit',expected=403)
assert isinstance(admin.call('/api/admin/audit'),list)

# Password reset does not disclose unknown accounts.
unknown=Client().call('/api/auth/request-password-reset','POST',{'email':'unknown@example.invalid'})
assert unknown['ok'] and 'dev_reset_token' not in unknown

# Logout invalidates session.
cust2.call('/api/auth/logout','POST',{})
cust2.call('/api/auth/me',expected=401)

print('PRELAUNCH TEST OK')
