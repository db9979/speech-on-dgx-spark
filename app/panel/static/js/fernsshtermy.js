'use strict';
// Fernzugang → sshTermy als Jump-Host (fernsshtermy.py): sshTermy on a computer reaches the paired systems through the
// panel, SSH end to end, the panel passes bytes only. Its own tab beside „Systeme“ (Dominik 2026-11-06 „ok“, Bild
// aufraeumen/2-sshtermy.png): one sentence with „So geht's“ (a jump link to its switch and guide); „Koppeln (Code)“ in
// the head (a fresh code, the browser only) shows the setup line with „Kopieren“; the paired sshTermy devices with
// unlocked or locked, last seen, their open channels, „Trennen“ and „Entfernen“ (a fresh code); then one row per system:
// ✓ with the keys the server reported, or ○ with the command for root there. On the system's card the same row under
// „Einrichten“ (stEin). The panel never adds a key. Every name and fingerprint goes through textContent.
const ST={zeile:null};
const ST_BEFEHL="sudo spark-anker schluessel dazu 'ssh-ed25519 AAAA… sshtermy@laptop'";
const ST_INFO=['Statt „ssh-ed25519 AAAA… sshtermy@laptop“ den öffentlichen Schlüssel aus sshTermy einsetzen, am Server als root; mit --weiterleiten auch Tunnel. Der Spark selbst trägt keine Schlüssel ein.',
  'Put the public key from sshTermy in place of "ssh-ed25519 AAAA… sshtermy@laptop", on the server as root; with --weiterleiten also tunnels. The Spark itself never adds a key.'];
function stBox(){const box=$('stmain'),d=FZ.d;if(!box)return;const v=d&&!d.gesperrt&&d.sshtermy;if(!v||box.hidden){box.textContent='';return}box.textContent='';
  const gs=v.geraete||[],neu=$('stkoppeln');neu.disabled=false;
  if(gs.length>=v.max){neu.disabled=true;neu.title=t(`Schon ${v.max} gekoppelt: erst eins entfernen.`,`Already ${v.max} paired: remove one first.`)}
  else if(!d.browser){neu.disabled=true;neu.title=t('Koppeln nur im Browser.','Pairing only in the browser.')}
  else if(window.codeLock)codeLock(neu,'protect');
  const intro=fzEl('div','pintro stintro');
  intro.append(document.createTextNode(t('sshTermy auf deinem Rechner erreicht die Systeme über den Spark. SSH läuft Ende-zu-Ende, der Spark reicht nur Bytes durch. ','sshTermy on your computer reaches the systems through the Spark. SSH runs end to end, the Spark only passes bytes on. ')),
    wayEl(t("So geht's","How it works"),'Funktionen → Fernzugang zu Servern → sshTermy als Jump-Host'));
  box.appendChild(intro);
  if(ST.zeile&&ST.zeile.bis>Date.now()){const z=fzEl('div','stzeile');z.appendChild(fzEl('code','',ST.zeile.setup));box.appendChild(z);
    const h=fzEl('div','fh'),k=fzBtn(t('Kopieren','Copy'),'fzlink',()=>copyString(ST.zeile.setup,k));
    h.append(document.createTextNode(t(`In sshTermy mit Strg+Leertaste die Befehle öffnen und bei „Vermittler koppeln / verwalten“ einfügen. Gilt ${Math.round(v.code_s/60)} Minuten und einmal. `,
      `In sshTermy open the commands with Ctrl+Space and paste at "Vermittler koppeln / verwalten". Works for ${Math.round(v.code_s/60)} minutes and once. `)),k);box.appendChild(h)}
  box.appendChild(fzEl('div','fzgrp',t('Gekoppelte Geräte','Paired devices')));
  const l1=fzEl('div','stliste');box.appendChild(l1);
  if(!gs.length)l1.appendChild(fzEl('div','mut stleer',t('Noch kein sshTermy gekoppelt: „Koppeln (Code)“ oben.','No sshTermy paired yet: "Pair (code)" above.')));
  for(const x of gs)l1.appendChild(stZeile(x));
  box.appendChild(fzEl('div','fzgrp',t('Schlüssel für sshTermy auf den Systemen','Keys for sshTermy on the systems')));
  const l2=fzEl('div','stliste fzeinliste');box.appendChild(l2);const sys=(d.geraete||[]).filter(g=>g.stand!=='abbau');
  if(!sys.length)l2.appendChild(fzEl('div','mut stleer',t('Noch kein System gekoppelt.','No system paired yet.')));
  for(const g of sys)l2.appendChild(stEin(g,'',true))}
function stZeile(x){const r=fzEl('div','strow'),tx=fzEl('div','sttext'),offen=x.entsperrt_bis&&x.entsperrt_bis*1000>Date.now();
  tx.append(fzEl('b','','sshTermy · '+x.name));
  const teile=[];if(x.profil)teile.push(t('Admin ','Admin ')+x.profil);
  teile.push(offen?t('entsperrt noch ','unlocked for ')+Math.max(1,Math.round((x.entsperrt_bis*1000-Date.now())/60000))+' min':t('gesperrt','locked'));
  teile.push(x.zuletzt?t('zuletzt ','last ')+fzZeit(x.zuletzt):t('seit ','since ')+fzZeit(x.seit));
  teile.push(x.kanaele===1?t('1 Kanal','1 channel'):t(`${x.kanaele||0} Kanäle`,`${x.kanaele||0} channels`));
  if(!x.admin)teile.push(t('Profil ist kein Admin mehr','profile is no admin any more'));
  tx.appendChild(fzEl('small','',teile.join(' · ')));r.append(fzEl('span','fzdot '+(x.kanaele?'bad':offen?'ok':'')),tx);
  const tr=fzBtn(t('Trennen','Disconnect'),'',async()=>{try{await api(`/api/admin/fernzugang/sshtermy/${x.id}/trennen`,{method:'POST'});fzLoad()}catch(e){fzFehler(e)}});
  if(!x.kanaele){tr.disabled=true;tr.title=t('Kein Kanal offen.','No channel open.')}
  const rm=fzBtn(t('Entfernen','Remove'),'danger',async()=>{if(!confirm(t(`„sshTermy · ${x.name}“ entfernen? Sein Schlüssel gilt sofort nicht mehr, offene Kanäle enden. Danach fragt der Spark nach Code oder Passkey.`,`Remove "sshTermy · ${x.name}"? Its key stops at once, open channels end. Then the Spark asks for a code or passkey.`)))return;
    try{await api(`/api/admin/fernzugang/sshtermy/${x.id}`,{method:'DELETE'});fzMsg(t('Entfernt.','Removed.'));fzLoad()}catch(e){fzFehler(e)}});
  if(window.codeLock)codeLock(rm,'protect');const kn=fzEl('div','strechts');kn.append(tr,rm);r.appendChild(kn);return r}
async function stKoppeln(){try{const r=await api('/api/admin/fernzugang/sshtermy/koppeln',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin:location.origin})});
    const j=await r.json();ST.zeile={setup:j.setup,bis:Date.now()+j.gilt_s*1000};stBox();
    setTimeout(()=>{if(ST.zeile&&ST.zeile.bis<=Date.now()){ST.zeile=null;stBox()}},j.gilt_s*1000+500)}catch(e){fzFehler(e)}}
// one system's row for sshTermy (its tab, and „Einrichten“ on the card): the keys the server reported (never the key
// itself), or the command for root there; with keys „Weiteren Schlüssel …“ shows the command again. aus: why „In die
// Shell“ cannot work now; nurKopieren on the sshTermy tab (the system's name is the title there)
function stEin(g,aus,nurKopieren){const k=g.schluessel,o={k:'sshtermy',titel:nurKopieren?g.name:'sshTermy',aus,nurKopieren,info:t(...ST_INFO)};
  if(g.art==='windows')o.text=t('auf Windows noch nicht (der Anker kann es dort nicht)','not on Windows yet (the anchor cannot do it there)');
  else if(k===null||k===undefined)o.text=t('Der Server hat noch nichts gemeldet (Anker ab 1.11.0).','The server has reported nothing yet (anchor 1.11.0 or newer).');
  else if(!k.length)Object.assign(o,{text:t('noch kein Schlüssel','no key yet'),cmd:ST_BEFEHL});
  else{const teile=k.map(x=>[x.kommentar||x.typ,fzKurz(x.fp),x.weiterleiten?t('mit Tunnel','with tunnels'):t('ohne Tunnel','without tunnels')].join(' · '));
    o.ok=true;o.text=(k.length===1?t('1 Schlüssel: ','1 key: '):t(`${k.length} Schlüssel: `,`${k.length} keys: `))+teile.join('; ');
    const key=g.id+':stweiter',zeile=fzEl('div','fzeinmehr');zeile.appendChild(fzBefehl(ST_BEFEHL,g,nurKopieren,aus));zeile.hidden=!FZ.klapp.has(key);
    const b=fzBtn(t('Weiteren Schlüssel …','Another key …'),'',()=>fzKlapp(key,zeile,b));b.setAttribute('aria-expanded',String(!zeile.hidden));o.knoepfe=[b];o.unten=[zeile]}
  return fzEin(g,o)}
{const b=$('stkoppeln');if(b)b.onclick=stKoppeln}
