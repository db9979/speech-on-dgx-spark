// ---------------------------------------------------------------- Apps merken sich den letzten Stand (appmerken.py)
// Only inside the Android app (IN_ANDROID, android.js) and only while /api/profile/settings says app_keep (the admin
// switch chat.app_cache, the profile not blocked): the page keeps the last answer of the conversations (the 20 newest
// with their last 50 messages), the chats list and the own settings for its profile in the app's own storage and
// shows it at once on the next start, with „Stand 16:05 · wird aktualisiert …“, until the Spark has answered. Never a
// guest, never the admin's pages, never a key or a code. Signing out, another profile and the switch off delete it
// (merkWipe); the copy for reading offline in a trusted browser is verlauf.js, this one is only for the app.
// A load that needs SLOW_MS or more is told to the Spark once in 10 minutes (POST /api/app/langsam: page word and
// milliseconds only, appmerken.PAGES).
const MERK='merk:',MERK_CONVOS=20,MERK_MSGS=50,MERK_MAX=1500000,MERK_SLOW=2000,MERK_AHEAD=300e3;
const MERKST={on:null,who:'',said:{},ahead:0,setKept:false,paged:false};   // on: what the Spark said last for the profile who
function merkOn(){if(typeof IN_ANDROID==='undefined'||!IN_ANDROID||!PROFILE)return false;if(MERKST.who===PROFILE.id)return MERKST.on;
  try{return localStorage.getItem(MERK+'on:'+PROFILE.id)==='1'}catch{return false}}
function merkKeys(){const out=[];try{for(let i=0;i<localStorage.length;i++){const k=localStorage.key(i);if(k&&k.startsWith(MERK))out.push(k)}}catch{}return out}
// everything kept except this profile's own while it may keep (all: everything, signing out)
function merkWipe(all){const mine=!all&&PROFILE&&merkOn()?MERK+PROFILE.id+':':null,flag=PROFILE?MERK+'on:'+PROFILE.id:null;
  for(const k of merkKeys())if(!(mine&&(k.startsWith(mine)||k===flag)))try{localStorage.removeItem(k)}catch{}}
// the Spark's word (app_keep in /api/profile/settings): from now on keep, or delete everything kept
function merkAllow(keep){if(!PROFILE)return;MERKST.on=!!(keep&&IN_ANDROID);MERKST.who=PROFILE.id;
  try{if(MERKST.on)localStorage.setItem(MERK+'on:'+PROFILE.id,'1')}catch{}merkWipe(false)}
function merkPut(name,data){if(!merkOn())return;let s='';try{s=JSON.stringify({at:Date.now(),d:data})}catch{return}
  if(s.length>MERK_MAX)return;try{localStorage.setItem(MERK+PROFILE.id+':'+name,s)}catch{}}
function merkGet(name){if(!merkOn())return null;try{const x=JSON.parse(localStorage.getItem(MERK+PROFILE.id+':'+name)||'null');
  return x&&typeof x.at==='number'?x:null}catch{return null}}
// the conversations as /api/profile/convos sends them, cut down: the newest with their last messages
function merkConvos(list){if(!Array.isArray(list))return;
  merkPut('verlauf',list.slice().sort((a,b)=>(b.updated||0)-(a.updated||0)).slice(0,MERK_CONVOS).map(c=>({...c,msgs:(c.msgs||[]).slice(-MERK_MSGS)})))}
// a kept state on screen: the small note above the chat until the Spark answered (nothing: the note goes)
function merkNote(at){const n=$('merknote');if(!n)return;if(!at){n.hidden=true;return}
  const d=new Date(at),today=d.toDateString()===new Date().toDateString();
  const time=d.toLocaleString(L==='en'?'en-GB':'de-DE',today?{hour:'2-digit',minute:'2-digit'}:{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  n.textContent=t('Stand ','As of ')+time+t(' · wird aktualisiert …',' · refreshing …');n.hidden=false}
function merkFailed(){const n=$('merknote');if(n&&!n.hidden)n.textContent=n.textContent.replace(/ · .*$/,t(' · Spark gerade nicht erreichbar',' · Spark not reachable right now'))}
// a load that took long: once per page in 10 minutes into the Spark's log (only inside the app)
function merkTime(page,began){const ms=Math.round(performance.now()-began);
  if(ms<MERK_SLOW||typeof IN_ANDROID==='undefined'||!IN_ANDROID||!PROFILE||Date.now()-(MERKST.said[page]||0)<600e3)return;MERKST.said[page]=Date.now();
  api('/api/app/langsam',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seite:page,ms:Math.min(ms,600000)})}).catch(()=>{})}
// the page's start inside the app, from opening until the own settings were there (once per page)
function merkPage(){if(!MERKST.paged){MERKST.paged=true;merkTime('seite',0)}}
// back in front, at most every 5 minutes: the own settings and the chats list once in the background (the
// conversations come anyway: chat.js convoLook on visibilitychange, kept in convos.fresh)
function merkAhead(){if(document.hidden||!merkOn()||Date.now()-MERKST.ahead<MERK_AHEAD)return;MERKST.ahead=Date.now();
  loadSettings().catch(()=>{});if(window.CHATS_ON&&typeof cxLoad==='function'&&!CX.shown)cxLoad()}
document.addEventListener('visibilitychange',merkAhead);
