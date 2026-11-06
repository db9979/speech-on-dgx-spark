'use strict';
// Fernzugang → sshTermy als Jump-Host (fernsshtermy.py): sshTermy on a computer reaches the paired systems through the
// panel, SSH end to end, the panel passes bytes only. The box below the systems: „Koppeln (Code)“ (a fresh code, the
// browser only) shows the setup line with „Kopieren“; the paired sshTermy keys with unlocked or locked, their open
// channels, „Trennen“ and „Entfernen“ (a fresh code). On the system's card the part „Schlüssel für sshTermy“: what the
// server reported (fingerprint, comment, tunnels) and the command for root there; the panel never adds a key.
// Every name and fingerprint goes through textContent.
const ST={zeile:null};
const ST_BEFEHL="sudo spark-anker schluessel dazu 'ssh-ed25519 AAAA… sshtermy@laptop'";
function stBox(){const box=$('fzsshtermy'),d=FZ.d;if(!box)return;const v=d&&!d.gesperrt&&d.sshtermy;box.hidden=!v;box.textContent='';if(!v)return;
  const kopf=fzEl('div','stkopf'),tx=fzEl('div','sttext');
  tx.append(fzEl('h3','',t('sshTermy als Jump-Host','sshTermy as jump host')),
    fzEl('div','fh',t('sshTermy auf deinem Rechner erreicht die Server über den Spark. SSH läuft Ende-zu-Ende, der Spark reicht nur Bytes durch.','sshTermy on your computer reaches the servers through the Spark. SSH runs end to end, the Spark only passes bytes on.')));
  const neu=fzBtn(t('Koppeln (Code)','Pair (code)'),'p',stKoppeln);neu.id='stkoppeln';
  const gs=v.geraete||[];if(gs.length>=v.max){neu.disabled=true;neu.title=t(`Schon ${v.max} gekoppelt: erst eins entfernen.`,`Already ${v.max} paired: remove one first.`)}
  if(!d.browser){neu.disabled=true;neu.title=t('Koppeln nur im Browser.','Pairing only in the browser.')}
  if(window.codeLock)codeLock(neu,'protect');
  kopf.append(tx,neu);box.appendChild(kopf);
  if(ST.zeile&&ST.zeile.bis>Date.now()){const z=fzEl('div','stzeile');z.appendChild(fzEl('code','',ST.zeile.setup));box.appendChild(z);
    const h=fzEl('div','fh'),k=fzBtn(t('Kopieren','Copy'),'fzlink',()=>copyString(ST.zeile.setup,k));
    h.append(document.createTextNode(t(`In sshTermy mit Strg+Leertaste die Befehle öffnen und bei „Vermittler koppeln / verwalten“ einfügen. Gilt ${Math.round(v.code_s/60)} Minuten und einmal. `,
      `In sshTermy open the commands with Ctrl+Space and paste at "Vermittler koppeln / verwalten". Works for ${Math.round(v.code_s/60)} minutes and once. `)),k);box.appendChild(h)}
  box.appendChild(fzEl('div','fzgrp',t('Gekoppelte Geräte','Paired devices')));
  if(!gs.length)box.appendChild(fzEl('div','mut',t('Noch kein sshTermy gekoppelt.','No sshTermy paired yet.')));
  for(const x of gs)box.appendChild(stZeile(x))}
function stZeile(x){const r=fzEl('div','strow'),tx=fzEl('div','sttext'),nm=fzEl('div','stname'),offen=x.entsperrt_bis&&x.entsperrt_bis*1000>Date.now();
  nm.append(fzEl('b','','sshTermy · '+x.name));if(x.profil)nm.appendChild(fzEl('span','pill',t('Admin ','Admin ')+x.profil));
  const teile=[offen?t('entsperrt noch ','unlocked for ')+Math.max(1,Math.round((x.entsperrt_bis*1000-Date.now())/60000))+' min':t('gesperrt','locked')];
  if(x.kanaele)teile.push(x.kanaele===1?t('1 Kanal offen','1 channel open'):t(`${x.kanaele} Kanäle offen`,`${x.kanaele} channels open`));
  teile.push(x.zuletzt?t('zuletzt ','last ')+fzZeit(x.zuletzt):t('seit ','since ')+fzZeit(x.seit));if(!x.admin)teile.push(t('Profil ist kein Admin mehr','profile is no admin any more'));
  tx.append(nm,fzEl('small','',teile.join(' · ')));r.append(fzEl('span','fzdot '+(x.kanaele?'bad':offen?'ok':'')),tx);
  if(x.kanaele)r.appendChild(fzBtn(t('Trennen','Disconnect'),'',async()=>{try{await api(`/api/admin/fernzugang/sshtermy/${x.id}/trennen`,{method:'POST'});fzLoad()}catch(e){fzFehler(e)}}));
  const rm=fzBtn(t('Entfernen','Remove'),'danger',async()=>{if(!confirm(t(`„sshTermy · ${x.name}“ entfernen? Sein Schlüssel gilt sofort nicht mehr, offene Kanäle enden. Danach fragt der Spark nach Code oder Passkey.`,`Remove "sshTermy · ${x.name}"? Its key stops at once, open channels end. Then the Spark asks for a code or passkey.`)))return;
    try{await api(`/api/admin/fernzugang/sshtermy/${x.id}`,{method:'DELETE'});fzMsg(t('Entfernt.','Removed.'));fzLoad()}catch(e){fzFehler(e)}});
  if(window.codeLock)codeLock(rm,'protect');r.appendChild(rm);return r}
async function stKoppeln(){try{const r=await api('/api/admin/fernzugang/sshtermy/koppeln',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin:location.origin})});
    const j=await r.json();ST.zeile={setup:j.setup,bis:Date.now()+j.gilt_s*1000};stBox();
    setTimeout(()=>{if(ST.zeile&&ST.zeile.bis<=Date.now()){ST.zeile=null;stBox()}},j.gilt_s*1000+500)}catch(e){fzFehler(e)}}
// the system's card: the keys of sshTermy the server reported (never the key itself), and the command for root there
function stSchluessel(g){const w=fzEl('div','stschl');w.appendChild(fzEl('div','fzgrp',t('Schlüssel für sshTermy','Keys for sshTermy')));
  const k=g.schluessel;
  if(k===null||k===undefined)w.appendChild(fzEl('div','mut',t('Der Server hat noch nichts gemeldet (Anker ab 1.11.0).','The server has reported nothing yet (anchor 1.11.0 or newer).')));
  else if(!k.length)w.appendChild(fzEl('div','mut',t('Noch kein Schlüssel für sshTermy auf diesem Server.','No key for sshTermy on this server yet.')));
  for(const x of k||[]){const r=fzEl('div','strow');const tx=fzEl('div','sttext');tx.append(fzEl('span','',x.typ+' '),fzEl('code','',fzKurz(x.fp)),fzEl('span','',' '+(x.kommentar||'')));
    r.append(tx,fzEl('span','pill',x.weiterleiten?t('mit Tunnel','with tunnels'):t('ohne Tunnel','without tunnels')));w.appendChild(r)}
  const h=fzEl('div','fh'),c=fzBtn(t('Kopieren','Copy'),'fzlink',()=>copyString(ST_BEFEHL,c));
  h.append(document.createTextNode(t('Dazu nur am Server als root: ','Added only on the server as root: ')),fzEl('code','',ST_BEFEHL),
    document.createTextNode(t(' (mit --weiterleiten auch Tunnel). Der Spark selbst trägt keine Schlüssel ein. ',' (with --weiterleiten also tunnels). The Spark itself never adds a key. ')),c);
  w.appendChild(h);return w}
