// Einstellungen → Sicherheit starts with "Sicherheit auf einen Blick" (V01.0.262): fixed checks from
// /api/admin/security-glance as a traffic light (red = open, yellow = recommended, green = fine), each with a
// button to the place where it is changed. Red items also show under Zustand → "Braucht dich".
let SECNEED=[],SECAT=0;
const SECTXT={
  admin_mfa:x=>x.lvl==='ok'?[t('Zweiter Anmeldeschritt für den Admin','Second sign-in step for the admin'),t('An.','On.')]
    :[t('Zweiter Anmeldeschritt für den Admin ist aus','Second sign-in step for the admin is off'),t('Ohne ihn gehen Mit-Admins, die Kiwix-Adresse und das Update vom iPhone nicht, und ein gestohlenes Passwort reicht.','Without it co-admins, the Kiwix address and the update from the iPhone do not work, and a stolen password is enough.'),t('Einrichten','Set up'),'mfa'],
  backup:x=>x.days==null?[t('Noch keine Sicherung','No backup yet'),t('Unter Update und Sicherung eine Sicherung anlegen.','Create a backup under Update and backup.'),t('Öffnen','Open'),'upd']
    :x.lvl==='bad'?[t('Letzte Sicherung ist alt','Last backup is old'),t(`Vor ${x.days} Tagen.`,`${x.days} days ago.`),t('Öffnen','Open'),'upd']
    :[t('Sicherung nur auf dem Spark','Backup only on the Spark'),t(`${x.count} Sicherungen, die letzte vor ${x.days} Tagen. Stirbt die SSD, sind sie mit weg: eine Kopie herunterladen oder nach außen legen.`,`${x.count} backups, the last ${x.days} days ago. If the SSD dies they are gone too: download a copy or store one elsewhere.`),t('Öffnen','Open'),'upd'],
  short_pins:x=>x.lvl==='ok'?[t('PINs der Profile','Profile PINs'),t('Keine kurze PIN bekannt (gezählt ab der nächsten Anmeldung).','No short PIN known (counted from the next sign-in).')]
    :[t(`${x.count} Profil(e) mit PIN unter 6 Zeichen`,`${x.count} profile(s) with a PIN under 6 characters`),x.names.join(', ')+'. '+t('Für Profile mit Mail, Dokumenten oder Rolle besser 6 oder mehr.','Better 6 or more for profiles with mail, documents or a role.'),t('Profile','Profiles'),'prof'],
  role_mfa:x=>[t('Admin-Rechte ohne zweiten Schritt','Admin rights without second step'),x.names.join(', ')+'. '+t('Der Admin-Modus geht erst, wenn das Profil ihn einrichtet.','Admin mode only works once the profile sets it up.'),t('Rollen','Roles'),'sec'],
  https:x=>x.lvl==='ok'?[t('Verbindung','Connection'),t('Diese Seite läuft über https.','This page runs over https.')]
    :[t('Diese Seite läuft über http','This page runs over http'),t('Passwort und Cookies gehen unverschlüsselt durchs Netz. Besser über den Reverse Proxy oder Port 31443 öffnen.','Password and cookies travel unencrypted. Better open it via the reverse proxy or port 31443.')],
  public:x=>x.lvl==='ok'?[t('Assistent nur mit Anmeldung','Assistant only with sign-in'),t('Nur angemeldete Personen und Geräte mit Schlüssel, keine Gäste.','Only signed-in profiles and devices with a key, no guests.')]
    :[t('Assistent ohne Passwort ist an','Assistant without password is on'),t('Jeder im Netz kann als Gast fragen (ohne persönliche Daten).','Anyone on the network can ask as a guest (no personal data).'),t('Ansehen','View'),'sec'],
  allow_lan:x=>x.lvl==='ok'?[t('Heimnetz-Adressen','Home network addresses'),t('Aus: Profile erreichen nur Server im Internet.','Off: profiles reach only servers on the internet.')]
    :[t('Heimnetz-Adressen sind erlaubt','Home network addresses are allowed'),t('Profile dürfen Server im Heimnetz abfragen. Nur anlassen, wenn ein NAS oder Ähnliches gebraucht wird.','Profiles may query servers in the home network. Keep it only if a NAS or similar is needed.'),t('Ansehen','View'),'sec'],
  session_days:x=>[t('Anmeldung im Browser','Sign-in in the browser'),t(`Endet nach ${x.days} Tagen ohne Nutzung.`,`Ends after ${x.days} days without use.`)+(x.lvl==='ok'?'':' '+t('30 Tage oder weniger empfohlen.','30 days or fewer recommended.')),x.lvl==='ok'?'':t('Ändern','Change'),'sec'],
  headers:()=>[t('Schutz der Seite im Browser','Browser protection of the page'),t('Keine fremde Seite darf das Panel einbetten, Mikrofon und Kamera nur für das Panel.','No other page may embed the panel, microphone and camera only for the panel.')],
  updates:()=>[t('Nur geprüfte Updates','Only tested updates'),t('Der Spark installiert nur Versionen mit grünen Tests.','The Spark installs only versions with green tests.')],
  vault:()=>[t('Geheimnisse im Tresor','Secrets in the vault'),t('Tokens und Passwörter verschlüsselt, nie im Log, nie gesprochen.','Tokens and passwords encrypted, never in the log, never spoken.')],
  outside:()=>[t('Fremder Text ist nur Daten','Outside text is only data'),t('Web, Mail, Dokumente und Kiwix schalten nichts.','Web, mail, documents and Kiwix switch nothing.')]};
const secGo=go=>{if(go==='mfa'){goCfg('sec');const m=$('admmfa');if(m)setTimeout(()=>m.scrollIntoView({behavior:'smooth',block:'center'}),150)}
  else if(go==='upd')goCfg('upd');else if(go==='prof')goSec('prof');else goCfg('sec')};
async function loadSecGlance(force){if(!ADMIN||document.body.classList.contains('mgr'))return;if(!force&&Date.now()-SECAT<300e3)return;SECAT=Date.now();
  let d;try{d=await (await api('/api/admin/security-glance')).json()}catch{return}
  SECNEED=d.items.filter(x=>x.lvl==='bad').map(x=>{const [ti,,btn,go]=SECTXT[x.key]?SECTXT[x.key](x):[x.key];return {lvl:'bad',text:ti+'.',btn:btn||t('Öffnen','Open'),go:'sec:'+(go||'sec')}});
  if(typeof zustand==='function')zustand();
  const box=$('secglance');if(!box)return;box.textContent='';
  const head=document.createElement('div');head.className='sgsum';const n=k=>d.items.filter(x=>x.lvl===k).length;
  head.textContent=n('bad')?t(`${n('bad')} offen, ${n('warn')} empfohlen`,`${n('bad')} open, ${n('warn')} recommended`):n('warn')?t(`Nichts offen, ${n('warn')} empfohlen`,`Nothing open, ${n('warn')} recommended`):t('Alles grün.','All green.');
  box.appendChild(head);
  for(const x of d.items){const f=SECTXT[x.key];if(!f)continue;const [ti,tx,btn,go]=f(x);
    const r=document.createElement('div');r.className='sgrow';const dot=document.createElement('i');dot.className='amp '+x.lvl;
    const l=document.createElement('div');l.className='lbl';const b=document.createElement('b');b.textContent=ti;const s=document.createElement('span');s.textContent=tx||'';l.append(b,s);r.append(dot,l);
    if(btn&&go){const k=document.createElement('button');k.type='button';k.className='b';k.textContent=btn;k.onclick=()=>secGo(go);r.appendChild(k)}
    box.appendChild(r)}}
window.loadSecGlance=loadSecGlance;
