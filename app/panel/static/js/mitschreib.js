// Mitschreib-Link (mitschreiblink.py, Listen Stufe 4): kept apart from the page Listen (listen.js) so the page can
// change its look without touching it, and the shared dialog (geteilt.js) can take the part over later.
// - mitLinkHtml(l) / mitLinkBind(box,l): the part „Link für Leute ohne Profil“ in the list's „Teilen …“ window
// - mitHash(): #liste=<code>, the visitor's small page (put something on, with „sehen“ also the open entries)
const MIT={lid:'',links:null,made:null,err:''};
const mitDays=n=>n===7?t('7 Tage','7 days'):n===30?t('30 Tage','30 days'):t('1 Jahr','1 year');
const mitDate=s=>new Date(s*1000).toLocaleDateString();
function mitLinkHtml(l){if(MIT.lid!==l.id){MIT.lid=l.id;MIT.links=null;MIT.made=null;MIT.err=''}
  const rows=MIT.links===null?`<div class="fh">${esc(t('Lädt …','Loading …'))}</div>`
    :MIT.links.map(x=>`<div class="setrow"><div class="lbl"><b>${esc(t('Link bis ','Link until ')+mitDate(x.until))}</b><span>${esc(x.see?t('eintragen und ansehen','put on and look'):t('nur eintragen','put on only'))}</span></div>`+
      `<button class="b" type="button" data-mitoff="${esc(x.id)}">${esc(t('Widerrufen','Revoke'))}</button></div>`).join('');
  const made=MIT.made?`<div class="mitmade"><div class="jqr">${MIT.made.qr||''}</div><div class="sp"><input readonly value="${esc(MIT.made.link)}" aria-label="${esc(t('Der Link','The link'))}" data-k="mitlink">`+
    `<div class="row"><button class="b" type="button" data-k="mitcopy">${esc(t('Kopieren','Copy'))}</button></div>`+
    `<div class="fh">${esc(t('Nur jetzt sichtbar: weitergeben oder den QR-Code zeigen.','Visible only now: pass it on or show the QR code.'))}</div></div></div>`:'';
  return `<div class="mitlinks"><b>${esc(t('Link für Leute ohne Profil','Link for people without a profile'))}</b>`+rows+made+
    `<div class="row"><select data-k="mitdays" aria-label="${esc(t('Gültig für','Valid for'))}">${[7,30,365].map(n=>`<option value="${n}"${n===30?' selected':''}>${esc(mitDays(n))}</option>`).join('')}</select>`+
    `<label class="lstnote"><input type="checkbox" data-k="mitsee"> ${esc(t('darf die Liste sehen','may see the list'))}</label>`+
    `<button class="b" type="button" data-k="mitmake">${esc(t('Link erstellen','Make link'))}</button></div>`+
    (MIT.err?`<div class="fh err">${esc(MIT.err)}</div>`:'')+
    `<div class="fh">${esc(t('Wer den Link hat, setzt nur etwas auf diese Liste: kein Abhaken, kein Löschen, kein Assistent.','Whoever has the link only puts things on this list: no ticking off, no deleting, no assistant.'))}</div></div>`}
async function mitLinkBind(box,l){const path='/api/profile/listen/'+encodeURIComponent(l.id)+'/links';
  const redraw=()=>{const old=box.querySelector('.mitlinks');if(!old)return;const tmp=document.createElement('div');tmp.innerHTML=mitLinkHtml(l);old.replaceWith(tmp.firstChild);mitLinkBind(box,l)};
  if(MIT.links===null){const {r,d}=await apiTry(path);MIT.links=r.ok?d.links:[];if(!r.ok)MIT.err=errSay(r.status,d.detail,'');redraw();return}
  box.querySelectorAll('[data-mitoff]').forEach(b=>b.onclick=async()=>{const {r,d}=await apiTry(path+'/'+encodeURIComponent(b.dataset.mitoff),{method:'DELETE'});
    if(r.ok){MIT.links=d.links;MIT.made=null;MIT.err=''}else MIT.err=errSay(r.status,d.detail,'');redraw()});
  const mk=box.querySelector('[data-k=mitmake]');if(mk)mk.onclick=async()=>{mk.disabled=true;
    const {r,d}=await apiTry(path,xjson('POST',{days:+box.querySelector('[data-k=mitdays]').value,see:box.querySelector('[data-k=mitsee]').checked,base:location.origin}));
    if(r.ok){MIT.links=d.links;MIT.made={link:d.link,qr:d.qr};MIT.err=''}else MIT.err=errSay(r.status,d.detail,'');redraw()};
  const cp=box.querySelector('[data-k=mitcopy]');if(cp)cp.onclick=async()=>{const f=box.querySelector('[data-k=mitlink]');
    try{await navigator.clipboard.writeText(f.value);cp.textContent=t('Kopiert','Copied')}catch{f.select()}}}
// ---------------------------------------------------------------- the visitor
// the public routes answer with their own codes; api() would open the login on a 401
async function mitPub(p,b){const r=await /*raw: public route, api() would open the login on a 401*/fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
  let d={};try{d=await r.json()}catch{}
  if(!r.ok){const e=new Error(typeof d.detail==='string'?d.detail:'');e.status=r.status;throw e}return d}
const mitErr=e=>e.status===404?t('Mitschreib-Links sind auf diesem Spark gerade aus.','Write links are switched off on this Spark right now.')
  :e.status===429?t('Zu viele Versuche. Bitte später noch einmal.','Too many attempts. Please try again later.')
  :e.status===400?t('Der Link passt nicht oder ist abgelaufen.','The link does not fit or has expired.')
  :t('Das hat nicht geklappt.','That did not work.');
function mitHash(){const m=/^#liste=([A-Za-z0-9_-]{24})$/.exec(location.hash);if(!m)return false;
  history.replaceState(null,'',location.pathname+location.search);mitVisit(m[1]);return true}
function mitModal(){let m=$('mitmodal');if(!m){m=document.createElement('div');m.id='mitmodal';m.className='modal';
  m.innerHTML='<div class="card modalcard joincard" id="mitcard"></div>';document.body.appendChild(m)}m.style.display='grid';return $('mitcard')}
async function mitVisit(code){const box=mitModal(),head=`<div class="row joinbrand"><span class="logo"></span><b>Spark</b></div>`;
  box.innerHTML=head+`<div class="mut">${esc(t('Link wird geprüft …','Checking the link …'))}</div>`;
  let d;try{d=await mitPub('/api/liste/check',{code})}catch(e){box.innerHTML=head+`<div class="err">${esc(mitErr(e))}</div>`;return}
  let name='';try{name=localStorage.getItem('mitname')||''}catch{}
  const draw=(msg,ok)=>{const lname=L==='en'?d.name_en:d.name;
    box.innerHTML=head+`<h2>${esc(d.icon+' '+lname)}</h2><div class="intro">${esc(t('Setz etwas auf diese Liste. Mehrere mit Komma, z. B. „2 Milch, Brot“.','Put something on this list. Several with commas, e.g. "2 milk, bread".'))}</div>`+
      `<label for="mittext">${esc(t('Eintrag','Entry'))}</label><input id="mittext" maxlength="400" autocomplete="off" enterkeyhint="done">`+
      `<label for="mitname">${esc(t('Dein Name (freiwillig)','Your name (optional)'))}</label><input id="mitname" maxlength="30" autocomplete="nickname" value="${esc(name)}">`+
      `<div class="row joinfoot"><span class="mut sm">${esc(t('gültig bis ','valid until ')+mitDate(d.until))}</span><button class="b p" type="button" id="mitgo">${esc(t('Eintragen','Put on'))}</button></div>`+
      `<div id="mitmsg" class="${ok?'fh':'err'}">${esc(msg||'')}</div>`+
      (d.see?`<h3>${esc(t('Schon auf der Liste','Already on the list'))}</h3>`+((d.items||[]).length?`<ul class="mititems">${d.items.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:`<div class="mut">${esc(t('Noch nichts.','Nothing yet.'))}</div>`):'');
    const go=async()=>{const text=$('mittext').value.trim();if(!text)return;name=$('mitname').value.trim();try{localStorage.setItem('mitname',name)}catch{}
      $('mitgo').disabled=true;
      try{d=Object.assign(d,await mitPub('/api/liste/add',{code,text,name}));draw(t('Danke, steht drauf.','Thanks, it is on the list.'),true)}
      catch(e){draw(mitErr(e),false)}
      $('mittext').focus()};
    $('mitgo').onclick=go;$('mittext').onkeydown=e=>{if(e.key==='Enter')go()};$('mittext').focus()};
  draw('',true)}
