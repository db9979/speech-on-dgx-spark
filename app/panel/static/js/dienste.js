// Zustand → Dienste (dienstwacht.py, admin): what the Dienst-Wächter looks at, whether it answers, since when it is
// gone, outages today and the last 7 days. Only names of services, fixed words and times (through esc); a tick
// takes a service off the list (not looked at, nobody hears of it), "Jetzt prüfen" looks at every service at once.
const SVCW={ok:t('läuft','running'),wobble:t('wackelt','wobbling'),down:t('antwortet nicht','not answering'),inet:t('wegen Internet weg','gone with the internet'),
  off:t('nicht geprüft','not looked at'),held:t('Notaus: nicht geprüft','kill switch: not looked at'),blocked:t('vom Wächter nicht erlaubt','not allowed by the Wächter'),new:t('noch nicht geprüft','not looked at yet')};
const SVCP={ok:'ok',wobble:'warn',down:'bad',inet:'bad',new:'warn'};
const svHM=s=>s?new Date(s*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}):'';
const svDay=s=>s?new Date(s*1000).toLocaleString([], {weekday:'short',hour:'2-digit',minute:'2-digit'}):'';
const svDur=(a,b)=>{const m=Math.max(1,Math.round((b-a)/60));return m<60?m+' min':Math.floor(m/60)+' h'+(m%60?' '+m%60+' min':'')};
function svRow(x){const name=t(x.name[0],x.name[1]);
  const what=x.st==='down'||x.st==='inet'?t(`seit ${svHM(x.since)}`,`since ${svHM(x.since)}`):x.checked?t(`geprüft ${svHM(x.checked)}`,`checked ${svHM(x.checked)}`):'';
  const parts=x.parts?' · '+t(`${x.parts.bad} von ${x.parts.n} Adressen weg`,`${x.parts.bad} of ${x.parts.n} addresses gone`):'';
  const today=x.today?' · '+t(`${x.today} Ausfälle heute`,`${x.today} outages today`):'';
  const box=x.set?`<label class="mut" style="margin-left:auto;white-space:nowrap"><input type="checkbox" data-svcw="${esc(x.id)}"${x.watched?' checked':''}> ${esc(t('prüfen','look at'))}</label>`:'';
  return `<div class="zrow"><span class="pill ${SVCP[x.watched&&x.set?x.st:'off']||''}">${esc(SVCW[x.watched&&x.set?x.st:'off']||x.st)}</span><span><b>${esc(name)}</b>${what?' · '+esc(what):''}${esc(parts)}${esc(today)}${
    x.set?'':' · '+esc(t('nicht eingerichtet','not set up'))}${x.st==='down'?`<div class="mut">${esc(x.what)}</div>`:''}</span>${box}</div>`}
async function zWatch(d){const box=$('zsvc');if(!box||document.hidden)return;
  if(!d){try{d=await (await api('/api/admin/svcwatch',{cache:'no-store'})).json()}catch{return}}
  box.hidden=!d.on;if(!d.on)return;
  const log=(d.log||[]).map(x=>`<li>${esc(t(x.name[0],x.name[1]))} · ${esc(svDay(x.a))}${x.b?' – '+esc(svHM(x.b))+' ('+esc(svDur(x.a,x.b))+')':' · '+esc(t('noch weg','still gone'))}</li>`).join('');
  $('zsvclist').innerHTML=(d.paused?`<div class="note">${esc(t('Pausiert: der Spark startet oder spielt ein Update ein.','Paused: the Spark is starting or updating.'))}</div>`:'')+
    (d.admins?'':`<div class="note">${esc(t('Noch bekommt kein Admin-Profil die Hinweise: unter Ich → Gespräch → Dienste „Hinweise bei Ausfällen“ einschalten.','No admin profile gets the notes yet: switch on "Notes on outages" under Me → Conversation → Services.'))}</div>`)+
    (d.services||[]).map(svRow).join('')+
    `<details class="adv" style="margin-top:8px"><summary>${esc(t('Ausfälle der letzten 7 Tage','Outages of the last 7 days'))} (${(d.log||[]).length})</summary>${log?`<ul class="bghist">${log}</ul>`:`<div class="mut">${esc(t('Keine.','None.'))}</div>`}</details>`}
if($('zsvclist'))$('zsvclist').addEventListener('change',async e=>{const c=e.target.closest('[data-svcw]');if(!c)return;
  try{zWatch(await (await api('/api/admin/svcwatch/'+encodeURIComponent(c.dataset.svcw),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({on:c.checked})})).json())}
  catch(err){$('zsvcmsg').textContent=err.message;c.checked=!c.checked}});
if($('zsvccheck'))$('zsvccheck').onclick=async()=>{const m=$('zsvcmsg');m.textContent=t('Prüfe …','Checking …');
  try{zWatch(await (await api('/api/admin/svcwatch/check',{method:'POST'})).json());m.textContent=t('Fertig.','Done.')}catch(e){m.textContent=e.message}};
