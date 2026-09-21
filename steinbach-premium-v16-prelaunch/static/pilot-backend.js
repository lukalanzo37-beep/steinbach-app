(() => {
  'use strict';
  const state = { csrf: null, user: null, teamUsers: [], objects: [], appointments: [], timer: null };
  const $ = (id) => document.getElementById(id);
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));

  const api = async (path, options = {}) => {
    const headers = new Headers(options.headers || {});
    if (state.csrf && !['GET','HEAD','OPTIONS'].includes((options.method || 'GET').toUpperCase())) headers.set('X-CSRF-Token', state.csrf);
    if (options.json !== undefined) {
      headers.set('Content-Type','application/json');
      options.body = JSON.stringify(options.json);
      delete options.json;
    }
    const res = await fetch('/api' + path, { credentials:'same-origin', ...options, headers });
    let data = null;
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) data = await res.json();
    else data = await res.text();
    if (!res.ok) { const err=new Error((data && data.detail) || data || `HTTP ${res.status}`); err.status=res.status; err.data=data; throw err; }
    return data;
  };

  const mapStatus = s => s === 'approved' ? 'Vorteil freigegeben' : s === 'rejected' ? 'Abgelehnt' : 'Vorgemerkt';
  const mapReward = s => s === 'discount' ? 'Rabatt' : 'Guthaben / Provision';

  async function syncObjects() {
    const list = await api('/objects');
    state.objects = list;
    if (state.user?.role === 'customer') {
      const mapped = list.map((o,i)=>({id:`OBJ-${o.id}`, _api_id:o.id, name:o.name, type:o.type || '', city:o.city || '', active:i===0}));
      localStorage.setItem('steinbach_demo_objects_v13', JSON.stringify(mapped));
      try { renderObjects(); } catch {}
    }
  }

  async function syncTickets() {
    const list = await api('/tickets');
    const mapped = list.map(t => ({
      id:t.ticket_no, _api_id:t.id, category:t.category, urgency:t.urgency, object:t.object_name || '', location:t.location || '', text:t.description,
      contact:t.preferred_contact || 'Portal', phone:t.phone || '', status:t.status, assignee:t.assignee_name || 'Nicht zugewiesen',
      assignee_user_id:t.assignee_user_id || null, date:t.appointment_date || '', time:t.appointment_time || '', internalNote:t.internal_note || '',
      created:t.created_at, history:(t.history || []).map(h=>({text:h.event, at:h.created_at})), files:t.files || []
    }));
    localStorage.setItem('steinbach_demo_tickets_v9', JSON.stringify(mapped));
    try { renderTickets(); renderTeamInbox(); renderTeamAll(); } catch {}
    return mapped;
  }

  async function syncMessages() {
    const list = await api('/messages');
    const mapped = list.map(m=>({from:m.sender_role === 'customer' ? 'customer':'team', text:m.body, created:m.created_at, _api_id:m.id, _ticket_api_id:m.ticket_id || null}));
    localStorage.setItem('steinbach_demo_messages_v9', JSON.stringify(mapped));
    try { renderMessages(); renderTeamMessages(); } catch {}
  }

  async function syncNotifications() {
    if (!state.user) return;
    const list = await api('/notifications');
    if (state.user.role === 'customer') {
      const mapped = list.map(n=>({id:`n${n.id}`, icon:n.kind === 'urgent'?'!':n.kind==='message'?'✉':'•', title:n.title, text:n.body, created:n.created_at, read:!!n.read_at}));
      localStorage.setItem('steinbach_demo_notifications_v11', JSON.stringify(mapped));
      try { renderNotifications(); } catch {}
    }
  }

  async function syncServices() {
    if (state.user?.role !== 'customer' && state.user?.role !== 'admin') return;
    const list = await api('/service-requests');
    const byCode = {};
    [...list].reverse().forEach(r => { byCode[r.service_code] = r; });
    const base = (()=>{try{return JSON.parse(localStorage.getItem('steinbach_demo_services_v9')||'{}')}catch{return {}}})();
    Object.entries(byCode).forEach(([code,r])=>{
      if (r.status === 'pending') base[code] = {status:r.action==='remove'?'pendingRemove':'pendingAdd', _api_id:r.id};
      else if (r.status === 'approved') base[code] = {status:r.action==='remove'?'inactive':'active', _api_id:r.id};
      else if (r.status === 'rejected') base[code] = {status:base[code]?.status === 'active' ? 'active':'inactive', _api_id:r.id};
    });
    localStorage.setItem('steinbach_demo_services_v9',JSON.stringify(base));
    try { renderServices(); renderServiceQueue(); renderAdminQueuesMini(); } catch {}
  }

  async function syncReferrals() {
    if (state.user?.role !== 'customer' && state.user?.role !== 'admin') return;
    const list = await api('/referrals');
    const mapped = list.map(r=>({name:r.referred_name, contact:r.referred_contact || '', note:r.note || '', reward:mapReward(r.reward_type), created:r.created_at, status:mapStatus(r.status), _api_id:r.id, reward_value_cents:r.reward_value_cents}));
    localStorage.setItem('steinbach_demo_referrals_v11', JSON.stringify(mapped));
    try { renderReferralHistory(); renderReferralQueue(); renderAdminQueuesMini(); } catch {}
  }

  async function syncAppointments() {
    if (!state.user) return [];
    const list = await api('/appointments');
    state.appointments = list;
    if (state.user.role === 'customer') {
      const mapped = list.map(a=>({id:'api'+a.id,_api_id:a.id,date:a.appointment_date,time:[a.time_start,a.time_end].filter(Boolean).join('–')||'Zeit wird abgestimmt',reason:a.title,status:a.status,note:a.note||''}));
      localStorage.setItem('steinbach_demo_appointments_v11',JSON.stringify(mapped));
      try { renderAppointments(); } catch {}
    }
    try { renderTeamAppointments(); } catch {}
    return list;
  }

  async function syncAll() {
    await Promise.allSettled([syncObjects(),syncTickets(),syncMessages(),syncNotifications(),syncServices(),syncReferrals(),syncAppointments()]);
  }

  function startPolling() {
    clearInterval(state.timer);
    state.timer = setInterval(()=>{ if (state.user && document.visibilityState === 'visible') syncAll().catch(()=>{}); }, 15000);
  }

  async function loginHandler(e) {
    e.preventDefault(); e.stopImmediatePropagation();
    const form = e.currentTarget;
    const btn = form.querySelector('button[type="submit"]');
    const email = $('portalEmail')?.value.trim() || '';
    const password = $('portalPassword')?.value || '';
    const mfa_code = $('portalMfaCode')?.value.trim() || '';
    btn.disabled = true; btn.textContent = 'Anmelden …';
    try {
      const data = await api('/auth/login',{method:'POST',json:{email,password,mfa_code}});
      state.user=data.user; state.csrf=data.csrf;
      if (data.user.role !== 'customer') {
        try { state.teamUsers = await api('/team/users'); } catch { state.teamUsers=[]; }
      }
      await syncAll();
      portalLogin?.classList.add('hidden');
      if (data.user.role === 'customer') {
        portalApp?.classList.add('open'); teamApp?.classList.remove('open');
        try { renderTickets(); renderMessages(); renderServices(); renderAppointments(); renderNotifications(); loadPortalSettings(); renderReferralHistory(); renderObjects(); } catch {}
      } else {
        portalApp?.classList.remove('open');
        openTeamApp(data.user.role);
      }
      try { toast('Angemeldet', `${data.user.name} · ${data.user.role === 'customer'?'Kunde':data.user.role === 'admin'?'Admin':'Mitarbeiter'}`); } catch {}
      startPolling();
    } catch(err) {
      if (err.status===428) { const wrap=$('portalMfaWrap'); if(wrap)wrap.hidden=false; $('portalMfaCode')?.focus(); try{toast('Zusätzlicher Schutz','Bitte den 6-stelligen Authenticator-Code eingeben.')}catch{} }
      else { try { toast('Anmeldung fehlgeschlagen', err.message); } catch { alert(err.message); } }
    } finally { btn.disabled=false; btn.textContent='Portal öffnen'; }
  }

  async function logoutUI() {
    try { await api('/auth/logout',{method:'POST'}); } catch {}
    state.user=null; state.csrf=null; clearInterval(state.timer);
    portalApp?.classList.remove('open'); teamApp?.classList.remove('open'); portalLogin?.classList.remove('hidden');
    portalOverlay?.scrollTo({top:0,behavior:'instant'});
  }

  async function createTicketHandler(e) {
    e.preventDefault(); e.stopImmediatePropagation();
    const form=e.currentTarget; const btn=form.querySelector('button[type="submit"]'); btn.disabled=true;
    try {
      const objName=$('pdObject')?.value || '';
      const obj=state.objects.find(o=>o.name===objName) || state.objects[0];
      const urgency=$('pdUrgency').value === 'Notfall' ? 'Notfall' : $('pdUrgency').value;
      const result=await api('/tickets',{method:'POST',json:{
        object_id:obj?.id || null, category:$('pdCategory').value, urgency, location:$('pdLocation').value.trim(), description:$('pdText').value.trim(), preferred_contact:$('pdContact').value, phone:$('pdPhone').value.trim()
      }});
      const files=[...($('pdPhotos')?.files || [])].slice(0,6);
      for (const file of files) {
        const fd=new FormData(); fd.append('file',file);
        await api(`/tickets/${result.id}/files`,{method:'POST',body:fd});
      }
      await Promise.all([syncTickets(),syncNotifications()]);
      form.reset(); if ($('pdPreview')) $('pdPreview').innerHTML='';
      const s=$('portalTicketSuccess'); if(s){s.textContent=`Meldung ${result.ticket_no} wurde gespeichert und ist für Steinbach sichtbar.`; s.classList.add('show');}
      try { toast('Meldung gesendet', result.ticket_no); } catch {}
      await sleep(250); try { showPView('orders'); } catch {}
    } catch(err) { try{toast('Meldung nicht gesendet',err.message)}catch{alert(err.message)} }
    finally { btn.disabled=false; }
  }

  async function objectFormHandler(e){
    e.preventDefault();e.stopImmediatePropagation();
    try{
      await api('/objects',{method:'POST',json:{name:$('objectName').value.trim(),type:$('objectType').value,city:$('objectCity').value.trim(),address:'',postal_code:''}});
      e.currentTarget.reset(); await syncObjects(); try{toast('Objekt gespeichert','Das Objekt liegt jetzt in der Datenbank.')}catch{}
    }catch(err){try{toast('Objekt nicht gespeichert',err.message)}catch{alert(err.message)}}
  }

  async function customerMessageHandler(e){
    e.preventDefault();e.stopImmediatePropagation(); const input=$('portalMessageText'); const body=input.value.trim(); if(!body)return;
    try{await api('/messages',{method:'POST',json:{body}});input.value='';await Promise.all([syncMessages(),syncNotifications()]);try{toast('Nachricht gesendet','Steinbach sieht sie im internen Bereich.')}catch{}}
    catch(err){try{toast('Nachricht nicht gesendet',err.message)}catch{alert(err.message)}}
  }

  async function teamMessageHandler(e){
    e.preventDefault();e.stopImmediatePropagation(); const input=$('teamMessageText'); const body=input.value.trim(); if(!body)return;
    try{
      let customer=state.teamUsers.find(u=>u.role==='customer'); if(!customer){state.teamUsers=await api('/team/users');customer=state.teamUsers.find(u=>u.role==='customer');}
      if(!customer) throw new Error('Kein Kunde gefunden');
      await api('/messages',{method:'POST',json:{customer_id:customer.id,body}});input.value='';await syncMessages();try{toast('Nachricht gesendet','Die Antwort ist im Kundenportal gespeichert.')}catch{}
    }catch(err){try{toast('Nachricht nicht gesendet',err.message)}catch{alert(err.message)}}
  }

  async function referralHandler(e){
    e.preventDefault();e.stopImmediatePropagation(); const form=e.currentTarget;
    const reward=form.querySelector('input[name="rewardType"]:checked')?.value || 'Rabatt';
    try{
      await api('/referrals',{method:'POST',json:{referred_name:$('refName').value.trim(),referred_contact:$('refContact').value.trim(),note:$('refNote').value.trim(),reward_type:reward.toLowerCase().includes('rabatt')?'discount':'credit'}});
      form.reset(); await syncReferrals(); const s=$('referralSuccess'); if(s){s.textContent='Empfehlung wurde gespeichert. Vorteil und Höhe werden erst nach Prüfung verbindlich.';s.classList.add('show');} try{toast('Empfehlung gespeichert','Steinbach kann sie jetzt prüfen.')}catch{}
    }catch(err){try{toast('Empfehlung nicht gespeichert',err.message)}catch{alert(err.message)}}
  }

  async function serviceClickCapture(e){
    const btn=e.target.closest('[data-service-action]'); if(!btn || !state.user || state.user.role!=='customer') return;
    e.preventDefault(); e.stopImmediatePropagation();
    const code=btn.dataset.serviceAction;
    let local={};try{local=JSON.parse(localStorage.getItem('steinbach_demo_services_v9')||'{}')}catch{}
    const current=local[code] || {};
    try{
      if ((current.status==='pendingAdd'||current.status==='pendingRemove') && current._api_id){
        await api(`/service-requests/${current._api_id}`,{method:'DELETE'});
      } else {
        const action=current.status==='active'?'remove':'add';
        const obj=state.objects[0];
        await api('/service-requests',{method:'POST',json:{object_id:obj?.id||null,service_code:code,action,note:''}});
      }
      await Promise.all([syncServices(),syncNotifications()]); try{toast('Leistungsanfrage gespeichert','Die Änderung ist für Steinbach sichtbar.')}catch{}
    }catch(err){try{toast('Änderung nicht gespeichert',err.message)}catch{alert(err.message)}}
  }

  function findApiTicket(displayId){
    let arr=[];try{arr=JSON.parse(localStorage.getItem('steinbach_demo_tickets_v9')||'[]')}catch{}
    return arr.find(t=>t.id===displayId);
  }
  function assigneeIdByName(name){
    if(!name || name==='Nicht zugewiesen') return null;
    const u=state.teamUsers.find(x=>x.name===name); return u?.id || null;
  }

  async function saveTicketCapture(e, forceDone){
    if(!currentTicketId) return;
    e.preventDefault();e.stopImmediatePropagation();
    const local=findApiTicket(currentTicketId); if(!local?._api_id){try{toast('Nicht synchronisiert','Dieses Beispiel-Ticket liegt nicht in der Datenbank.')}catch{};return;}
    try{
      if(!state.teamUsers.length) state.teamUsers=await api('/team/users');
      await api(`/tickets/${local._api_id}`,{method:'PATCH',json:{
        status:forceDone?'Erledigt':$('tdStatus').value, assignee_user_id:assigneeIdByName($('tdAssignee').value), appointment_date:$('tdDate').value||null, appointment_time:$('tdTime').value||null, internal_note:$('tdInternal').value, customer_message:$('tdCustomerMsg').value.trim()||null
      }});
      await Promise.all([syncTickets(),syncMessages(),syncNotifications()]); try{closeTicketDetail();toast('Ticket aktualisiert',currentTicketId)}catch{}
    }catch(err){try{toast('Ticket nicht aktualisiert',err.message)}catch{alert(err.message)}}
  }

  async function newInternalTicketHandler(e){
    e.preventDefault();e.stopImmediatePropagation();
    try{
      if(!state.teamUsers.length) state.teamUsers=await api('/team/users');
      const customer=state.teamUsers.find(u=>u.role==='customer'); if(!customer) throw new Error('Kein Kunde vorhanden');
      const objs=await api('/objects'); const obj=objs.find(o=>o.customer_id===customer.id) || objs[0];
      const assignee=assigneeIdByName($('ntAssignee').value);
      await api('/admin/tickets-json',{method:'POST',json:{customer_id:customer.id,object_id:obj?.id||null,category:$('ntCategory').value,urgency:$('ntUrgency').value,location:$('ntLocation').value.trim(),description:$('ntText').value.trim(),preferred_contact:'Portal',phone:'',assignee_user_id:assignee}});
      e.currentTarget.reset(); await syncTickets(); try{toast('Auftrag angelegt','Der Vorgang wurde in der Datenbank gespeichert.');showTeamView('tickets')}catch{}
    }catch(err){try{toast('Auftrag nicht angelegt',err.message)}catch{alert(err.message)}}
  }

  async function adminQueueCapture(e){
    if(!state.user || state.user.role!=='admin') return;
    const sOk=e.target.closest('[data-service-approve]'), sNo=e.target.closest('[data-service-reject]'), rOk=e.target.closest('[data-ref-ok]'), rNo=e.target.closest('[data-ref-no]');
    if(!(sOk||sNo||rOk||rNo)) return;
    e.preventDefault();e.stopImmediatePropagation();
    try{
      if(sOk||sNo){
        const code=(sOk||sNo).dataset.serviceApprove || (sOk||sNo).dataset.serviceReject; let st={};try{st=JSON.parse(localStorage.getItem('steinbach_demo_services_v9')||'{}')}catch{}; const id=st[code]?._api_id;if(!id)throw new Error('Keine API-Anfrage zugeordnet');
        await api(`/service-requests/${id}`,{method:'PATCH',json:{status:sOk?'approved':'rejected'}});await syncServices();
      } else {
        const idx=Number((rOk||rNo).dataset.refOk ?? (rOk||rNo).dataset.refNo);let refs=[];try{refs=JSON.parse(localStorage.getItem('steinbach_demo_referrals_v11')||'[]')}catch{};const id=refs[idx]?._api_id;if(!id)throw new Error('Keine API-Empfehlung zugeordnet');
        await api(`/referrals/${id}`,{method:'PATCH',json:{status:rOk?'approved':'rejected'}});await syncReferrals();
      }
      await syncNotifications(); try{toast('Bearbeitet','Änderung wurde in der Datenbank gespeichert.')}catch{}
    }catch(err){try{toast('Nicht gespeichert',err.message)}catch{alert(err.message)}}
  }


  const slotTimes = label => ({'Vormittags':['09:00','12:00'],'Mittags':['12:00','14:00'],'Nachmittags':['14:00','17:00'],'Ganztägig flexibel':['09:00','17:00']}[label] || ['','']);

  async function appointmentFormHandler(e){
    e.preventDefault(); e.stopImmediatePropagation();
    const form=e.currentTarget; const btn=form.querySelector('button[type="submit"]'); if(btn)btn.disabled=true;
    try{
      const [start,end]=slotTimes($('apptTime').value); const obj=state.objects[0];
      await api('/appointments',{method:'POST',json:{object_id:obj?.id||null,title:$('apptReason').value,appointment_date:$('apptDate').value,time_start:start,time_end:end,note:$('apptNote').value.trim()}});
      form.reset(); await Promise.all([syncAppointments(),syncNotifications()]); try{toast('Terminanfrage gesendet','Steinbach sieht den Wunschtermin jetzt im internen Kalender.')}catch{}
    }catch(err){try{toast('Termin nicht gespeichert',err.message)}catch{alert(err.message)}} finally{if(btn)btn.disabled=false;}
  }

  function appointmentBadge(status){ return status==='Bestätigt'?'ok':status==='Erledigt'?'ok':status==='Angefragt'?'warn':status==='Abgesagt'?'urgent':'info'; }
  function fmtAppt(a){ return `${a.appointment_date}${a.time_start?' · '+a.time_start:''}${a.time_end?'–'+a.time_end:''}`; }
  function renderTeamAppointments(){
    if(!state.user || state.user.role==='customer') return;
    const list=$('teamAppointmentList'), mini=$('teamAppointmentMini'), stats=$('teamAppointmentStats');
    const arr=[...state.appointments].sort((a,b)=>(a.appointment_date+a.time_start).localeCompare(b.appointment_date+b.time_start));
    const today=new Date().toISOString().slice(0,10); const todayArr=arr.filter(a=>a.appointment_date===today && !['Abgesagt','Erledigt'].includes(a.status));
    if($('kpiToday')) $('kpiToday').textContent=String(todayArr.length); if($('teamApptCount')) $('teamApptCount').textContent=String(arr.filter(a=>a.status==='Angefragt').length);
    if(mini){ mini.innerHTML=''; const show=(todayArr.length?todayArr:arr.filter(a=>!['Abgesagt','Erledigt'].includes(a.status)).slice(0,3)); if(!show.length)mini.innerHTML='<p class="muted">Keine anstehenden Termine.</p>'; show.forEach(a=>{const r=document.createElement('div');r.className='portal-row';r.innerHTML='<div><b></b><small></small></div><span class="p-badge"></span>';r.querySelector('b').textContent=`${a.time_start||'–'} · ${a.title}`;r.querySelector('small').textContent=`${a.customer_name||''} · ${a.object_name||''} · ${a.appointment_date}`;const b=r.querySelector('.p-badge');b.textContent=a.status;b.classList.add(appointmentBadge(a.status));mini.appendChild(r)}); }
    if(list){ list.innerHTML=''; if(!arr.length)list.innerHTML='<p class="muted">Noch keine Termine.</p>'; arr.forEach(a=>{const row=document.createElement('div');row.className='queue-row';row.innerHTML=`<div><b></b><small></small><div class="ticket-meta"><span class="ticket-tag"></span><span class="ticket-tag"></span></div></div><div class="queue-actions"><button type="button" data-appt-confirm="${a.id}">Bestätigen</button><button type="button" data-appt-move="${a.id}">Verschieben</button><button type="button" class="approve" data-appt-done="${a.id}">Erledigt</button></div>`;row.querySelector('b').textContent=`${a.title} · ${a.customer_name||'Kunde'}`;row.querySelector('small').textContent=`${fmtAppt(a)} · ${a.object_name||''}`;const tags=row.querySelectorAll('.ticket-tag');tags[0].textContent=a.status;tags[1].textContent=a.employee_name||'Nicht zugewiesen';list.appendChild(row)}); }
    if(stats){const requested=arr.filter(a=>a.status==='Angefragt').length, confirmed=arr.filter(a=>a.status==='Bestätigt').length;stats.innerHTML=`<div class="portal-row"><div><b>Offene Anfragen</b><small>noch nicht bestätigt</small></div><span class="p-badge warn">${requested}</span></div><div class="portal-row"><div><b>Bestätigte Termine</b><small>serverseitig geplant</small></div><span class="p-badge ok">${confirmed}</span></div>`;}
  }
  window.steinbachRenderTeamAppointments=renderTeamAppointments;

  async function updateAppointment(id, mode){
    const a=state.appointments.find(x=>x.id===Number(id)); if(!a)return;
    let json={};
    if(mode==='confirm'){ let employee=a.employee_id; if(!employee){const me=state.user.role==='employee'?state.user:state.teamUsers.find(u=>u.role==='employee');employee=me?.id||null} json={status:'Bestätigt',employee_id:employee}; }
    if(mode==='done') json={status:'Erledigt'};
    if(mode==='move'){const date=prompt('Neues Datum (JJJJ-MM-TT):',a.appointment_date);if(!date)return;const time=prompt('Neue Startzeit (HH:MM):',a.time_start||'09:00');if(time===null)return;json={status:'Verschoben',appointment_date:date,time_start:time};}
    try{await api(`/appointments/${id}`,{method:'PATCH',json});await Promise.all([syncAppointments(),syncNotifications(),syncTickets()]);try{toast('Termin aktualisiert',`${a.title} · ${json.status||a.status}`)}catch{}}catch(err){try{toast('Termin nicht aktualisiert',err.message)}catch{alert(err.message)}}
  }

  async function renderSecurity(){
    if(!state.user || state.user.role!=='admin')return;
    try{
      const [mfa,health,push,ready]=await Promise.all([api('/auth/mfa/status'),api('/health'),api('/push/status'),api('/readiness')]);
      const box=$('mfaStatusBox'); if(box)box.innerHTML=`<div class="portal-row"><div><b>MFA</b><small>Authenticator-Schutz für dieses Admin-Konto</small></div><span class="p-badge ${mfa.enabled?'ok':'warn'}">${mfa.enabled?'Aktiv':'Nicht aktiv'}</span></div>`;
      const delivery=$('adminDeliveryStatus'); if(delivery)delivery.innerHTML=`<div class="portal-row"><div><b>Web-Push</b><small>${health.push_configured?'VAPID konfiguriert':'VAPID-Schlüssel fehlen'}</small></div><span class="p-badge ${health.push_configured?'ok':'warn'}">${health.push_configured?'Bereit':'Setup nötig'}</span></div><div class="portal-row"><div><b>Dieses Gerät</b><small>${push.subscribed?'Push-Abo vorhanden':'Noch nicht abonniert'}</small></div><span class="p-badge ${push.subscribed?'ok':'warn'}">${push.subscribed?'Aktiv':'Offen'}</span></div><div class="portal-row"><div><b>E-Mail</b><small>${health.smtp_configured?'SMTP konfiguriert':'E-Mails landen nur in der lokalen Outbox'}</small></div><span class="p-badge ${health.smtp_configured?'ok':'warn'}">${health.smtp_configured?'Bereit':'Pilot'}</span></div><div class="portal-row"><div><b>Launch-Readiness</b><small>${ready.ready?'Pflichtchecks bestanden':'Produktionschecks noch nicht vollständig'}</small></div><span class="p-badge ${ready.ready?'ok':'warn'}">${ready.ready?'Bereit':'Offen'}</span></div>`;
    }catch(err){try{toast('Sicherheitsstatus',err.message)}catch{}}
  }
  window.steinbachRenderSecurity=renderSecurity;

  async function inviteUserHandler(e){
    e.preventDefault();e.stopImmediatePropagation();
    try{const out=await api('/admin/invitations',{method:'POST',json:{name:$('inviteName').value.trim(),email:$('inviteEmail').value.trim(),role:$('inviteRole').value,phone:$('invitePhone').value.trim()}});const box=$('inviteResult');if(box){box.classList.add('show');box.textContent=out.dev_invite_link?`Einladung erstellt. Pilot-Link: ${out.dev_invite_link}`:'Einladung wurde per E-Mail vorbereitet.';}e.currentTarget.reset();try{toast('Einladung erstellt','Der Zugang kann jetzt vom neuen Nutzer aktiviert werden.')}catch{}}catch(err){try{toast('Einladung fehlgeschlagen',err.message)}catch{alert(err.message)}}
  }

  async function mfaSetup(){
    try{const setup=await api('/auth/mfa/setup',{method:'POST'});const box=$('mfaSetupResult');if(box){box.classList.add('show');box.innerHTML='';const b=document.createElement('div');b.innerHTML='<b>Authenticator-Schlüssel</b><br><code style="word-break:break-all"></code><br><small>In Microsoft Authenticator, Google Authenticator oder 1Password als TOTP hinzufügen.</small>';b.querySelector('code').textContent=setup.secret;box.appendChild(b);}const code=prompt('Jetzt den 6-stelligen Code aus der Authenticator-App eingeben:');if(!code)return;await api('/auth/mfa/confirm',{method:'POST',json:{code}});await renderSecurity();try{toast('MFA aktiviert','Admin-Anmeldungen benötigen ab jetzt zusätzlich den Authenticator-Code.')}catch{}}catch(err){try{toast('MFA nicht aktiviert',err.message)}catch{alert(err.message)}}
  }
  async function mfaDisable(){const code=prompt('Zur Deaktivierung den aktuellen 6-stelligen Authenticator-Code eingeben:');if(code===null)return;try{await api('/auth/mfa',{method:'DELETE',json:{code}});await renderSecurity();try{toast('MFA deaktiviert','Der zusätzliche Faktor wurde entfernt.')}catch{}}catch(err){try{toast('MFA nicht deaktiviert',err.message)}catch{alert(err.message)}}}

  const b64ToUint8Array=base64String=>{const padding='='.repeat((4-base64String.length%4)%4);const base64=(base64String+padding).replace(/-/g,'+').replace(/_/g,'/');const rawData=atob(base64);return Uint8Array.from([...rawData].map(ch=>ch.charCodeAt(0)))};
  async function subscribePush(){
    if(!state.user){try{toast('Bitte anmelden','Push wird an ein konkretes Portal-Konto gebunden.')}catch{};return}
    if(!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window)){throw new Error('Web-Push wird von diesem Browser nicht unterstützt')}
    const permission=await Notification.requestPermission();if(permission!=='granted')throw new Error('Benachrichtigungen wurden nicht freigegeben');
    const conf=await api('/push/public-key');if(!conf.enabled||!conf.public_key)throw new Error('Der Server hat noch keine VAPID-Schlüssel. Siehe VAPID-SETUP.md');
    const reg=await navigator.serviceWorker.ready;let sub=await reg.pushManager.getSubscription();if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64ToUint8Array(conf.public_key)});
    const j=sub.toJSON();await api('/push/subscribe',{method:'POST',json:{endpoint:j.endpoint,p256dh:j.keys.p256dh,auth:j.keys.auth}});try{toast('Push aktiviert','Dringende Meldungen und Statusänderungen können jetzt auf diesem Gerät erscheinen.')}catch{};await renderSecurity();return sub;
  }

  async function forgotPassword(){
    const email=prompt('Für welches Konto soll das Passwort zurückgesetzt werden?',$('portalEmail')?.value||''); if(!email)return;
    try{const out=await api('/auth/request-password-reset',{method:'POST',json:{email}});if(out.dev_reset_token){const pw=prompt('Pilotbetrieb: Neues Passwort (mindestens 10 Zeichen) eingeben:');if(!pw)return;await api('/auth/reset-password',{method:'POST',json:{token:out.dev_reset_token,new_password:pw}});try{toast('Passwort geändert','Sie können sich jetzt mit dem neuen Passwort anmelden.')}catch{}}else try{toast('Reset angefordert','Falls das Konto existiert, wurde eine E-Mail vorbereitet.')}catch{}}catch(err){try{toast('Reset fehlgeschlagen',err.message)}catch{alert(err.message)}}
  }

  async function handleAuthLink(){
    const params=new URLSearchParams(location.search);const reset=params.get('reset_token'),invite=params.get('invite_token');if(!reset&&!invite)return;
    const pw=prompt(invite?'Einladung annehmen: Neues Passwort mit mindestens 10 Zeichen festlegen.':'Passwort zurücksetzen: Neues Passwort mit mindestens 10 Zeichen festlegen.');if(!pw)return;
    try{if(invite)await api('/auth/accept-invite',{method:'POST',json:{token:invite,new_password:pw}});else await api('/auth/reset-password',{method:'POST',json:{token:reset,new_password:pw}});params.delete('reset_token');params.delete('invite_token');history.replaceState({},'',location.pathname+(params.toString()?'?'+params.toString():''));try{toast(invite?'Einladung angenommen':'Passwort geändert','Sie können sich jetzt anmelden.')}catch{}}catch(err){try{toast('Link konnte nicht verwendet werden',err.message)}catch{alert(err.message)}}
  }

  function patchLoginUI(){
    const card=document.querySelector('.portal-login-card'); if(!card)return;
    const h=card.querySelector('h2'); if(h) h.textContent='Pilot-Zugang';
    const badge=card.querySelector('.demo-badge'); if(badge){badge.textContent='Pilot – Datenbank & Rollen aktiv';badge.style.background='#eaf6ef';badge.style.borderColor='#c9e6d4';badge.style.color='#257148';}
    const roles=card.querySelector('.role-picker'); if(roles) roles.style.display='none';
    const note=card.querySelector('.portal-login-note'); if(note) note.textContent='V16 Pre-Launch: Backend, Rollen, Termine, Tickets, Uploads, Einladungen, Passwort-Reset und Admin-MFA sind aktiv. Vor Livebetrieb zeigt der Readiness-Check, welche Produktionspunkte noch fehlen.';
    const btn=card.querySelector('button[type="submit"]'); if(btn) btn.textContent='Portal öffnen';
    if($('portalEmail') && $('portalEmail').value==='demo@steinbach.de') $('portalEmail').value='kunde@steinbach.local';
    if($('portalPassword') && $('portalPassword').value==='demo') $('portalPassword').value='Kunde!2026Demo';
  }

  function attach(){
    patchLoginUI();
    if ($('teamBackCustomer')) $('teamBackCustomer').style.display='none';
    if ($('simulateTeamReply')) $('simulateTeamReply').style.display='none';
    $('portalLoginForm')?.addEventListener('submit',loginHandler,true);
    $('portalLogout')?.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();logoutUI()},true);
    $('teamLogout')?.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();logoutUI()},true);
    $('portalDamageForm')?.addEventListener('submit',createTicketHandler,true);
    $('objectForm')?.addEventListener('submit',objectFormHandler,true);
    $('portalMessageForm')?.addEventListener('submit',customerMessageHandler,true);
    $('teamMessageForm')?.addEventListener('submit',teamMessageHandler,true);
    $('referralForm')?.addEventListener('submit',referralHandler,true);
    $('serviceModelGrid')?.addEventListener('click',serviceClickCapture,true);
    $('saveTicketDetail')?.addEventListener('click',e=>saveTicketCapture(e,false),true);
    $('ticketMarkDone')?.addEventListener('click',e=>saveTicketCapture(e,true),true);
    $('teamNewTicketForm')?.addEventListener('submit',newInternalTicketHandler,true);
    $('appointmentForm')?.addEventListener('submit',appointmentFormHandler,true);
    $('inviteUserForm')?.addEventListener('submit',inviteUserHandler,true);
    $('mfaSetupBtn')?.addEventListener('click',mfaSetup,true);
    $('mfaDisableBtn')?.addEventListener('click',mfaDisable,true);
    $('forgotPasswordBtn')?.addEventListener('click',forgotPassword,true);
    $('enableNotifications')?.addEventListener('click',async e=>{e.preventDefault();e.stopImmediatePropagation();try{await subscribePush()}catch(err){try{toast('Push nicht aktiviert',err.message)}catch{alert(err.message)}}},true);
    $('adminPushTest')?.addEventListener('click',async()=>{try{await api('/push/test',{method:'POST'});toast('Push-Test gesendet','Bitte Benachrichtigungen auf diesem Gerät prüfen.')}catch(err){toast('Push-Test nicht möglich',err.message)}},true);
    $('adminRefreshDelivery')?.addEventListener('click',renderSecurity,true);
    $('refreshTeamAppointments')?.addEventListener('click',syncAppointments,true);
    document.addEventListener('click',e=>{const c=e.target.closest('[data-appt-confirm]'),m=e.target.closest('[data-appt-move]'),d=e.target.closest('[data-appt-done]');if(c){e.preventDefault();updateAppointment(c.dataset.apptConfirm,'confirm')}if(m){e.preventDefault();updateAppointment(m.dataset.apptMove,'move')}if(d){e.preventDefault();updateAppointment(d.dataset.apptDone,'done')}},true);
    document.addEventListener('click',adminQueueCapture,true);
    window.addEventListener('online',()=>state.user&&syncAll().catch(()=>{}));
    document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&state.user)syncAll().catch(()=>{})});
  }

  attach();
  handleAuthLink();
})();
