// Verlauf auf allen Geräten (verlauf.py, plan plaene/verlauf-vsync.md). chat.js adds only new messages, asks ?since=
// on coming back and every 30 s and closes a conversation deleted elsewhere. Here the two switches of the profile:
// "Verlauf sofort abgleichen" (one event stream: changes at once, "Handy antwortet gerade …") and "Verlauf offline
// lesen" (only on a browser the profile trusts: a copy of the conversations and questions asked without the Spark;
// every other browser keeps nothing and deletes what it had).
let OFFLINE_HERE=null;   // null: not known (no answer from the Spark), true/false: what /api/profile/settings said
const vsync={es:null,busy:{},t:null,keepT:null};
const OFFL='offl:',OFFQ='offq:',SHELL='spark-shell';

// ---------------------------------------------------------------- Sofort-Abgleich
function syncSettings(){const want=!!(PROFILE&&typeof ALLOW!=='undefined'&&ALLOW.sync_live&&typeof EventSource!=='undefined');
  if(want&&!vsync.es)syncStart();else if(!want&&vsync.es)syncStop();offlineKeep()}
function syncStart(){const es=new EventSource('/api/profile/convos/stream');vsync.es=es;
  es.onmessage=e=>{let ev;try{ev=JSON.parse(e.data)}catch{return}if(!ev||typeof ev!=='object')return;
    if(ev.type==='convo'){clearTimeout(vsync.t);vsync.t=setTimeout(()=>convoLook(true),300)}
    else if(ev.type==='busy'&&ev.tab!==TAB){vsync.busy[[ev.kind,ev.convo,ev.tab].join('|')]=ev;syncBusy()}
    else if(ev.type==='idle'){delete vsync.busy[[ev.kind,ev.convo,ev.tab].join('|')];syncBusy()}};
  // the browser opens it again by itself (retry 5 s); switched off (403) or signed out it stays closed
  es.onerror=()=>{if(es.readyState===2&&vsync.es===es){vsync.es=null;vsync.busy={};syncBusy()}}}
function syncStop(){if(vsync.es){vsync.es.close();vsync.es=null}vsync.busy={};syncBusy()}
// another device answers in the open conversation: a pale bubble with the kind of device, never the question
function syncBusy(){const log=$('chatlog');log.querySelectorAll('.msg.elsewhere').forEach(x=>x.remove());
  const here=Object.values(vsync.busy).filter(x=>!x.convo||x.convo===chat.cid);if(!here.length)return;
  const d=document.createElement('div');d.className='msg bot elsewhere';d.innerHTML='<div class="av"><i></i></div><div class="bubble"></div>';
  const n={Browser:t('Browser','Browser'),Handy:t('Handy','Phone'),'iPhone-App':t('iPhone-App','iPhone app'),CarPlay:'CarPlay',Lautsprecher:t('Lautsprecher','Speaker'),
    Uhr:t('Uhr','Watch'),Siri:'Siri',Telegram:'Telegram',Begleiter:t('Begleiter','Companion')}[here[0].name]||t('Anderes Gerät','Another device');
  d.lastChild.textContent=n+t(' antwortet gerade …',' is answering …');log.appendChild(d);log.scrollTop=1e9}

// ---------------------------------------------------------------- offline lesen (only a trusted browser)
function offlineKeys(){const out=[];try{for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i);if(k&&(k.startsWith(OFFL)||k.startsWith(OFFQ)))out.push(k)}}catch{}return out}
// deletes every copy except the signed-in profile's own on a browser it trusts (another profile's never stays)
function offlineWipe(all){const keep=!all&&PROFILE&&OFFLINE_HERE?[OFFL+PROFILE.id,OFFQ+PROFILE.id]:[];
  for(const k of offlineKeys())if(!keep.includes(k))try{localStorage.removeItem(k)}catch{}
  if(all||OFFLINE_HERE===false)try{if(window.caches)caches.delete(SHELL)}catch{}}
function offlineKeep(){if(OFFLINE_HERE===null)return;   // nothing known (the Spark did not answer): change nothing
  offlineWipe(false);if(!OFFLINE_HERE||!PROFILE)return;
  clearTimeout(vsync.keepT);vsync.keepT=setTimeout(()=>{if(!OFFLINE_HERE||!PROFILE)return;
    const c=convos.load().slice(0,30).map(x=>({id:x.id,title:x.title,updated:x.updated,msgs:(x.msgs||[]).slice(-60)}));
    try{localStorage.setItem(OFFL+PROFILE.id,JSON.stringify({at:Date.now(),p:{id:PROFILE.id,name:PROFILE.name},c}))}catch{}
    offlineShell()},800)}
function offlineCopy(){if(!PROFILE)return null;try{const d=JSON.parse(localStorage.getItem(OFFL+PROFILE.id)||'null');return d&&Array.isArray(d.c)?d:null}catch{return null}}
// the page itself (no personal data) for opening it again without the Spark; the service worker answers from it
// only while the device has no network
async function offlineShell(){if(!window.caches||vsync.shell===SPARK_VER)return;vsync.shell=SPARK_VER;
  try{const urls=['/',...[...document.querySelectorAll('script[src^="/static/"],link[rel=stylesheet][href^="/static/"]')].map(x=>x.getAttribute('src')||x.getAttribute('href'))];
    const c=await caches.open(SHELL);for(const k of await c.keys())await c.delete(k);await c.addAll(urls)}catch{vsync.shell=null}}
// opened without the Spark: who was signed in here (only from a trusted browser's copy)
function offlineWho(){for(const k of offlineKeys())if(k.startsWith(OFFL))try{const d=JSON.parse(localStorage.getItem(k));
  if(d&&d.p&&d.p.id)return {admin:false,profile:{id:String(d.p.id),name:String(d.p.name||'')},offline:true}}catch{}return null}
function offlineShow(d){chatSay(t('Ohne Verbindung zum Spark: Verlauf vom ','No connection to the Spark: history of ')+new Date(d.at).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})+t(', nur lesen.',', read only.'))}
// questions asked without the Spark (at most 10) go out once it answers again
// (opened without the Spark the settings are unknown: then only where the trusted copy is)
function offlineQueue(text){if(!PROFILE||!(OFFLINE_HERE===true||(OFFLINE_HERE===null&&offlineCopy())))return false;let q=[];try{q=JSON.parse(localStorage.getItem(OFFQ+PROFILE.id)||'[]')}catch{}
  if(!Array.isArray(q)||q.length>=10)return false;q.push(String(text).slice(0,2000));try{localStorage.setItem(OFFQ+PROFILE.id,JSON.stringify(q))}catch{return false}return true}
async function offlineFlush(){if(!PROFILE||vsync.flushing)return;let q=[];try{q=JSON.parse(localStorage.getItem(OFFQ+PROFILE.id)||'[]')}catch{}
  if(!Array.isArray(q)||!q.length)return;vsync.flushing=true;try{localStorage.removeItem(OFFQ+PROFILE.id)}catch{}
  try{for(const x of q){while(chat.ctrl||chat.rec)await new Promise(r=>setTimeout(r,300));await ask(String(x))}}finally{vsync.flushing=false}}
addEventListener('online',()=>{if(PROFILE)convoLook(true)});   // convoLook sends what waits once the Spark answers
