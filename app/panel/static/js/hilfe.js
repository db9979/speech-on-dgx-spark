// Spark-Hilfe (hilfe.py, V01.0.326): the card under an answer with the switches the assistant suggests, and
// "Frag Spark", a small window on every page that knows the page it was opened on. The card never switches by
// itself: only the tap on "Übernehmen" sends the card's id to the panel, which applies exactly what it holds,
// with the same checks as the forms (and the admin's code for Spark switches). Everything shown is text (esc).
let HILFE=null;   // from /api/whoami: {suggest, page} for this profile, null = off
function hilfeStart(h){HILFE=h&&typeof h==='object'?h:null;hilfeFab();if(HILFE&&HILFE.page&&!(HQIDS&&HQIDS.size))hilfeIds()}
// the rows the help has an entry for (B3): a "?" stands only there, never one that would fall back to a general search
let HQIDS=null,HQLOAD=null;
function hilfeIds(){if(!HQLOAD)HQLOAD=api('/api/hilfe/ids').then(r=>r.json()).catch(()=>({ids:[]})).then(d=>{HQIDS=new Set(d.ids||[]);if(!HQIDS.size)HQLOAD=null;hilfeFab()}).catch(()=>{HQLOAD=null})}
// after the admin saved or Ich opened: what /api/whoami says now (the switches can have changed meanwhile)
async function hilfeRefresh(){try{const w=await (await api('/api/whoami')).json();if(PROFILE||w.profile)hilfeStart(w.hilfe)}catch{}}
const HON=v=>v?t('an','on'):t('aus','off');
function hilfeShow(x){   // "Zeig mir wo": the switch on its page
  $('fab').classList.remove('open');
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
// ---------------------------------------------------------------- Frag Spark (chat.spark_drawer): the face at the bottom right
// The face is the same assistant on every page, so no button of its own: with "Frag Spark auf jeder Seite" on it
// also shows over Ich and for profiles, names the page it is on, takes a typed question too, and every question
// asked through it (spoken or typed, chat.js ask()) carries the page. Same conversation as the chat.
function hilfePage(){const pm=$('profmodal');
  if(pm&&pm.style.display==='grid'){const tab=document.querySelector('#profmodal .ptab.on');return tab&&/^[a-z]{2,10}box$/.test(tab.id)?'me/'+tab.id:'me/setbox'}
  const sec=document.querySelector('main section.on'),id=sec?sec.id:'chat';
  if(id==='cfg'){if(document.querySelector('.cfgwrap.featmode'))return 'feat';const b=document.querySelector('#cfgnav button.on[data-p]');return 'cfg/'+(b&&/^[a-z]{2,8}$/.test(b.dataset.p)?b.dataset.p:'start')}
  return ['chat','mon','live','test','logs','tech','route','int','prof','apps'].includes(id)?id:'chat'}
function hilfePageName(p){if(p.startsWith('me/')){const n=typeof ME_NAME!=='undefined'&&ME_NAME[p.slice(3)];return t('Ich','Me')+(n?' → '+(L==='en'?n[1]:n[0]):'')}
  if(p.startsWith('cfg/')){const b=document.querySelector(`#cfgnav button[data-p="${p.slice(4)}"]`);return t('Einstellungen','Settings')+(b?' → '+visText(b):'')}
  if(p==='feat')return t('Funktionen','Features');const b=document.querySelector(`nav button[data-s="${p}"]`);return b?visText(b):p}
// the page a question goes with: only through the face (not in the chat itself), only when switched on
function hilfeNow(){if(!(HILFE&&HILFE.page))return undefined;const p=hilfePage();return p==='chat'?undefined:p}
const hilfeFabOn=()=>!!(HILFE&&HILFE.page)&&!!hilfeNow();
// typing a question into the face works for everybody signed in; the page only goes along with "Frag Spark auf jeder Seite"
const hilfeAsk=()=>!document.body.classList.contains('guest')&&!!((typeof PROFILE!=='undefined'&&PROFILE)||(typeof ADMIN!=='undefined'&&ADMIN));
// "?" at every switch row (plan hilfe-besser 2): asks the face about exactly this switch; the panel checks the id.
// It sits right after the row's title, never inside it: the title's text stays the switch's name (screen readers,
// the tests), whether the list of ids has arrived yet or not.
let HFOCUS=null;
function hilfeFocusTake(){const f=HFOCUS;HFOCUS=null;return f||undefined}
function hilfeRowId(row){const i=[...row.querySelectorAll('input[id],select[id]')].find(x=>!x.closest('.lbl'));if(!i)return null;   // a field in the sentence is not the row's
  const m=/^set_setform_(\w{1,40})$/.exec(i.id);if(m)return 'me:'+m[1];return /^[\w.]{1,40}$/.test(i.id)&&!i.id.startsWith('set_')?'sw:'+i.id:null}
function hilfeMarks(){document.querySelectorAll('main section.on .setrow .lbl b, #profmodal .setrow .lbl b').forEach(b=>{
  if(b.nextElementSibling&&b.nextElementSibling.classList.contains('hqbtn'))return;const row=b.closest('.setrow'),id=row&&hilfeRowId(row);if(!id||!HQIDS||!HQIDS.has(id))return;
  const q=document.createElement('button');q.type='button';q.className='hqbtn';q.dataset.hq=id;q.textContent='?';
  q.setAttribute('aria-label',t('Frag Spark zu diesem Schalter','Ask Spark about this switch'));b.after(q)})}
document.addEventListener('click',e=>{const q=e.target.closest('.hqbtn');if(!q||!hilfeFabOn())return;e.preventDefault();e.stopPropagation();
  const b=q.previousElementSibling,name=b?[...b.childNodes].filter(n=>n.nodeType===3).map(n=>n.nodeValue).join('').trim():'';
  HFOCUS=q.dataset.hq;$('fab').classList.add('open');if(typeof stopListening==='function')stopListening(true);
  ask(t(`Was macht „${name}“ und wie steht es bei mir?`,`What does "${name}" do and how is it set for me?`))},true);
function hilfeFab(){const on=hilfeFabOn(),b=document.body;b.classList.toggle('hilfeon',on);if(on)hilfeMarks();
  const box=$('fabask');if(!box)return;box.hidden=!(on||hilfeAsk());$('fabpage').textContent=on?t('Du bist auf: ','You are on: ')+hilfePageName(hilfeNow()):'';$('fabq').placeholder=on?t('Frag etwas zu dieser Seite …','Ask something about this page …'):t('Frag etwas …','Ask something …');
  if(!on&&!(HILFE&&HILFE.page))$('fabcards').textContent=''}
function hilfeFabCards(cards){const el=$('fabcards');if(!el)return;el.textContent='';
  if($('fab').classList.contains('open'))for(const c of cards)el.appendChild(hilfeCard(c))}
{const f=$('fabask');if(f){f.addEventListener('submit',e=>{e.preventDefault();const q=$('fabq').value.trim();if(!q||!(hilfeFabOn()||hilfeAsk()))return;$('fabq').value='';
    if(typeof stopListening==='function')stopListening(true);$('fab').classList.add('open');ask(q)});
  $('fabq').addEventListener('focus',()=>{if(typeof stopListening==='function')stopListening(true)})}
 // the page changes without a call into this file (menu, Ich, Funktionen): follow the body, Ich and the menus
 const mo=new MutationObserver(ms=>{if(ms.every(m=>m.type==='childList'&&[...m.addedNodes].every(n=>n.classList&&n.classList.contains('hqbtn'))))return;hilfeFab()});
 mo.observe(document.body,{attributes:true,attributeFilter:['class']});
 const pm=$('profmodal');if(pm)mo.observe(pm,{attributes:true,attributeFilter:['style','class'],subtree:true,childList:true});
 for(const id of['cfgnav']){const n=$(id);if(n)mo.observe(n,{attributes:true,subtree:true,attributeFilter:['class']})}
 document.querySelectorAll('main section').forEach(x=>mo.observe(x,{attributes:true,attributeFilter:['class']}))}
