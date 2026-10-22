// Krisenspiel gemeinsam (krisenteam.py, Paket 11): the page of a seat, #krise=<code>. A player with or without a
// profile sees the same dashboard as the owner (values, systems, chronicle, the team) and takes the moves of its role;
// the page asks every poll seconds for the situation. Kept apart from the owner's page (krisenspiel.js) and reuses
// only its small helpers (ksP, ksBar, ksEur, KSSTAT, KSART). Everything shown is text (esc), nothing is a command.
const KG={code:'',d:null,busy:false,err:'',at:0,timer:0};
async function kgPub(p,b){const r=await /*raw: public route, api() would open the login on a 401*/fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  let d={};try{d=await r.json()}catch{}
  if(!r.ok){const e=new Error(typeof d.detail==='string'?d.detail:'');e.status=r.status;throw e}return d}
const kgErr=e=>e.status===404?t('Gemeinsam spielen ist auf diesem Spark gerade aus.','Playing together is switched off on this Spark right now.')
  :e.status===429?t('Zu viele Versuche. Bitte später noch einmal.','Too many attempts. Please try again later.')
  :e.status===400?t('Der Link passt nicht mehr: abgelaufen, entfernt oder ein neues Spiel.','The link does not fit any more: expired, removed or a new game.')
  :e.status===409?t('Jemand war schneller; jetzt ist die Lage aktuell.','Someone was faster; the situation is current now.')
  :e.status===422?t('Dieser Zug geht gerade nicht oder gehört nicht zu deiner Rolle.','This move is not possible right now or not your role.')
  :t('Das hat nicht geklappt.','That did not work.');
function kgHash(){const m=/^#krise=([A-Za-z0-9_-]{32})$/.exec(location.hash);if(!m)return false;
  history.replaceState(null,'',location.pathname+location.search);KG.code=m[1];kgStart();return true}
function kgBox(){let m=$('kgmodal');if(!m){m=document.createElement('div');m.id='kgmodal';m.className='modal kgmodal';
  m.innerHTML='<div class="card modalcard kgcard" id="kgcard"></div>';document.body.appendChild(m)}m.style.display='grid';return $('kgcard')}
const KGHEAD=`<div class="row joinbrand"><span class="logo"></span><b>Spark</b></div>`;
async function kgStart(){const box=kgBox();let name='';try{name=localStorage.getItem('kgname')||''}catch{}
  box.innerHTML=KGHEAD+`<h2>${esc(t('IT-Krisenspiel gemeinsam','IT crisis game together'))}</h2><div class="intro">${esc(t('Du wurdest zu einem laufenden Spiel eingeladen. Alles ist simuliert; du nimmst nur die Züge deiner Rolle.','You were invited to a running game. Everything is simulated; you only take the moves of your role.'))}</div>`+
    `<label for="kgname">${esc(t('Dein Name im Spiel','Your name in the game'))}</label><input id="kgname" maxlength="30" autocomplete="nickname" value="${esc(name)}">`+
    `<div class="row joinfoot"><button class="b p" type="button" id="kggo">${esc(t('Mitspielen','Join'))}</button></div><div id="kgmsg" class="err"></div>`;
  const go=async()=>{name=$('kgname').value.trim();try{localStorage.setItem('kgname',name)}catch{}$('kggo').disabled=true;
    try{KG.d=await kgPub('/api/krise/lage',{code:KG.code,name});KG.at=Date.now();kgDraw();kgPoll()}
    catch(e){$('kgmsg').textContent=kgErr(e);$('kggo').disabled=false}};
  $('kggo').onclick=go;$('kgname').onkeydown=e=>{if(e.key==='Enter')go()};$('kgname').focus()}
function kgPoll(){clearInterval(KG.timer);KG.timer=setInterval(async()=>{const m=$('kgmodal');
  if(!KG.d||!m||m.style.display==='none'){clearInterval(KG.timer);return}
  if(KG.busy||document.visibilityState!=='visible'||Date.now()-KG.at<KG.d.poll*1000)return;
  try{const d=await kgPub('/api/krise/lage',{code:KG.code});const turn=KG.d.zug,team=JSON.stringify(KG.d.team);KG.d=d;KG.at=Date.now();KG.err='';
    if(d.zug!==turn||JSON.stringify(d.team)!==team||d.ende)kgDraw();else kgClock()}
  catch(e){KG.err=kgErr(e);KG.at=Date.now();kgDraw();if(e.status===400||e.status===404)clearInterval(KG.timer)}},1000)}
function kgLeft(g){const u=g.uhr;if(!u||g.ende)return g.m.zeit;
  const sec=u.rest+(u.pause?0:Math.min(u.seit+(Date.now()-KG.at)/1000,u.luecke));return Math.max(0,g.m.zeit-u.offen-Math.floor(sec/u.s))}
function kgClock(){const g=KG.d,el=document.querySelector('#kgcard .ks-time');if(!g||!el)return;const left=kgLeft(g);
  el.querySelector('b').textContent=`${left} min`;el.querySelector('em').style.width=Math.max(0,Math.min(100,Math.round(100*left/(g.m.zeit_start||1))))+'%'}
setInterval(()=>{if(KG.d&&KG.d.uhr)kgClock()},1000);
function kgDraw(){const g=KG.d,box=kgBox(),m=g.m,R=g.rollen,left=kgLeft(g);
  const team=`<div class="kg-team">${g.team.map(p=>`<span class="pill${p.online?' ok':''}">${esc(ksP(R[p.rolle]))}${p.gastgeber?esc(t(' · Gastgeber',' · host')):p.name?' · '+esc(p.name):''}${p.ich?esc(t(' (du)',' (you)')):''}</span>`).join(' ')}</div>`;
  const mets=`<div class="ks-mets">${ksBar(t('Zeit','Time'),left,m.zeit_start,`${left} min`,left*4<m.zeit_start,'ks-time')}
    ${ksBar(t('Stress','Stress'),m.stress,100,m.stress+' %',m.stress>=75)}${ksBar(t('Vertrauen','Trust'),m.vertrauen,100,m.vertrauen+' %',m.vertrauen<30)}
    ${ksBar(t('Moral','Morale'),m.moral,100,m.moral+' %',m.moral<30)}${ksBar(t('Budget','Budget'),m.budget,m.budget_start,ksEur(m.budget),m.budget*5<m.budget_start)}
    <div class="ks-met dmg"><span>${esc(t('Schaden','Damage'))}</span><b>${esc(ksEur(m.kosten))}</b></div></div>`;
  const assets=`<div class="ks-assets">${g.assets.map(a=>{const s=KSSTAT[a.status]||[a.status,a.status,''];
    return `<div class="ks-asset ${s[2]}"><b>${esc(a.name)}</b><small class="mut">${esc(ksP(a.typ))}</small><span class="pill ${s[2]}">${esc(t(s[0],s[1]))}</span><small>${esc(ksP(a.details))}</small></div>`}).join('')}</div>`;
  const acts=g.ende?`<div class="ks-end"><div class="ks-note ${KSNOTE[g.ende.note]||''}">${esc(g.ende.note)}</div><div><h4>${esc(t(`${g.ende.punkte} von 100 Punkten`,`${g.ende.punkte} of 100 points`))}</h4><ul class="facts small">${g.ende.gruende.map(x=>`<li><span>${esc(ksP(x))}</span></li>`).join('')}</ul></div></div>`
    :g.modus==='konsole'?`<div class="ks-only mut">${esc(t('Nur Konsole: Die Züge tippt die Leitung, du schaust zu.','Console only: the lead types the moves, you watch.'))}</div>`
    :`<h4>${esc(t('Deine Züge als ','Your moves as ')+ksP(R[g.rolle]))}</h4><div class="ks-acts">${g.aktionen.map(a=>`<button type="button" class="b ks-act" data-kgmove="${esc(a.id)}"${a.frei&&a.darf?'':' disabled'} title="${esc(!a.darf?t('Rolle ','Role ')+ksP(R[a.rolle]):a.frei?'':ksP(a.warum))}"><b>${esc(ksP(a.label))}</b><small>${esc(a.darf?'':ksP(R[a.rolle]))}</small></button>`).join('')}</div>`;
  const chron=g.chronik.slice().reverse().slice(0,12).map(c=>`<div class="ks-ev ${esc(c.art)}"><small class="mut">${esc(t(...(KSART[c.art]||[c.art,c.art])))} · ${esc(t('Minute ','minute '))}${c.min}${c.wer?' · '+esc(ksP(R[c.wer.rolle]||[c.wer.rolle,c.wer.rolle]))+(c.wer.name?' ('+esc(c.wer.name)+')':''):''}</small><p>${esc(ksP(c.text))}</p></div>`).join('');
  box.innerHTML=KGHEAD+`<div class="ks"><div class="ks-head"><div><h3>${esc(ksP(g.titel))}</h3><div class="mut">${esc(ksP(g.stufe))} · ${esc(t(`Zug ${g.zug} · Minute ${g.min}`,`Move ${g.zug} · minute ${g.min}`))}</div></div><button type="button" class="b" data-kgleave="1">${esc(t('Verlassen','Leave'))}</button></div>${team}${mets}
    <div class="ks-grid"><div>${assets}${acts}</div><div><h4>${esc(t('Chronik','Chronicle'))}</h4><div class="ks-chron" aria-live="polite">${chron}</div></div></div>
    <div class="ksmsg ${KG.err?'err':'mut'}" role="status">${esc(KG.err)}</div></div>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#kgcard [data-kgmove],#kgcard [data-kgleave]');if(!b)return;
  if(b.dataset.kgleave){clearInterval(KG.timer);KG.d=null;$('kgmodal').style.display='none';return}
  if(KG.busy)return;KG.busy=true;b.disabled=true;
  try{KG.d=await kgPub('/api/krise/zug',{code:KG.code,aktion:b.dataset.kgmove,zug:KG.d.zug});KG.err=''}
  catch(e){KG.err=kgErr(e);if(e.status===409)try{KG.d=await kgPub('/api/krise/lage',{code:KG.code})}catch{}}
  KG.busy=false;KG.at=Date.now();kgDraw()});
