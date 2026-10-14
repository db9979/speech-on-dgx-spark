// Zustand der NAS (naszustand.py, plan synology-bauplan.md S6): Funktionen → Speicher und NAS → Zustand der NAS (the
// main admin enters host, SNMPv3 user and both passwords; they are never shown again, an empty field keeps them) and
// the card Zustand → Dienste "Zustand der NAS" with the newest values. Values from the NAS are text (esc).
const nzWhy=k=>{const w=(NZ&&NZ.why_words||{})[k];return w?t(w[0],w[1]):k};
const nzWord=w=>w?t(w,(NZ&&NZ.words||{})[w]||w):t('unbekannt','unknown');
let NZ=null;
function nzShow(d){NZ=d;if(!$('nzbox'))return;$('nzhost').value=d.host||'';$('nzuser').value=d.user||'';$('nzauth').value='';$('nzpriv').value='';
  $('nzauth').placeholder=d.has_auth?t('Passwort für die Anmeldung (gespeichert)','Sign-in password (saved)'):t('Passwort für die Anmeldung (SHA)','Sign-in password (SHA)');
  $('nzpriv').placeholder=d.has_priv?t('Passwort für die Verschlüsselung (gespeichert)','Privacy password (saved)'):t('Passwort für die Verschlüsselung (AES)','Privacy password (AES)');
  const l=d.last,m=$('nzmsg');
  m.textContent=!d.set?t('Noch nicht eingerichtet.','Not set up yet.'):!l?t('Noch nicht gelesen.','Not read yet.')
    :l.ok?t('Zuletzt gelesen: ','Last read: ')+new Date(l.t*1000).toLocaleString():t('Fehler am ','Failed on ')+new Date(l.t*1000).toLocaleString()+': '+nzWhy(l.why);
  m.classList.toggle('err',!!(l&&!l.ok));$('nznow').disabled=!d.set;$('nzforget').disabled=!d.set}
async function nzLoad(){if(!$('nzbox')||document.body.classList.contains('mgr'))return;
  try{nzShow(await (await api('/api/admin/naszustand')).json())}catch{}}
const nzErr=e=>{$('nzmsg').textContent=e.message;$('nzmsg').classList.add('err')};
const nzDone=d=>{nzShow(d);if(d.checked===false&&d.why){$('nzmsg').textContent=t('Gespeichert, aber gelesen hat es nicht: ','Saved, but reading failed: ')+nzWhy(d.why);$('nzmsg').classList.add('err')}zNasZustand()};
if($('nzsave'))$('nzsave').onclick=async()=>{$('nzmsg').classList.remove('err');$('nzmsg').textContent=t('Speichere und lese einmal …','Saving and reading once …');
  try{nzDone(await (await api('/api/admin/naszustand',xjson('PUT',{host:$('nzhost').value.trim(),user:$('nzuser').value.trim(),auth:$('nzauth').value,priv:$('nzpriv').value}))).json())}catch(e){nzErr(e)}};
if($('nznow'))$('nznow').onclick=async()=>{$('nzmsg').classList.remove('err');$('nzmsg').textContent=t('Lese die NAS …','Reading the NAS …');
  try{nzDone(await (await api('/api/admin/naszustand/now',{method:'POST'})).json())}catch(e){nzErr(e)}};
if($('nzforget'))$('nzforget').onclick=async()=>{if(!confirm(t('Adresse, Benutzer und Passwörter vergessen? Danach liest der Spark nichts mehr.','Forget address, user and passwords? Then the Spark reads nothing any more.')))return;
  try{nzShow(await (await api('/api/admin/naszustand',{method:'DELETE'})).json());zNasZustand()}catch(e){nzErr(e)}};
// Zustand → Dienste: one card, the values in rows (pill: fine, warning, problem)
function nzRows(d){const v=d.values,l=d.last||{};if(!v)return `<div class="mut">${esc(l.why?nzWhy(l.why):t('Noch keine Werte.','No values yet.'))}</div>`;
  const pill=(cls,w)=>`<span class="pill ${cls}">${esc(w)}</span>`;
  const head=`<div class="zrow">${l.ok?pill('ok',t('antwortet','answers')):pill('bad',nzWhy(l.why))}<span><b>${esc(v.model||'NAS')}</b>${v.dsm?' · '+esc(v.dsm):''}${v.update===true?' · '+esc(t('Update verfügbar','update ready')):''}
    <div class="mut">${esc(t('gelesen','read'))} ${esc(new Date(v.t*1000).toLocaleString())}${typeof v.temp==='number'?' · '+esc(t('System','system'))+' '+v.temp+' °C':''}${v.fans?' · '+esc(t('Lüfter','fans'))+' '+esc(nzWord(v.fans==='fehler'?'ausgefallen':'ok')):''}</div></span></div>`;
  const vols=(v.vols||[]).map(x=>`<div class="zrow">${pill(x.st==='ok'?(typeof x.pct==='number'&&x.pct>=d.full_pct?'warn':'ok'):x.st==='beschädigt'||x.st==='ausgefallen'?'bad':'warn',nzWord(x.st))}<span><b>${esc(x.name||t('Speicherbereich','Storage area')+' '+x.n)}</b>${typeof x.pct==='number'?`<div class="mut">${esc(t(`${x.pct} % belegt, ${x.free_gb} GB frei von ${x.total_gb} GB`,`${x.pct} % used, ${x.free_gb} GB free of ${x.total_gb} GB`))}</div>`:''}</span></div>`).join('');
  const disks=(v.disks||[]).map(x=>{const w=x.health&&x.health!=='ok'?x.health:x.st;return `<div class="zrow">${pill(w==='ok'?(typeof x.temp==='number'&&x.temp>=d.temp_max?'warn':'ok'):'bad',nzWord(w))}<span><b>${esc(t('Festplatte','Disk'))} ${x.n}</b>${typeof x.temp==='number'?' · '+x.temp+' °C':''}</span></div>`}).join('');
  const probs=(d.problems||[]).length?`<div class="note">${esc(d.problems.map(p=>t(p.de,p.en)).join(' · '))}</div>`:'';
  return probs+head+vols+disks}
async function zNasZustand(){const box=$('znaszustand');if(!box||document.hidden)return;
  const {r,d}=await apiTry('/api/admin/naszustand');if(!r.ok)return;
  box.hidden=!(d.on&&d.set);if(box.hidden)return;$('znaszustandlist').innerHTML=nzRows(d)}
