// Admin: profiles and devices.
// ---------------------------------------------------------------- profiles and devices (admin)
// For many profiles: search, filter, sort and pages of 25 (the Spark does it); details open per profile.
// Liste + Detail (Klar 4, Redesign Stufe 4): a row per person with initials, one line below and the state as a dot with a
// word; the open person beside the list (from 660 px of the box, app.css .ld-wide), on a phone as a page with „‹ Personen“.
// Everything is built with textContent (ichteile.js ldRow …), names never go in as HTML.
const PL={q:'',show:'',sort:'name',page:0,open:'',names:[],timer:null};
const pwhen=s=>s?new Date(s*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
const pCount=(n,one,many)=>`${n} ${n===1?one:many}`;
// the kind of a device as a symbol: speaker, iPhone app, watch, terminal, Home Assistant, own program (key)
const PDEV={speaker:'speaker',app:'mobile',watch:'watch',tui:'fern',room:'home',key:'key'};   // names in icons.js
const pDevIcon=x=>ldIco(PDEV[x.speaker?'speaker':x.kind==='app'||x.app?'app':PDEV[x.kind]?x.kind:'key']);
const perr=(id,e)=>{$(id).innerHTML=`<span class="err">${esc(e.message)}</span>`};
// The profile of a device: a list of all profiles, sorted by name. Keys a profile set up itself under Ich
// (speaker, iPhone app, Pebble watch, terminal, Home Assistant) stay with it: they show the name and where they are managed.
const popts=(sel,first)=>(first?`<option value="">${esc(first)}</option>`:'')+[...PL.names].sort((a,b)=>a.name.localeCompare(b.name))
  .map(u=>`<option value="${esc(u.id)}"${u.id===sel?' selected':''}>${esc(u.name)}</option>`).join('');
const dkind=x=>x.speaker?t('Lautsprecher, eingerichtet unter Ich → Lautsprecher','Speaker, set up under Me → Speakers')
  :x.kind==='app'||x.app?t('iPhone-App, nur fragen und hören, gekoppelt unter Ich → iPhone-App','iPhone app, only asks and listens, paired under Me → iPhone app')
  :x.kind==='watch'?t('Pebble-Uhr, gekoppelt unter Ich → Pebble-Uhr','Pebble watch, paired under Me → Pebble watch')
  :x.kind==='tui'?t('Terminal, gekoppelt unter Ich → Terminal','Terminal, paired under Me → Terminal')
  :x.kind==='room'?t('Home Assistant, erzeugt unter Ich → Raum-Modus','Home Assistant, made under Me → Room mode'):'';
// filters as a segment, search and sort on top (the Spark knows more filters: mfa, room, for the other pages)
const PSHOW=()=>[['',t('Alle','All')],['idle',t('Ungenutzt','Unused')],['nodev',t('Ohne Gerät','No device')],['nomfa',t('Ohne 2FA','No 2FA')]];
function profFilter(){const f=$('pfilter');if(!f.dataset.done){f.dataset.done='1';
    const q=document.createElement('input');q.id='pq';q.type='search';q.maxLength=40;q.placeholder=t('Suchen: Name, Rufname oder Gerät','Search: name, call name or device');q.setAttribute('aria-label',q.placeholder);
    const so=document.createElement('select');so.id='psort';so.setAttribute('aria-label',t('Sortieren','Sort'));
    for(const [v,l] of [['name',t('nach Name','by name')],['recent',t('zuletzt benutzt zuerst','last used first')],['new',t('neueste zuerst','newest first')]]){const o=document.createElement('option');o.value=v;o.textContent=l;so.appendChild(o)}
    const seg=document.createElement('div');seg.id='pshow';f.append(q,so);f.after(seg);
    q.oninput=()=>{clearTimeout(PL.timer);PL.timer=setTimeout(()=>{PL.q=q.value;PL.page=0;loadProf()},250)};
    so.onchange=()=>{PL.sort=so.value;PL.page=0;loadProf()}}
  $('pshow').replaceChildren(ldSeg(PSHOW(),PL.show,k=>{PL.show=k;PL.page=0;loadProf()},t('Filter','Filter')))}
const PROLE=()=>typeof ROLE_NAME!=='undefined'?ROLE_NAME:{admin:t('Admin','Admin'),manager:t('Verwalter','Manager')};
// the line below a name: role, call name, last use, devices, facts; the state on the right: listening, setup still open
function pRow(u){const R=PROLE(),sub=[u.role?R[u.role]||u.role:'',u.call,u.last?t('zuletzt ','last ')+pwhen(u.last):t('noch nie benutzt','never used'),
    pCount(u.devices,t('Gerät','device'),t('Geräte','devices')),pCount(u.facts,t('Fakt','fact'),t('Fakten','facts'))].filter(Boolean).join(' · ');
  const st=u.room?ldSt('ok',t('hört zu','listening')):u.setup&&u.setup.total&&u.setup.done<u.setup.total?ldSt('warn',t('eingerichtet ','set up ')+u.setup.done+'/'+u.setup.total)
    :u.mfa?ldSt('ok',t('2. Schritt','2nd step')):null;
  const r=ldRow({lead:ldAva(u.name),title:u.name,sub,right:[st],on:PL.open===u.id,act:()=>pOpen(u.id)});r.dataset.prow=u.id;return r}
function pOpen(id){PL.open=id;loadProf();const b=$('pbox');if(b&&NARROW())b.scrollIntoView({block:'start'})}
async function loadProf(){profFilter();let d;const keep=window.lzKeep?lzKeep($('prof')):()=>{};   // open parts and the scroll stay (ruhige-seiten.md)
  try{d=await (await api('/api/admin/profiles?'+new URLSearchParams({q:PL.q,show:PL.show,sort:PL.sort,page:PL.page,per:25}))).json()}catch(e){perr('pmsg',e);return}
  PL.page=d.page;PL.names=d.names;const name=id=>(d.names.find(u=>u.id===id)||{}).name||'?';
  $('duser').innerHTML=popts($('duser').value,t('Profil wählen …','Pick a profile …'));
  const list=$('proflist'),rows=d.users.map(pRow);
  // Gäste as the first row: who talks without a profile, and what they get (nothing to open)
  if(d.guests&&!PL.q&&!PL.show&&!d.page){const g=ldRow({lead:ldAva('','user'),title:t('Gäste','Guests'),sub:d.guests.public
      ?t('Nur Fragen und Antworten, keine Funktionen und keine Werkzeuge, nie persönliche Daten','Questions and answers only, no functions and no tools, never personal data'):t('Ohne Profil spricht niemand mit dem Assistenten.','Without a profile nobody talks to the assistant.'),
    right:[ldSt(d.guests.public?'ok':'',d.guests.public?t('Gastzugang an','guest access on'):t('Gastzugang aus','guest access off'))]});g.classList.add('pguest');rows.unshift(g)}
  list.replaceChildren(...(rows.length?rows:[ldEmpty('users',d.all?t('Kein Profil passt.','No profile matches.'):t('Noch keine Profile.','No profiles yet.'))]));
  const pages=Math.max(1,Math.ceil(d.total/d.per));
  $('ppager').innerHTML=`<span class="mut">${d.total===d.all?d.all+' '+t('Profile','profiles'):d.total+' '+t('von','of')+' '+d.all+' '+t('Profilen','profiles')}${pages>1?' · '+t('Seite','page')+' '+(d.page+1)+'/'+pages:''}</span>${pages>1?`<button class="b" type="button" data-ppage="${d.page-1}"${d.page?'':' disabled'} aria-label="${esc(t('Seite zurück','Previous page'))}">${ic('back')}</button><button class="b" type="button" data-ppage="${d.page+1}"${d.page+1<pages?'':' disabled'} aria-label="${esc(t('Seite weiter','Next page'))}">${ic('chev')}</button>`:''}`;
  $('ppager').querySelectorAll('[data-ppage]').forEach(b=>b.onclick=()=>{PL.page=+b.dataset.ppage;loadProf()});
  // the open person beside the list (a phone shows it as a page instead of the list)
  const ps=$('pside'),u=d.users.find(x=>x.id===PL.open);$('pbox').classList.toggle('ld-sel',!!u);ps.classList.toggle('ld-idle',!u);
  const old=$('pdetail');if(u&&old&&old.dataset.pid===u.id&&ps.contains(old)){}   // the same person stays open: no „…“ in between
  else if(u){const h=icEl('div','pdhead'),bk=icEl('button','b ld-back');bk.type='button';bk.append(icSvg('back',16),' '+t('Personen','People'));bk.onclick=()=>{PL.open='';loadProf()};
    const nm=icEl('span');nm.append(icEl('b','',u.name),icEl('small','',u.call||PROLE()[u.role]||t('Profil','Profile')));
    const x=icEl('button','fdx');x.type='button';x.setAttribute('aria-label',t('Schließen','Close'));x.title=t('Schließen','Close');x.appendChild(icSvg('x',16));x.onclick=()=>{PL.open='';loadProf()};
    h.append(bk,ldAva(u.name),nm,x);const det=icEl('div','mut','…');det.id='pdetail';det.dataset.pid=u.id;ps.replaceChildren(h,det)}
  else ps.replaceChildren(ldEmpty('user',t('Person antippen: Zugang, Geräte, Funktionen und Rechte stehen dann hier.','Tap a person: access, devices, functions and rights then show here.')));
  $('dadd').disabled=!d.all;
  $('devlist').replaceChildren(...(d.devices.length?d.devices.map(x=>{const k=dkind(x),right=[];
      if(k){const f=icEl('span');f.title=t('Fest bei diesem Profil. Zum Wechseln dort entfernen und unter dem anderen Profil neu einrichten.','Fixed to this profile. To change it, remove it there and set it up again under the other profile.');
        f.append(name(x.user)+' ',icEl('small','mut'));f.lastChild.append(icSvg('lock',12),' '+t('fest','fixed'));right.push(f)}
      else{const s=document.createElement('select');s.dataset.dmove=x.id;s.setAttribute('aria-label',t('Profil','Profile'));s.innerHTML=popts(x.user);s.onchange=()=>devUser(x.id,s.value);right.push(s)}
      const del=icEl('button','b',t('Löschen','Delete'));del.type='button';del.dataset.ddel=x.id;del.onclick=()=>delDev(x.id,x.name,x.speaker?'1':'');right.push(del);
      const sub=(k?k+' · ':'')+t('zuletzt','last used')+': '+(x.last?pwhen(x.last.t)+(x.last.ip?' · '+x.last.ip:''):t('noch nie','never'));
      return ldRow({lead:pDevIcon(x),title:x.name,sub,right:[x.room?ldSt('ok',t('hört zu','listening')):null,...right]})})
    :[ldEmpty('key',PL.q||PL.show?t('Keine Geräte bei den gezeigten Profilen.','No devices with the profiles shown.'):t('Noch keine Geräte.','No devices yet.'))]));
  if(PL.open&&$('pdetail'))profDetail(PL.open,keep);else keep()}
// One profile in detail (plan „Vereinheitlichen“ Phase 5): Zugang (PIN, zweiter Schritt, Rolle, Browser), Rufname,
// Geräte, Funktionen „n von m an“ with the functions blocked for this profile (tap lifts the block), Rechte (Aufträge, Spark-Update aus der App, Platz für
// Uploads) and Löschen. Everything that used to sit on other pages per profile is here; the pages stay for the overview.
const pbtn=(id,l,extra='')=>`<button class="b" type="button" id="${id}"${extra}>${esc(l)}</button>`;
const pmb=b=>b>=1024**2?(b/1024**2).toFixed(b>=10*1024**2?0:1)+' MB':Math.ceil(b/1024)+' KB';
async function profDetail(id,keep){keep=keep||(window.lzKeep&&$('pdetail')?lzKeep($('pdetail')):null);let u;try{u=await (await api('/api/admin/profiles/'+encodeURIComponent(id))).json()}catch(e){perr('pmsg',e);return}
  const R=PROLE(),r=u.rights,h3=x=>`<h3 class="sec">${esc(x)}</h3>`,sel=(v,cur,l)=>`<option value="${esc(v)}"${v===cur?' selected':''}>${esc(l)}</option>`;
  let role='';
  if(u.main)role=setRow(esc(t('Admin-Rechte','Admin rights')),esc(u.mfa?t('Admin darf alles außer dem Panel-Passwort selbst, Verwalter nur Zustand, Profile und Funktionen. Gilt sofort in seiner Anmeldung.','An admin may do everything but the panel password itself, a manager only status, profiles and functions. In effect at once in their sign-in.')
      :t('Erst mit dem zweiten Anmeldeschritt des Profils.','Only with the profile\'s second login step.')),
    `<select id="prole" aria-label="${esc(t('Admin-Rechte','Admin rights'))}"${u.mfa||u.role?'':' disabled'}>${sel('',u.role,t('keine','none'))}${sel('admin',u.role,R.admin)}${sel('manager',u.role,R.manager)}</select>`);
  else if(u.role)role=setRow(esc(t('Admin-Rechte','Admin rights')),esc(t('Ändert nur ein Admin.','Only an admin changes it.')),`<span class="pill">${esc(R[u.role]||u.role)}</span>`);
  const sess=u.sessions.map(x=>`<li><span>${esc(x.agent)}<br><small class="mut">${t('angemeldet','signed in')} ${esc(pwhen(x.first))} · ${t('zuletzt','last used')} ${esc(pwhen(x.last))}</small></span><button class="b" type="button" data-psess="${esc(x.id)}">${t('Abmelden','Sign out')}</button></li>`).join('')
    ||`<li class="mut">${t('Kein Browser angemeldet.','No browser signed in.')}</li>`;
  // trusted browsers (second step without code at sign-in, mfa.py): remove one, it asks for a code again
  const trust=(u.trusted||[]).map(x=>`<li><span>${esc(x.name)}<br><small class="mut">${t('seit','since')} ${esc(pwhen(x.first))} · ${t('zuletzt','last used')} ${esc(pwhen(x.last))}</small></span><button class="b" type="button" data-ptrust="${esc(x.id)}">${t('Entfernen','Remove')}</button></li>`).join('');
  let rights='';
  if(r){const off=t('Auf dem Spark aus','Off on the Spark');
    rights=h3(t('Rechte','Rights'))
    +setRow(esc(t('Aufträge im Hintergrund','Background jobs')),esc(t('Was der Assistent für dieses Profil allein erledigen darf. Gilt sofort, ohne eigenen Schalter.','What the assistant may do alone for this profile. Applies at once, without an own switch.')),
      `<select id="pagent" aria-label="${esc(t('Aufträge','Jobs'))}">${sel('',r.agent.level,t('aus','off'))}${sel('read',r.agent.level,t('nur lesen und berichten','read and report only'))}${sel('act',r.agent.level,t('auch handeln mit „Ja“','also act after "Yes"'))}</select>`,{why:r.agent.spark?'':off})
    +(r.vorrang?setRow(esc(t('Vorrang','Priority')),esc(t('Reden mehrere gleichzeitig, kommt dieses Profil mit Sprachausgabe, Spracherkennung und Sprachmodell zuerst dran. Höchstens ','When several people talk at once, this profile goes first for speech output, recognition and the language model. At most ')+r.vorrang.max+t(' Profile.',' profiles.')),
      `<select id="pvor" aria-label="${esc(t('Vorrang','Priority'))}">${sel('',r.vorrang.level,t('normal','normal'))}${sel('vorrang',r.vorrang.level,t('Vorrang','priority'))}${sel('hinten',r.vorrang.level,t('hinten anstellen','last in line'))}</select>`,{why:r.vorrang.spark?'':off}):'')
    +(r.tageslimit?setRow(esc(t('Ohne Tageslimit','No daily limit')),esc(r.tageslimit.admin?t('Als Admin ohnehin ohne Tageslimit. Platz und Warteschlangen gelten weiter.','As an admin without daily limits anyway. Space and queues still hold.'):t('Bilder, Musik, Kontingent und Dungeon-Bilder ohne Tagesgrenze, auch ohne zweiten Anmeldeschritt. Platz und Warteschlangen gelten weiter.','Pictures, music, allowance and Dungeon pictures without a daily cap, also without the second login step. Space and queues still hold.')),
      `<label class="chk"><input type="checkbox" id="pfrei"${r.tageslimit.frei||r.tageslimit.admin?' checked':''}${r.tageslimit.admin?' disabled':''}> ${t('frei','free')}</label>`):'')
    +setRow(esc(t('Spark-Update aus der iPhone-App','Spark update from the iPhone app')),esc(u.mfa?t('Hinweise bekommen und das Update selbst starten (mit Face ID und Code).','Get notices and start the update itself (with Face ID and code).'):t('Starten geht erst mit dem zweiten Anmeldeschritt.','Starting needs the second login step first.')),
      `<span class="row" style="gap:10px;flex-wrap:nowrap"><label class="chk"><input type="checkbox" id="pupdn"${r.update.notify?' checked':''}> ${t('Hinweise','Notices')}</label><label class="chk"><input type="checkbox" id="pupds"${r.update.start?' checked':''}${u.mfa?'':' disabled'}> ${t('Starten','Start')}</label></span>`,{why:r.update.spark?'':off})
    +setRow(esc(t('Platz für Uploads','Space for uploads')),esc(t('Belegt ','Used ')+pmb(r.quota.used)+t(' von ',' of ')+r.quota.mb+' MB'+(r.quota.own?'':t(' (Standard)',' (default)'))),
      `<span class="row" style="gap:6px;flex-wrap:nowrap"><input id="pquota" type="number" min="50" max="50000" step="50" style="width:90px" value="${r.quota.own?r.quota.mb:''}" placeholder="${r.quota.default_mb}" aria-label="MB">${pbtn('pquotasave',t('Speichern','Save'))}</span>`,{why:r.quota.spark?'':t('Dokumente sind auf dem Spark aus','Documents are off on the Spark')})}
  $('pdetail').innerHTML=`<div class="pdet"><div class="intro sm">${t('Angelegt','Created')}: ${esc(pwhen(u.created))} · ${t('zuletzt benutzt','last used')}: ${esc(pwhen(u.last))} · ${u.facts} ${t('gemerkte Fakten','remembered facts')} · ${u.msg?t('Nachrichten an','messages on'):t('Nachrichten aus','messages off')}</div>
    ${h3(t('Zugang','Access'))}
    ${setRow(esc('PIN'),esc(t('Eine neue PIN meldet alle Browser dieses Profils ab.','A new PIN signs out every browser of this profile.')),pbtn('ppinnew',t('PIN ändern','Change PIN')))}
    ${setRow(esc(t('PIN-Link','PIN link')),esc(t('Ein Link, mit dem die Person ihre PIN selbst wählt (gilt einen Tag, einmal). Besser als eine PIN weiterzusagen.','A link with which the person picks the PIN themselves (one day, once). Better than passing a PIN on.')),pbtn('ppinlink',t('PIN-Link','PIN link')))}
    <div id="ppinout"></div>
    ${setRow(esc(t('Zweiter Anmeldeschritt','Second login step')),esc(u.mfa?t('An. Zurücksetzen, falls Handy und Wiederherstellungscodes weg sind.','On. Reset it if phone and recovery codes are lost.'):t('Aus. Das Profil schaltet ihn unter Ich → Sicherheit ein.','Off. The profile switches it on under Me → Security.')),
      u.mfa?pbtn('pmfa',t('Zurücksetzen','Reset')):`<span class="mut">${t('aus','off')}</span>`)}
    ${role}
    <b>${t('Angemeldete Browser','Signed-in browsers')}</b><ul class="facts" id="psess">${sess}</ul>${trust?`<b>${t('Vertraute Browser','Trusted browsers')}</b><ul class="facts" id="ptrust">${trust}</ul>`:''}
    ${h3(t('Rufname','Call name'))}
    <div class="rowin"><input id="pcall" maxlength="40" value="${esc(u.call||'')}" placeholder="${esc(t('z. B. Thomas M. oder Papa','e.g. Thomas M. or Dad'))}" aria-label="${esc(t('Rufname für Nachrichten','Call name for messages'))}"><button class="b" type="button" id="pcallsave">${t('Speichern','Save')}</button></div>
    <div class="fh">${t('So können andere ihn in Nachrichten nennen, wenn Namen sich ähneln. Muss eindeutig sein.','How others can name this profile in messages when names are alike. Must be unique.')}</div>
    ${h3(t('Geräte','Devices'))}<ul class="facts">${u.devices.map(x=>`<li><span>${esc(x.name)}${x.room?` <span class="pill ok">${t('hört zu','listening')}</span>`:''} <small class="mut">${x.speaker?t('Lautsprecher','speaker'):x.app?t('iPhone-App','iPhone app'):t('Schlüssel','key')} · ${t('zuletzt','last used')}: ${x.last?esc(pwhen(x.last.t)):t('noch nie','never')}</small></span></li>`).join('')||`<li class="mut">${t('Keine.','None.')}</li>`}</ul>
    ${h3(t('Funktionen','Functions'))}
    ${setRow(esc(t(`darf ${u.features.on} von ${u.features.of} freigegebenen Funktionen`,`may use ${u.features.on} of ${u.features.of} released functions`)),esc(t('Was im Spark an ist, gilt sofort für jedes Profil. Sperren setzt du in der Funktion unter „Wer darf es“; hier hebst du sie mit einem Tipp auf.','What is switched on in the Spark works at once for every profile. You set blocks in the function under "Who may use it"; here one tap lifts them.')),'')}
    <div class="wchips" id="pblk"></div>
    ${u.setup&&u.setup.total?setRow(joinSetupLine(u.setup),esc(u.setup.open.length?t('Offen: ','Open: ')+u.setup.open.join(', '):t('Alles eingerichtet.','Everything set up.')),u.setup.open.length?pbtn('premind',t('Erinnern','Remind')):''):''}
    ${rights}
    ${h3(t('Daten','Data'))}
    ${setRow(esc(t('Profil löschen','Delete profile')),esc(t('Mit Gedächtnis, Gesprächen und Geräten. Geht nicht rückgängig.','With memory, conversations and devices. Cannot be undone.')),pbtn('pdel',t('Löschen','Delete')))}</div>`;if(keep)keep();
  const ok=m=>{$('pmsg').textContent=m},again=()=>profDetail(id);
  $('ppinlink').onclick=()=>joinPinLink(id,u.name,$('ppinout'));
  if($('premind'))$('premind').onclick=async()=>{try{const r=await (await api('/api/admin/profiles/'+encodeURIComponent(id)+'/remind',jpost('POST',{}))).json();
    ok(r.sent?t('Erinnerung geschickt.','Reminder sent.'):t('Keine Mitteilung möglich: das Profil hat noch kein Gerät mit Mitteilungen.','No notification possible: the profile has no device with notifications yet.'))}catch(e){perr('pmsg',e)}};
  $('pcallsave').onclick=async()=>{try{const r=await (await api('/api/admin/profiles/'+encodeURIComponent(id)+'/call',jpost('PUT',{call:$('pcall').value}))).json();
    ok(r.call?t('Rufname gespeichert: ','Call name saved: ')+r.call:t('Rufname entfernt.','Call name removed.'));loadProf()}catch(e){perr('pmsg',e)}};
  if($('pmfa'))$('pmfa').onclick=()=>resetMfa(id,u.name);$('ppinnew').onclick=()=>newPin(id,u.name);$('pdel').onclick=()=>delProf(id,u.name);
  pBlocked(id,u.name);
  if($('ptrust'))$('ptrust').querySelectorAll('[data-ptrust]').forEach(b=>b.onclick=async()=>{try{await api('/api/admin/profiles/'+encodeURIComponent(id)+'/trusted/'+encodeURIComponent(b.dataset.ptrust),{method:'DELETE'});ok(t('Entfernt: fragt wieder einen Code.','Removed: asks for a code again.'))}catch(e){perr('pmsg',e)}again()});
  $('psess').querySelectorAll('[data-psess]').forEach(b=>b.onclick=async()=>{try{await api('/api/admin/profiles/'+encodeURIComponent(id)+'/sessions/'+encodeURIComponent(b.dataset.psess),{method:'DELETE'});ok(t('Abgemeldet.','Signed out.'))}catch(e){perr('pmsg',e)}again()});
  if($('prole'))$('prole').onchange=async()=>{const v=$('prole').value;
    if(!v&&!confirm(t('Rolle entziehen? Die Admin-Rechte enden sofort.','Take the role away? The admin rights end at once.'))){$('prole').value=u.role;return}
    try{await api('/api/admin/roles/'+encodeURIComponent(id),jpost('PUT',{role:v}));ok(t('Rolle gespeichert.','Role saved.'));loadProf()}catch(e){perr('pmsg',e);$('prole').value=u.role}};
  if(!r)return;
  if($('pfrei'))$('pfrei').onchange=async()=>{try{await api('/api/admin/profiles/'+encodeURIComponent(id)+'/tageslimit',jpost('PUT',{frei:$('pfrei').checked}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e);again()}};
  if($('pvor'))$('pvor').onchange=async()=>{try{await api('/api/admin/vorrang/'+encodeURIComponent(id),jpost('PUT',{level:$('pvor').value}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e);again()}};
  $('pagent').onchange=async()=>{try{await api('/api/admin/agent/levels/'+encodeURIComponent(id),jpost('PUT',{level:$('pagent').value}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e);again()}};
  const upd=async()=>{try{await api('/api/admin/iphone-update/'+encodeURIComponent(id),jpost('PUT',{notify:$('pupdn').checked,start:$('pupds').checked}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e)}again()};
  $('pupdn').onchange=upd;$('pupds').onchange=upd;
  $('pquotasave').onclick=async()=>{const v=$('pquota').value.trim();
    try{await api('/api/admin/wissen/quota',jpost('POST',{owner:id,mb:v===''?null:Number(v)}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e)}again()}}
const jpost=(m,b)=>({method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
$('padd').onclick=async()=>{try{await api('/api/admin/profiles',jpost('POST',{name:$('pname').value,pin:$('ppin').value}));
    $('pmsg').textContent=t('Angelegt: ','Created: ')+$('pname').value;$('pname').value=$('ppin').value='';$('pnew').open=false;loadProf()}catch(e){perr('pmsg',e)}};
// a new PIN in hidden fields, typed twice, with its rule, never in a browser prompt in plain text (code check 19.10. D10)
window.newPin=(id,n)=>{const old=$('pinbox');if(old)old.remove();const box=document.createElement('div');box.id='pinbox';box.className='card pinbox';
  box.innerHTML=`<b></b><div class="fh"></div><input type="password" id="pinnew1" autocomplete="new-password"><input type="password" id="pinnew2" autocomplete="new-password"><div class="row"><button class="b p" type="button" id="pinok"></button><button class="b" type="button" id="pinno"></button><span class="err" id="pinerr"></span></div>`;
  box.querySelector('b').textContent=t('Neue PIN für ','New PIN for ')+n;
  box.querySelector('.fh').textContent=t('4 bis 64 Zeichen ohne Leerzeichen. Meldet alle Browser dieses Profils ab.','4 to 64 characters without spaces. Logs out all browsers of this profile.');
  const a=box.querySelector('#pinnew1'),b=box.querySelector('#pinnew2');a.placeholder=t('Neue PIN','New PIN');b.placeholder=t('Noch einmal','Again');
  a.setAttribute('aria-label',a.placeholder);b.setAttribute('aria-label',b.placeholder);
  box.querySelector('#pinok').textContent=t('PIN setzen','Set PIN');box.querySelector('#pinno').textContent=t('Abbrechen','Cancel');
  box.querySelector('#pinno').onclick=()=>box.remove();
  box.querySelector('#pinok').onclick=async()=>{const e=box.querySelector('#pinerr'),pin=a.value;
    if(!/^\S{4,64}$/.test(pin)){e.textContent=t('4 bis 64 Zeichen ohne Leerzeichen.','4 to 64 characters without spaces.');return}
    if(pin!==b.value){e.textContent=t('Die beiden PINs sind verschieden.','The two PINs differ.');return}
    try{await api('/api/admin/profiles/'+id,jpost('PUT',{pin}));box.remove();$('pmsg').textContent=t('PIN geändert.','PIN changed.')}catch(err){perr('pinerr',err)}};
  const at=$('ppinnew');(at?at.closest('.row')||at.parentElement:$('pmsg')).after(box);a.focus()};
window.resetMfa=async(id,n)=>{if(!confirm(t('Zweiten Anmeldeschritt für „','Switch off the second login step for "')+n+t('“ ausschalten? Danach reicht wieder die PIN.','"? Then the PIN alone is enough again.')))return;
  try{await api('/api/admin/profiles/'+id+'/mfa',{method:'DELETE'});$('pmsg').textContent=t('Zurückgesetzt.','Reset.');loadProf()}catch(e){perr('pmsg',e)}};
window.delProf=async(id,n)=>{if(!confirm(t('Profil „','Delete profile "')+n+t('“ mit seinem ganzen Gedächtnis und seinen Geräten löschen?','" with all its memory and devices?')))return;
  try{await api('/api/admin/profiles/'+id,{method:'DELETE'});PL.open='';$('pmsg').textContent=t('Gelöscht: ','Deleted: ')+n;loadProf()}catch(e){perr('pmsg',e)}};
$('dadd').onclick=async()=>{const u=$('duser').value;if(!u){$('dmsg').innerHTML=`<span class="err">${esc(t('Bitte ein Profil wählen.','Please pick a profile.'))}</span>`;return}
  try{const r=await (await api('/api/admin/devices',jpost('POST',{name:$('dname').value,user:u}))).json();
    $('dmsg').innerHTML=`${t('Geräteschlüssel (wird nur jetzt angezeigt):','Device key (shown only now):')}<div class="token">${esc(r.token)}</div>`;$('dname').value='';$('duser').value='';$('dnew').open=false;loadProf()}
  catch(e){perr('dmsg',e)}};
window.devUser=async(id,u)=>{try{await api('/api/admin/devices/'+id,jpost('PUT',{user:u}));$('dmsg').textContent=t('Gerät umgehängt.','Device moved.')}catch(e){perr('dmsg',e)}loadProf()};
window.delDev=async(id,n,spk)=>{if(!confirm(t('Gerät „','Delete device "')+n+t('“ löschen? Sein Schlüssel gilt dann nicht mehr.','"? Its key stops working.')+(spk?t(' Der Lautsprecher muss danach neu eingerichtet werden.',' The speaker then has to be set up again.'):'')))return;
  await api('/api/admin/devices/'+id,{method:'DELETE'});$('dmsg').textContent='';loadProf()};
const sendTyped=()=>{const x=$('chattext').value.trim()||(typeof pics!=='undefined'&&pics.list.length?t('Was ist auf dem Bild?','What is in the picture?'):'');if(!x)return;$('chattext').value='';audioCtx();stopListening(true);stopAnswer();chat.nextSpoken=false;ask(x,null)};
$('chatsend').onclick=sendTyped;   // Enter sendet über feld.js (data-senden)
document.addEventListener('keydown',e=>{if(e.code!=='Space'||!$('chat').classList.contains('on')||/INPUT|TEXTAREA|SELECT|BUTTON/.test(document.activeElement.tagName))return;
  e.preventDefault();$('talk').click()});

// the functions the admin blocked for this one profile (features.blocked, the same data as Gesperrte Funktionen): one
// chip each, a tap allows it again (only the admin or a Verwalter lifts a block, Dominik 2026-10-13)
async function pBlocked(id,name){const box=$('pblk');if(!box)return;let d;try{d=await (await api('/api/admin/features')).json()}catch{return}
  if(!$('pblk'))return;box.textContent='';
  const fs=d.features.filter(f=>f.blockable!==false&&f.cells[id]===false&&!(f.inherited&&f.inherited[id]));
  if(!fs.length){const p=document.createElement('span');p.className='mut';p.textContent=t('Nichts gesperrt.','Nothing blocked.');box.appendChild(p);return}
  for(const f of fs){const b=document.createElement('button');b.type='button';b.className='wchip';const nm=f.name[L==='en'?1:0];b.textContent='⊘ '+nm;
    const label=t('gesperrt, antippen erlaubt wieder','blocked, tap to allow again');b.title=label;b.setAttribute('aria-label',`${nm} – ${name}: ${label}`);
    b.onclick=async()=>{b.disabled=true;try{await api(`/api/admin/features/${encodeURIComponent(f.key)}/profiles/${encodeURIComponent(id)}`,xjson('PUT',{on:true}));
      pBlocked(id,name);if(window.loadWho&&$('whobox'))loadWho()}catch(e){alert(e.message);b.disabled=false}};box.appendChild(b)}}
