// Zustand → Geräte-Updates (geraeteupdate.py, admin): what the Spark keeps for each kind of device, which devices
// run which version, the night round of the speakers and the XiaoZhi note. Only version numbers, fixed words and
// device or profile names (through esc); "Jetzt suchen" asks every module at once, "Weiter verteilen" lets a
// stopped night round go on.
const DEVW=s=>{if(!s)return t('noch nie','never');const d=new Date(s*1000);return d.toLocaleString([], {weekday:'short',hour:'2-digit',minute:'2-digit'})};
function devKind(k){const n=t(k.name[0],k.name[1]),devs=k.devices||[];
  const ver=k.version?esc(k.version):esc(t('noch keine','none yet'));
  const pill=k.error?'bad':k.waiting?'warn':'ok';
  const cnt=k.kind==='android'?t(`${k.profiles||0} Profile mit der App`,`${k.profiles||0} profiles with the app`)
    :k.kind==='pebble'?t(`${devs.length} Uhren`,`${devs.length} watches`)
    :t(`${k.current} von ${devs.length} aktuell`,`${k.current} of ${devs.length} up to date`);
  const list=devs.map(d=>`<li>${esc(d.name)}${d.owner?' <span class="mut">('+esc(d.owner)+')</span>':''} · ${d.have?esc(d.have):esc(t('Version unbekannt','version unknown'))}${
    d.newer?' · <b>'+esc(d.auto===false?t('Update von Hand','update by hand'):t('Update ausstehend','update waiting'))+'</b>':d.newer===false?' · '+esc(t('aktuell','up to date')):''}${d.online===false?' · '+esc(t('nicht verbunden','not connected')):''}</li>`).join('');
  return `<div class="zrow"><span class="pill ${pill}">${ver}</span><span><b>${esc(n)}</b> · ${esc(cnt)} · ${esc(t('geprüft ','checked '))}${esc(DEVW(k.checked))}${k.error?' · '+esc(t('letzte Prüfung fehlgeschlagen','last check failed')):''}${list?`<ul class="bghist">${list}</ul>`:''}</span></div>`}
async function zDev(d){const box=$('zdev');if(!box||document.hidden)return;
  if(!d){try{const r=await fetch('/api/admin/devup',{cache:'no-store'});if(!r.ok)return;d=await r.json()}catch{return}}
  box.hidden=!d.on;if(!d.on)return;
  const N=d.night||{},U=d.upstream||{};
  let night='';
  if(N.on)night=`<div class="zrow"><span class="pill ${N.stopped?'bad':N.pending?'warn':'ok'}">${esc(N.at||'')}</span><span><b>${esc(t('Lautsprecher nachts','Speakers at night'))}</b> · ${
    esc(N.stopped?t(`angehalten: „${N.failed||'?'}“ kam nicht mit ${N.version} zurück`,`stopped: "${N.failed||'?'}" did not come back with ${N.version}`)
      :N.pending?t('ein Lautsprecher startet gerade neu','a speaker is restarting'):N.version?t(`${N.ok} mit ${N.version} neu gestartet`,`${N.ok} restarted with ${N.version}`):t('wartet auf die Nacht','waits for the night'))}</span></div>`;
  let up='';
  if(U.on)up=`<div class="zrow"><span class="pill ${U.version&&U.base&&U.version!==U.base?'warn':'ok'}">XiaoZhi</span><span>${
    esc(U.version?t(`neueste ${U.version}, unsere Firmware baut auf ${U.base||'?'}`,`newest ${U.version}, our firmware builds on ${U.base||'?'}`):t('noch nicht gefragt','not asked yet'))}${U.error?' · '+esc(t('letzte Frage fehlgeschlagen','last question failed')):''}</span></div>`;
  $('zdevlist').innerHTML=(d.kinds||[]).map(devKind).join('')+night+up||`<div class="mut">${esc(t('Noch keine Gerätefunktion an.','No device function on yet.'))}</div>`;
  $('zdevgo').style.display=N.on&&N.stopped?'':'none'}
if($('zdevcheck'))$('zdevcheck').onclick=async()=>{const m=$('zdevmsg');m.textContent=t('Suche …','Looking …');
  try{const d=await (await api('/api/admin/devup/check',{method:'POST'})).json();m.textContent=d.ok?t('Fertig.','Done.'):t('Nicht alles ging, siehe oben.','Not everything worked, see above.');zDev(d)}
  catch(e){m.textContent=e.message}};
if($('zdevgo'))$('zdevgo').onclick=async()=>{const m=$('zdevmsg');
  try{zDev(await (await api('/api/admin/devup/night/resume',{method:'POST'})).json());m.textContent=t('Geht im nächsten Nachtfenster weiter.','Goes on in the next night window.')}catch(e){m.textContent=e.message}};
