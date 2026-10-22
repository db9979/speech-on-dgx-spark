// Admin: profiles and devices.
// ---------------------------------------------------------------- profiles and devices (admin)
// For many profiles: search, filter, sort and pages of 25 (the Spark does it); details open per profile.
const PL={q:'',show:'',sort:'name',page:0,open:'',names:[],timer:null};
const pwhen=s=>s?new Date(s*1000).toLocaleString([], {dateStyle:'short',timeStyle:'short'}):t('noch nie','never');
// a row of the list: initials on a colour of the name (the same colours as the symbols), counts in words, setup as a bar
const PAVC=['blue','violet','teal','green','amber','red'];
const pAvatar=n=>{const w=String(n||'?').trim().split(/\s+/),i=(w.length>1?w[0][0]+w[1][0]:String(n||'?').slice(0,2)).toUpperCase();
  let h=0;for(const c of String(n))h=(h*31+c.charCodeAt(0))>>>0;return `<span class="cic c-${PAVC[h%PAVC.length]} pav" aria-hidden="true">${esc(i)}</span>`};
const pCount=(n,one,many)=>`${n} ${n===1?one:many}`;
const pSetup=s=>`<span class="psetup${s.done>=s.total?' ok':''}" title="${esc(t('Einrichten','Setup'))}"><span class="psbar"><i style="width:${Math.round(100*s.done/s.total)}%"></i></span>${s.done}/${s.total}</span>`;
// the kind of a device as a symbol: speaker, iPhone app, watch, terminal, Home Assistant, own program (key)
const PDEV={speaker:['teal','M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 010 6'],app:['blue','M7 2h10v20H7zM11 18h2'],watch:['violet','M8 6h8v12H8zM9 2h6v4M9 18v4h6v-4'],
  tui:['gray','M3 4h18v16H3zM7 9l3 3-3 3M12 15h5'],room:['amber','M3 11l9-7 9 7M5 10v10h14V10'],key:['green','M14 10a4 4 0 10-1.2 2.8L20 20M17 17l2-2']};
const pDevIcon=x=>{const d=PDEV[x.speaker?'speaker':x.kind==='app'||x.app?'app':PDEV[x.kind]?x.kind:'key'];
  return `<span class="cic c-${d[0]} pav" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="${d[1]}"/></svg></span>`};
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
function profFilter(){if($('pfilter').dataset.done)return;$('pfilter').dataset.done='1';
  const o=(v,l)=>`<option value="${v}">${esc(l)}</option>`;
  $('pfilter').innerHTML=`<input id="pq" type="search" placeholder="${esc(t('Suchen: Name, Rufname oder Gerät','Search: name, call name or device'))}" style="flex:2;min-width:140px" maxlength="40">
    <select id="pshow" style="width:auto">${o('',t('alle','all'))}${o('idle',t('seit 90 Tagen nicht benutzt','not used for 90 days'))}${o('nodev',t('ohne Gerät','without a device'))}${o('mfa',t('mit zweitem Schritt','with second step'))}${o('nomfa',t('ohne zweiten Schritt','without second step'))}${o('room',t('hört gerade zu','listening right now'))}</select>
    <select id="psort" style="width:auto">${o('name',t('nach Name','by name'))}${o('recent',t('zuletzt benutzt zuerst','last used first'))}${o('new',t('neueste zuerst','newest first'))}</select>`;
  $('pq').oninput=()=>{clearTimeout(PL.timer);PL.timer=setTimeout(()=>{PL.q=$('pq').value;PL.page=0;loadProf()},250)};
  $('pshow').onchange=()=>{PL.show=$('pshow').value;PL.page=0;loadProf()};$('psort').onchange=()=>{PL.sort=$('psort').value;PL.page=0;loadProf()}}
async function loadProf(){profFilter();let d;const keep=window.lzKeep?lzKeep($('prof')):()=>{};   // open parts and the scroll stay (ruhige-seiten.md)
  try{d=await (await api('/api/admin/profiles?'+new URLSearchParams({q:PL.q,show:PL.show,sort:PL.sort,page:PL.page,per:25}))).json()}catch(e){perr('pmsg',e);return}
  PL.page=d.page;PL.names=d.names;const name=id=>(d.names.find(u=>u.id===id)||{}).name||'?';
  $('duser').innerHTML=popts($('duser').value,t('Profil wählen …','Pick a profile …'));
  const side=pSide();
  $('proflist').innerHTML=d.users.map(u=>`<tr data-prow="${esc(u.id)}"${PL.open===u.id?' class="pon"':''}><td><div class="prow">${pAvatar(u.name)}<div class="pmid"><div class="pname"><b>${esc(u.name)}</b>${u.call?` <span class="mut">${esc(u.call)}</span>`:''}${u.role?` <span class="pill">${esc(PROLE()[u.role]||u.role)}</span>`:''}${u.mfa?` <span class="pill ok" title="${esc(t('mit zweitem Anmeldeschritt','with second login step'))}">2FA</span>`:''}${u.room?` <span class="pill ok">${t('hört zu','listening')}</span>`:''}</div>
    <div class="pmeta">${u.last?esc(t('zuletzt ','last ')+pwhen(u.last)):t('noch nie benutzt','never used')} · ${pCount(u.devices,t('Gerät','device'),t('Geräte','devices'))} · ${pCount(u.facts,t('Fakt','fact'),t('Fakten','facts'))}${u.msg?' · '+t('Nachrichten an','messages on'):''}</div></div>
    ${u.setup&&u.setup.total?pSetup(u.setup):''}</div></td>
    <td class="pgo"><button class="b pchev" type="button" data-popen="${esc(u.id)}" aria-label="${esc(PL.open===u.id?t('Schließen','Close'):t('Details','Details'))}" title="${esc(PL.open===u.id?t('Schließen','Close'):t('Details','Details'))}"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="${PL.open===u.id?'M6 15l6-6 6 6':'M9 6l6 6-6 6'}"/></svg></button></td></tr>${PL.open===u.id&&!side?`<tr><td colspan="2"><div id="pdetail" class="mut">…</div></td></tr>`:''}`).join('')
    ||`<tr><td class="mut">${d.all?t('Kein Profil passt.','No profile matches.'):t('Noch keine.','None yet.')}</td></tr>`;
  // Gäste as the first row: who talks without a profile, and what they get
  if(d.guests&&!PL.q&&!PL.show&&!d.page)$('proflist').insertAdjacentHTML('afterbegin',`<tr class="pguest"><td><div class="prow"><span class="cic c-gray pav" aria-hidden="true">?</span><div class="pmid"><div class="pname"><b>${t('Gäste','Guests')}</b> <span class="pill${d.guests.public?' ok':''}">${d.guests.public?t('Gastzugang an','guest access on'):t('Gastzugang aus','guest access off')}</span></div><div class="pmeta">${d.guests.public
      ?t('Nur Fragen und Antworten, keine Funktionen und keine Werkzeuge, nie persönliche Daten','Questions and answers only, no functions and no tools, never personal data'):t('Ohne Profil spricht niemand mit dem Assistenten.','Without a profile nobody talks to the assistant.')}</div></div></div></td>
    <td class="pgo"></td></tr>`);
  const pages=Math.max(1,Math.ceil(d.total/d.per));
  $('ppager').innerHTML=`<span class="mut">${d.total===d.all?d.all+' '+t('Profile','profiles'):d.total+' '+t('von','of')+' '+d.all+' '+t('Profilen','profiles')}${pages>1?' · '+t('Seite','page')+' '+(d.page+1)+'/'+pages:''}</span>${pages>1?`<button class="b" type="button" data-ppage="${d.page-1}"${d.page?'':' disabled'}>‹</button><button class="b" type="button" data-ppage="${d.page+1}"${d.page+1<pages?'':' disabled'}>›</button>`:''}`;
  $('ppager').querySelectorAll('[data-ppage]').forEach(b=>b.onclick=()=>{PL.page=+b.dataset.ppage;loadProf()});
  $('proflist').querySelectorAll('[data-popen]').forEach(b=>b.onclick=()=>{PL.open=PL.open===b.dataset.popen?'':b.dataset.popen;loadProf()});
  // wide: the open profile on the right (Paket 5), the whole line opens it; narrow it opens below its line
  if(side){$('proflist').querySelectorAll('[data-prow]').forEach(r=>r.onclick=e=>{if(e.target.closest('button,a,input,select'))return;PL.open=r.dataset.prow;loadProf()});
    const ps=$('pside'),u=d.users.find(x=>x.id===PL.open);
    const old=$('pdetail');if(u&&old&&old.dataset.pid===u.id&&ps.contains(old)){}   // the same person stays open: no „…“ in between
    else if(u){ps.textContent='';const h=document.createElement('div');h.className='pdhead';const b=document.createElement('b');b.textContent=u.name;
      const x=document.createElement('button');x.type='button';x.className='fdx';x.textContent='×';x.setAttribute('aria-label',t('Schließen','Close'));x.onclick=()=>{PL.open='';loadProf()};
      h.append(b,x);const det=document.createElement('div');det.id='pdetail';det.dataset.pid=u.id;det.className='mut';det.textContent='…';ps.append(h,det)}
    else{ps.textContent='';const e=document.createElement('div');e.className='fdempty';const b=document.createElement('b');b.textContent=t('Person antippen','Tap a person');
      const sp=document.createElement('span');sp.textContent=t('Hier stehen dann Zugang, Geräte, Funktionen, Rechte mit dem Platz für Uploads und Löschen.','Access, devices, functions, rights with the space for uploads, and delete then show here.');e.append(b,sp);ps.appendChild(e)}}
  $('dadd').disabled=!d.all;
  const mid='style="vertical-align:middle"';
  $('devlist').innerHTML=d.devices.map(x=>{const k=dkind(x);return `<tr><td ${mid}><div class="prow">${pDevIcon(x)}<div class="pmid"><div class="pname"><b>${esc(x.name)}</b>${x.room?` <span class="pill ok">${t('hört zu','listening')}</span>`:''}</div><div class="pmeta">${k?esc(k)+' · ':''}${t('zuletzt','last used')}: ${x.last?esc(pwhen(x.last.t))+' · '+esc(x.last.ip||''):t('noch nie','never')}</div></div></div></td>
    <td style="vertical-align:middle;width:150px">${k?`<span title="${esc(t('Fest bei diesem Profil. Zum Wechseln dort entfernen und unter dem anderen Profil neu einrichten.','Fixed to this profile. To change it, remove it there and set it up again under the other profile.'))}">${esc(name(x.user))} <small class="mut">🔒 ${t('fest','fixed')}</small></span>`
      :`<select data-dmove="${esc(x.id)}" aria-label="${esc(t('Profil','Profile'))}" style="width:100%">${popts(x.user)}</select>`}</td>
    <td style="text-align:right;vertical-align:middle"><button class="b" type="button" data-ddel="${esc(x.id)}" data-dname="${esc(x.name)}" data-dspk="${x.speaker?'1':''}">${t('Löschen','Delete')}</button></td></tr>`}).join('')
    ||`<tr><td class="mut">${PL.q||PL.show?t('Keine Geräte bei den gezeigten Profilen.','No devices with the profiles shown.'):t('Noch keine.','None yet.')}</td></tr>`;
  $('devlist').querySelectorAll('[data-dmove]').forEach(i=>i.onchange=()=>devUser(i.dataset.dmove,i.value));
  $('devlist').querySelectorAll('[data-ddel]').forEach(b=>b.onclick=()=>delDev(b.dataset.ddel,b.dataset.dname,b.dataset.dspk));
  if(PL.open&&$('pdetail'))profDetail(PL.open,keep);else keep()}
// Personen als Liste + Detail (plaene/einstellungen-neu.md, Paket 5): from about 740 px card width the details sit beside
// the list; switching between wide and narrow draws the list again
function pSide(){const c=document.querySelector('#prof .pcard');if(!c)return false;const w=c.getBoundingClientRect().width;
  const on=w>=740&&!document.body.classList.contains('appview');c.classList.toggle('split',on);return on}
{const c=document.querySelector('#prof .pcard');let was=null;if(c)new ResizeObserver(()=>{const w=c.getBoundingClientRect().width;if(!w)return;
  const on=w>=740&&!document.body.classList.contains('appview');if(was!==null&&on!==was&&$('prof').classList.contains('on'))loadProf();was=on}).observe(c)}
// One profile in detail (plan „Vereinheitlichen“ Phase 5): Zugang (PIN, zweiter Schritt, Rolle, Browser), Rufname,
// Geräte, Funktionen „n von m an“ with the functions blocked for this profile (tap lifts the block), Rechte (Aufträge, Spark-Update aus der App, Platz für
// Uploads) and Löschen. Everything that used to sit on other pages per profile is here; the pages stay for the overview.
const PROLE=()=>typeof ROLE_NAME!=='undefined'?ROLE_NAME:{admin:t('Admin','Admin'),manager:t('Verwalter','Manager')};
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
    ${setRow(esc(t('Nur Krisenspiel','Crisis game only')),esc(t('Das Profil sieht nach der Anmeldung nur das Krisenspiel: kein Assistent, kein Werkzeug, kein Gerät. Nie mit Admin-Rolle.','After signing in the profile sees only the crisis game: no assistant, no tool, no device. Never with an admin role.')),`<label class="chk"><input type="checkbox" id="pspiel"${u.nur_spiel?' checked':''}${u.role?' disabled':''}> ${t('an','on')}</label>`)}
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
  $('pspiel').onchange=async()=>{try{await api('/api/admin/profiles/'+encodeURIComponent(id)+'/nurspiel',jpost('PUT',{on:$('pspiel').checked}));
    ok($('pspiel').checked?t('Nur noch Krisenspiel.','Crisis game only now.'):t('Wieder ein normales Profil.','A normal profile again.'));loadProf()}catch(e){perr('pmsg',e)}again()};
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
  if($('pvor'))$('pvor').onchange=async()=>{try{await api('/api/admin/vorrang/'+encodeURIComponent(id),jpost('PUT',{level:$('pvor').value}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e);again()}};
  $('pagent').onchange=async()=>{try{await api('/api/admin/agent/levels/'+encodeURIComponent(id),jpost('PUT',{level:$('pagent').value}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e);again()}};
  const upd=async()=>{try{await api('/api/admin/iphone-update/'+encodeURIComponent(id),jpost('PUT',{notify:$('pupdn').checked,start:$('pupds').checked}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e)}again()};
  $('pupdn').onchange=upd;$('pupds').onchange=upd;
  $('pquotasave').onclick=async()=>{const v=$('pquota').value.trim();
    try{await api('/api/admin/wissen/quota',jpost('POST',{owner:id,mb:v===''?null:Number(v)}));ok(t('Gespeichert.','Saved.'))}catch(e){perr('pmsg',e)}again()}}
const jpost=(m,b)=>({method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
$('padd').onclick=async()=>{try{await api('/api/admin/profiles',jpost('POST',{name:$('pname').value,pin:$('ppin').value,nur_spiel:$('pspielnew').checked}));$('pspielnew').checked=false;
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
