// Spark-Hilfe (hilfe.py, V01.0.326): the card under an answer with the switches the assistant suggests, and
// "Frag Spark", a small window on every page that knows the page it was opened on. The card never switches by
// itself: only the tap on "Übernehmen" sends the card's id to the panel, which applies exactly what it holds,
// with the same checks as the forms (and the admin's code for Spark switches). Everything shown is text (esc).
let HILFE=null;   // from /api/whoami: {suggest, page} for this profile, null = off
function hilfeStart(h){HILFE=h&&typeof h==='object'?h:null;hilfeFab()}
const HON=v=>v?t('an','on'):t('aus','off');
function hilfeShow(x){   // "Zeig mir wo": the switch on its page
  if(hilfeOpen.on)hilfeClose();
  if(x.kind==='admin'||(!x.kind&&x.sw&&ADMIN)){if(typeof goCfg!=='function')return;goCfg('feat');
    setTimeout(()=>{const el=$(x.kind==='admin'?'chat.'+x.switch:x.sw);if(!el)return;if(typeof featShow==='function')featShow(el);if(typeof sFlash==='function')sFlash(el.closest('.setrow')||el)},150);return}
  if(typeof openMe==='function')openMe(x.me||'setbox')}
function hilfeCard(c){const d=document.createElement('div');d.className='hcard';d.dataset.card=c.id||'';
  const rows=(c.items||[]).map(x=>`<div class="hrow"><span><b>${esc(x.name)}</b><small>${esc(x.where||'')}</small></span><span class="hval"><s>${esc(HON(x.old))}</s> <em>${esc(HON(x.new))}</em></span></div>`).join('');
  const nope=(c.blocked||[]).map((x,i)=>`<div class="hrow hno"><span><b>${esc(x.name)}</b><small>${esc(x.why||'')}</small></span>${x.sw||x.me?`<button type="button" class="mlink" data-hshow="${i}">${esc(t('Zeig mir wo','Show me where'))}</button>`:''}</div>`).join('');
  d.innerHTML=`<h4>${esc(c.title||t('Vorschlag','Suggestion'))}</h4>${rows}${nope}
    <div class="hwhy">${esc(c.admin?t('Mit Spark-Schaltern: Übernehmen fragt nach deinem Code, wenn der zweite Anmeldeschritt an ist. Steht danach im Admin-Protokoll.','With Spark switches: applying asks for your code when the second sign-in step is on. Listed in the admin log afterwards.')
      :t('Nur Schalter, die du selbst ändern darfst. Nichts ist geändert, bis du übernimmst.','Only switches you may change yourself. Nothing changes until you apply.'))}</div>
    <div class="row"><button type="button" class="b p" data-hdo="apply">${esc(t('Übernehmen','Apply'))}</button><button type="button" class="b" data-hdo="where">${esc(t('Zeig mir wo','Show me where'))}</button><button type="button" class="b" data-hdo="no">${esc(t('Nein danke','No thanks'))}</button></div>
    <div class="hmsg mut" role="status"></div>`;
  if(!c.id)d.querySelector('.row').remove();
  const msg=d.querySelector('.hmsg'),row=d.querySelector('.row');
  const send=async what=>{const r=await apiTry('/api/hilfe/karte/'+encodeURIComponent(c.id),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({do:what})});
    if(!r.r.ok){msg.textContent=String(r.d.detail||t('Ging nicht.','Did not work.')).slice(0,200);return null}return r.d.state};
  const after=()=>{if(typeof loadSettings==='function')loadSettings().catch(()=>{});if(c.admin&&ADMIN&&typeof loadCfg==='function')loadCfg().catch(()=>{});if(typeof whoSoon==='function')whoSoon()};
  d.addEventListener('click',async e=>{const s=e.target.closest('[data-hshow]');if(s){hilfeShow((c.blocked||[])[+s.dataset.hshow]||{});return}
    const b=e.target.closest('[data-hdo]');if(!b||b.disabled)return;const what=b.dataset.hdo;
    if(what==='where'){hilfeShow((c.items||[])[0]||{});return}
    b.disabled=true;msg.textContent='';const st=await send(what);b.disabled=false;if(!st)return;
    if(st==='no'){row.remove();msg.textContent=t('Abgelehnt, nichts geändert.','Declined, nothing changed.');return}
    if(st==='applied'){after();row.innerHTML=`<button type="button" class="b" data-hdo="undo">${esc(t('Rückgängig','Undo'))}</button>`;msg.textContent=t('Übernommen.','Applied.');return}
    if(st==='undone'){after();row.remove();msg.textContent=t('Zurückgenommen, alles wie vorher.','Undone, everything as before.')}});
  return d}
// ---------------------------------------------------------------- Frag Spark (chat.spark_drawer)
const hilfeOpen={on:false,msgs:[],ctrl:null};
function hilfePage(){const pm=$('profmodal');
  if(pm&&pm.style.display==='grid'){const tab=document.querySelector('#profmodal .ptab.on');return tab&&/^[a-z]{2,10}box$/.test(tab.id)?'me/'+tab.id:'me/setbox'}
  const sec=document.querySelector('main section.on'),id=sec?sec.id:'chat';
  if(id==='cfg'){if(document.querySelector('.cfgwrap.featmode'))return 'feat';const b=document.querySelector('#cfgnav button.on[data-p]');return 'cfg/'+(b&&/^[a-z]{2,8}$/.test(b.dataset.p)?b.dataset.p:'start')}
  return ['chat','mon','live','test','logs','who','int','prof','apps'].includes(id)?id:'chat'}
function hilfePageName(p){if(p.startsWith('me/')){const n=typeof ME_NAME!=='undefined'&&ME_NAME[p.slice(3)];return t('Ich','Me')+(n?' → '+(L==='en'?n[1]:n[0]):'')}
  if(p.startsWith('cfg/')){const b=document.querySelector(`#cfgnav button[data-p="${p.slice(4)}"]`);return t('Einstellungen','Settings')+(b?' → '+visText(b):'')}
  if(p==='feat')return t('Funktionen','Features');const b=document.querySelector(`nav button[data-s="${p}"]`);return b?visText(b):p}
function hilfeFab(){let f=$('hilfefab');const want=!!(HILFE&&HILFE.page);   // whoami gives it only to a signed-in profile
  if(!want){if(f)f.hidden=true;if(hilfeOpen.on)hilfeClose();return}
  if(!f){f=document.createElement('button');f.id='hilfefab';f.type='button';f.className='b p hilfefab';f.textContent=t('Frag Spark','Ask Spark');
    f.addEventListener('click',()=>hilfeOpen.on?hilfeClose():hilfeShowDrawer());document.body.appendChild(f)}
  f.hidden=false}
function hilfeShowDrawer(){let d=$('hilfedraw');
  if(!d){d=document.createElement('div');d.id='hilfedraw';d.className='card hilfedraw';d.setAttribute('role','dialog');d.setAttribute('aria-label',t('Frag Spark','Ask Spark'));
    d.innerHTML=`<div class="hhead"><b>${esc(t('Frag Spark','Ask Spark'))}</b><button type="button" class="ib" id="hilfex" aria-label="${esc(t('Schließen','Close'))}">✕</button></div>
      <div class="hpage mut" id="hilfepg"></div><div class="hlog" id="hilfelog"></div>
      <form class="hask" id="hilfeform"><input id="hilfeq" maxlength="500" autocomplete="off" placeholder="${esc(t('Frage zu dieser Seite …','Question about this page …'))}"><button class="b p" type="submit">${esc(t('Fragen','Ask'))}</button></form>`;
    document.body.appendChild(d);$('hilfex').addEventListener('click',hilfeClose);
    $('hilfeform').addEventListener('submit',e=>{e.preventDefault();const q=$('hilfeq').value.trim();if(q){$('hilfeq').value='';hilfeAsk(q)}})}
  hilfeOpen.page=hilfePage();$('hilfepg').textContent=t('Du bist auf: ','You are on: ')+hilfePageName(hilfeOpen.page);
  d.hidden=false;hilfeOpen.on=true;setTimeout(()=>$('hilfeq').focus(),50)}
function hilfeClose(){const d=$('hilfedraw');if(d)d.hidden=true;hilfeOpen.on=false;if(hilfeOpen.ctrl)hilfeOpen.ctrl.abort()}
function hilfeLine(cls,text){const el=document.createElement('div');el.className=cls;el.textContent=text;$('hilfelog').appendChild(el);return el}
async function hilfeAsk(q){if(hilfeOpen.ctrl)return;hilfeLine('hq',q);const a=hilfeLine('ha typing','…');hilfeOpen.msgs.push({role:'user',content:q});
  const ctrl=new AbortController();hilfeOpen.ctrl=ctrl;let full='',err='';const cards=[];
  try{const r=await api('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},signal:ctrl.signal,
      body:JSON.stringify({messages:hilfeOpen.msgs.slice(-10),speak:false,page:hilfeOpen.page,tz:(()=>{try{return Intl.DateTimeFormat().resolvedOptions().timeZone}catch{return ''}})()})});
    const rd=r.body.getReader(),dec=new TextDecoder();let buf='';
    for(;;){const{value,done}=await rd.read();if(done)break;buf+=dec.decode(value,{stream:true});let i;
      while((i=buf.indexOf('\n\n'))>=0){const line=buf.slice(0,i).split('\n').find(l=>l.startsWith('data:'));buf=buf.slice(i+2);if(!line)continue;let ev;try{ev=JSON.parse(line.slice(5))}catch{continue}
        if(ev.type==='text'){full+=ev.delta;a.classList.remove('typing');a.textContent=full;$('hilfelog').scrollTop=1e9}
        else if(ev.type==='retract'){full=full.slice(0,full.length-ev.drop);a.textContent=full}
        else if(ev.type==='hilfe'&&ev.card)cards.push(ev.card);
        else if(ev.type==='error'&&!err)err=typeof errText==='function'?errText(ev.code,ev.message):String(ev.message||'')}}}
  catch(e){if(e.name!=='AbortError')err=e.message}
  hilfeOpen.ctrl=null;a.classList.remove('typing');
  if(full.trim())hilfeOpen.msgs.push({role:'assistant',content:full.trim()});else{hilfeOpen.msgs.pop();a.textContent=err||'–'}
  for(const c of cards)a.appendChild(hilfeCard(c));$('hilfelog').scrollTop=1e9}
