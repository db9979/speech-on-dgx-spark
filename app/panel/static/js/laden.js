// Seiten sichtbar laden (plan plaene/seiten-laden.md, Dominik 12.10.2026: „wenn eine Seite noch nicht ganz aufgebaut
// ist, sollte dies visuell dargestellt werden“). Four parts, all display only:
// - a thin bar on top while what the person just opened or pressed is loading (lzFetch, used by api() in base.js);
//   polls on a timer (Zustand every 3 s, Live, the version check) do not move it;
// - grey placeholder rows in a box until its data is there, the last data dimmed with „wird aktualisiert …“ when a
//   page is opened again, „dauert länger als sonst …“ after 8 s, and the error in the box itself with „Noch einmal“
//   (ladeBox); one box that fails takes nothing from the rest of the page;
// - an end to waiting: after 30 s a box says so with „Noch einmal“ (the answer still shows if it comes later);
// - a band on top when the Spark does not answer at all, which tries again by itself and reloads the open page once
//   it is back.
// Built with textContent only; buttons go through data-on (strict CSP). Nothing is kept in the browser's storage.
const LZ={n:0,t:0,shown:0,act:0,boot:Date.now(),wait:30e3,slow:8e3,show:150,fails:0,band:null,next:0,tick:0};
document.addEventListener('pointerdown',()=>LZ.act=Date.now(),true);
document.addEventListener('keydown',()=>LZ.act=Date.now(),true);
// scrolling by hand counts as moving too: a box that finished drawing never scrolls the page back then (ladeBox)
for(const ev of ['wheel','touchmove'])document.addEventListener(ev,()=>LZ.act=Date.now(),{capture:true,passive:true});
window.addEventListener('hashchange',()=>LZ.act=Date.now());
function lzBarEl(){let b=$('lzbar');if(!b){b=document.createElement('div');b.id='lzbar';b.hidden=true;b.setAttribute('role','progressbar');
  b.setAttribute('aria-label',t('Seite lädt','Page loading'));b.append(document.createElement('i'));document.body.append(b)}return b}
// counted only right after a click, a key or the start of the page: a timer's poll is no "the page is loading"
function lzBegin(force){if(!force&&Date.now()-LZ.act>1500&&Date.now()-LZ.boot>4000)return null;
  if(++LZ.n===1){clearTimeout(LZ.t);LZ.t=setTimeout(()=>{if(LZ.n>0){lzBarEl().hidden=false;LZ.shown=Date.now()}},LZ.show)}
  let done=false;
  return ()=>{if(done)return;done=true;LZ.n=Math.max(0,LZ.n-1);if(LZ.n)return;clearTimeout(LZ.t);const b=$('lzbar');
    if(b&&!b.hidden)LZ.t=setTimeout(()=>{if(!LZ.n)b.hidden=true},Math.max(0,300-(Date.now()-LZ.shown)))}}
window.lzBegin=lzBegin;
const lzTimeout=()=>new Error(t('Keine Antwort nach 30 Sekunden. Der Spark arbeitet vielleicht gerade viel. Bitte noch einmal versuchen.',
  'No answer after 30 seconds. The Spark may be very busy right now. Please try again.'));
// fetch for api(): the bar, and what the band needs to know. Nothing is cut off here: a box gives up waiting by itself
// after 30 s (ladeBox) and still shows the answer if it comes later.
window.lzFetch=async(p,o={})=>{const end=lzBegin(false);
  try{const r=await /*raw: lzFetch is the loading bar api() itself uses*/fetch(p,o);lzNet(r.status);return r}
  catch(e){if(!(e&&e.name==='AbortError'))lzNet(0);throw e}
  finally{if(end)end()}};
// ---------------------------------------------------------------- the band: the Spark does not answer
// two failed requests in a row (no network answer, 502 or 504 from a proxy) show it; 503 is the Notaus, not "gone".
// It sits fixed on top, above Ich and the dialogs.
// While the update window is open the panel restarts on purpose: that window says so, the band stays away.
function lzNet(st){if(st===0||st===502||st===504){if(++LZ.fails>=2&&!updBusy())lzDown();return}
  LZ.fails=0;if(LZ.band&&!LZ.band.hidden)lzUp()}
function lzDown(){let b=LZ.band;if(!b){b=LZ.band=document.createElement('div');b.id='lzband';b.className='lzband';b.setAttribute('role','alert');
    const s=document.createElement('b');s.textContent=t('Spark antwortet nicht.','The Spark is not answering.');
    const m=document.createElement('span');m.id='lzbandmsg';
    const go=document.createElement('button');go.type='button';go.className='b';go.dataset.on='lzPing';go.textContent=t('Jetzt versuchen','Try now');
    b.append(s,m,go);const u=$('updbanner');if(u)u.before(b);else document.body.prepend(b)}
  if(!b.hidden&&LZ.tick)return;b.hidden=false;LZ.next=Date.now()+5e3;clearInterval(LZ.tick);LZ.tick=setInterval(lzCount,1000);lzCount()}
function lzCount(){const left=Math.ceil((LZ.next-Date.now())/1000);
  if(left<=0){lzPing();return}
  const m=$('lzbandmsg');if(m)m.textContent=t(`Neuer Versuch in ${left} s …`,`Trying again in ${left} s …`)}
async function lzPing(){LZ.next=Date.now()+5e3;const m=$('lzbandmsg');if(m)m.textContent=t('Versuche …','Trying …');
  try{const r=await /*raw: the is-the-Spark-back probe of the band api() uses*/fetch('/api/whoami',{cache:'no-store'});if(r.ok||r.status===401||r.status===403){LZ.fails=0;lzUp()}}catch{}}
ON.lzPing=()=>lzPing();
// back: the band goes, and the open page loads what it shows again (never the settings form: unsaved changes stay)
function lzUp(){clearInterval(LZ.tick);LZ.tick=0;if(LZ.band)LZ.band.hidden=true;
  try{if($('profmodal').style.display==='grid'&&typeof meLoadOnce==='function')meLoadOnce()
    else{const s=document.querySelector('main section.on');if(s&&['mon','prof','route','logs','apps','live'].includes(s.id))showSec(s.id)}}catch{}}
// ---------------------------------------------------------------- placeholders in a box
// forms: 'zeilen' (a list), 'karten' (tiles, Zustand and Live), 'tabelle' (rows of a table)
function lzSkel(form,n){const d=document.createElement('div');d.className='lz-sk lz-'+(form||'zeilen');d.setAttribute('aria-hidden','true');
  for(let i=0;i<(n||3);i++){const r=document.createElement('div');r.className='lz-r';for(const c of ['c','l','s']){const x=document.createElement('i');x.className=c;r.append(x)}d.append(r)}
  return d}
// puts placeholders where the data will go; in a table as one row over all columns
function lzPut(at,el,top){if(at.tagName==='TBODY'||at.tagName==='TABLE'){const tr=document.createElement('tr'),td=document.createElement('td');
    tr.className='lz-skrow';td.colSpan=20;td.append(el);tr.append(td);el=tr;at=at.tagName==='TABLE'?at.tBodies[0]||at:at}
  if(top)at.prepend(el);else at.append(el);return el}
// placeholders into an empty place only (Zustand's tiles, Live before its first answer); the page's own drawing replaces them
function lzSkelIn(at,form,n){if(!at||at.childElementCount)return;at.append(lzSkel(form,n))}
window.lzSkelIn=lzSkelIn;
function lzChip(text,cls){const c=document.createElement('span');c.className='lz-chip'+(cls?' '+cls:'');c.textContent=text;return c}
// ladeBox(box, load, o): runs load() (which draws into the box) and shows meanwhile what is going on.
// o.at: where placeholders and the error go (default the box); o.form, o.n: the placeholders; o.quiet: an error
// stays silent (boxes that were silent before); o.auth: a 401 is passed on (Ich: then the profile is signed out);
// o.stale: false keeps the old content undimmed and o.skel: false shows no placeholders (settings forms, whose fields
// stand there anyway); o.top: chips and the error go on top of o.at. A newer run on the same box replaces the older one.
let LZ_SEQ=0,LZ_RUN=0;
// true while no box is loading: what the browser tests wait for after opening a page (never a fixed pause; a switch
// flipped before the settings are there would be set back by them)
window.lzIdle=()=>LZ_RUN===0;
// Nothing jumps (plaene/ruhige-seiten.md): parts that were open in the box (<details>) open again when the box drew
// them anew, and the page keeps its scroll when drawing made it shorter for a moment, unless the person moved meanwhile.
// While the update window is open a box keeps its last content quietly instead of an error.
async function ladeBox(box,load,o={}){if(!box)return load();
  const keep=lzKeep(box);
  const id=String(++LZ_SEQ),at=o.at||box,had=box.dataset.lzok==='1',made=[];box.dataset.lz=id;box.classList.add('lz-host');
  box._lzAgain=()=>ladeBox(box,load,o);
  lzErrOff(box);
  const mine=()=>box.dataset.lz===id;
  box.setAttribute('aria-busy','true');
  let chip=null;LZ_RUN++;
  const t1=setTimeout(()=>{if(!mine())return;
    if(had){if(o.stale!==false)box.classList.add('lz-stale');chip=lzChip(t('wird aktualisiert …','updating …'));made.push(lzPut(at,chip,true))}
    else if(o.skel!==false)made.push(lzPut(at,lzSkel(o.form,o.n),o.top))},LZ.show);
  const t2=setTimeout(()=>{if(!mine())return;box.classList.add('lz-slow');const say=t('dauert länger als sonst …','taking longer than usual …');
    if(chip){chip.textContent=say;chip.classList.add('w')}else{chip=lzChip(say,'w');made.push(lzPut(at,chip,true))}},LZ.slow);
  const t3=setTimeout(()=>{if(!mine())return;made.forEach(x=>x.remove());made.length=0;chip=null;box.classList.remove('lz-slow','lz-stale');lzErr(box,at,o,lzTimeout())},LZ.wait);
  try{const r=await load();if(mine()){box.dataset.lzok='1';lzErrOff(box);keep()}return r}
  catch(e){if(o.auth&&e&&e.status===401)throw e;if(mine())lzErr(box,at,updBusy()?{...o,quiet:true}:o,e)}
  finally{LZ_RUN--;clearTimeout(t1);clearTimeout(t2);clearTimeout(t3);made.forEach(x=>x.remove());
    if(mine()){box.classList.remove('lz-stale','lz-slow');box.removeAttribute('aria-busy')}}}
// what ladeBox (and users.js) put back after drawing: the scroll, when drawing made the page shorter for a moment
function lzKeep(box){const y=window.scrollY,act=LZ.act;return ()=>{if(LZ.act===act&&window.scrollY<y-2&&box&&box.offsetParent)window.scrollTo(0,y)}}
// Open stays open, everywhere (plaene/ruhige-seiten.md): a part the person opened or closed (<details>) keeps that
// state when its box is drawn anew (a save, a poll, a reload of the box), found again by the nearest id and the
// summary's words (numbers left out: „3 Einstellungen …“ stays the same part). Memory only, never stored.
const LZ_OPEN=new Map();
const lzOpenKey=d=>{const s=d.querySelector(':scope>summary'),h=d.parentElement&&d.parentElement.closest('[id]');
  return s?(h?h.id:'')+'|'+s.textContent.replace(/\d+/g,'#').replace(/\s+/g,' ').trim().slice(0,80):''};
document.addEventListener('toggle',e=>{const d=e.target;if(!(d instanceof HTMLDetailsElement)||!d.isConnected||d._lzSet)return;const k=lzOpenKey(d);if(k)LZ_OPEN.set(k,d.open)},true);
new MutationObserver(ms=>{if(!LZ_OPEN.size)return;for(const m of ms)for(const n of m.addedNodes){if(n.nodeType!==1)continue;
    const ds=n.tagName==='DETAILS'?[n]:n.querySelectorAll('details');
    for(const d of ds){const k=lzOpenKey(d);if(!k||!LZ_OPEN.has(k))continue;const want=LZ_OPEN.get(k);if(d.open!==want){d._lzSet=1;d.open=want;setTimeout(()=>{d._lzSet=0},0)}}}})
  .observe(document.body,{childList:true,subtree:true});
const lzErrOff=box=>box.querySelectorAll('.lz-err').forEach(e=>{if(e.closest('.lz-host')===box)(e.closest('.lz-skrow')||e).remove()});
// the error in the box: the panel's sentence (errSay in api()), „Noch einmal“, and for the admin where to look further
function lzErr(box,at,o,e){lzErrOff(box);if(o.quiet)return;
  const er=document.createElement('div');er.className='lz-err';er.setAttribute('role','alert');
  const p=document.createElement('p');p.textContent=(e&&e.message)||t('Konnte nicht geladen werden.','Could not be loaded.');
  const again=document.createElement('button');again.type='button';again.className='b';again.dataset.on='lzAgain';again.textContent=t('Noch einmal','Try again');
  er.append(p,again);
  // way.js turns the way into a link for the admin; profiles cannot open the logs
  if(typeof ADMIN!=='undefined'&&ADMIN){const w=document.createElement('span');w.className='mut';w.textContent=t('Mehr dazu unter Zustand → Logs → Diagnose.','More under Status → Logs → Diagnosis.');er.append(w)}
  lzPut(at,er,o.top)}
window.ladeBox=ladeBox;window.lzKeep=lzKeep;
ON.lzAgain=b=>{const h=b.closest('.lz-host');if(h&&h._lzAgain)h._lzAgain()};
// at most `most` loads at the same time (Ich has ~30 boxes; all at once would meet the rate limits)
async function lzPool(jobs,most){let i=0;const run=async()=>{while(i<jobs.length){const j=jobs[i++];await j()}};
  await Promise.all(Array.from({length:Math.min(most,jobs.length)},run))}
window.lzPool=lzPool;
// Zustand's tiles until the first answer of /api/status (zCards replaces them)
lzSkelIn($('zcards'),'karten',3);
