// Shared helpers: theme, API calls, main menu, copying, small formatters.
// Installable as an app ("Add to home screen"); the service worker caches nothing. Its address carries the
// version (set by panel.py), so the browser takes the new worker with each update.
const SPARK_VER=(document.querySelector('meta[name="spark-version"]')||{}).content||'';
const SW_URL='/sw.js?v='+encodeURIComponent(SPARK_VER);
if('serviceWorker' in navigator&&window.isSecureContext)navigator.serviceWorker.register(SW_URL).catch(()=>{});
// A newer version on the Spark (after an update): the page reloads itself, so no Strg+F5 is needed, also in
// the phone view and the home-screen app. Never during a conversation (recording, answer, playback, wake word,
// room mode) and not after something was typed in the last 10 minutes; then a bar offers "Neu laden".
const verWatch={seen:Date.now(),edit:0,back:0,newer:''};
document.addEventListener('pointerdown',()=>verWatch.seen=Date.now(),true);
document.addEventListener('keydown',()=>verWatch.seen=Date.now(),true);
document.addEventListener('input',e=>{if(e.target.type!=='checkbox'&&e.target.id!=='findq')verWatch.edit=Date.now()},true);
function sparkBusy(){try{return !!(chat.rec||chat.resumeMic||chat.ctrl||chat.asrBusy||chat.busy||playing()||wake.on||room.on)}catch{return true}}
function verReload(){try{const s=document.querySelector('section.on');if(s)sessionStorage.setItem('versec',s.id)}catch{}location.reload()}
function verBar(text){let b=$('verbanner');if(b)return;
  b=document.createElement('div');b.id='verbanner';b.className='updbanner';
  const sp=document.createElement('span');sp.textContent=text;
  const go=document.createElement('button');go.type='button';go.className='b p';go.textContent=t('Neu laden','Reload');go.onclick=verReload;
  b.append(sp,go);$('updbanner').before(b)}
function verTry(){const now=Date.now(),calm=!sparkBusy()&&now-verWatch.edit>600e3;
  if(calm&&(document.visibilityState==='hidden'||now-verWatch.back<5000||now-verWatch.seen>120e3))return verReload();
  verBar(t('Neue Version ist da: ','A new version is here: ')+verWatch.newer)}
// Switched a function on or off in the settings: the page reads the switches once at start (start.js), so
// after a saved change it compares them with the Spark and loads itself again when one differs (no F5).
const whoFlags=w=>JSON.stringify(Object.keys(w||{}).sort().filter(k=>typeof w[k]==='boolean'||k==='face').map(k=>[k,w[k]]));
let WHO_FLAGS=null,whoT=null;
async function whoCheck(){if(WHO_FLAGS===null)return;
  try{const r=await fetch('/api/whoami',{cache:'no-store'});if(!r.ok)return;const w=await r.json();
    if(whoFlags(w)===WHO_FLAGS)return;
    if(!sparkBusy()){try{sessionStorage.setItem('flagsreload','1')}catch{}return verReload()}
    verBar(t('Funktionen geändert, neu laden zeigt sie: ','Functions changed, reload shows them: '))}catch{}}
const whoSoon=()=>{clearTimeout(whoT);whoT=setTimeout(whoCheck,300)};
async function verCheck(){if(!SPARK_VER)return;if(verWatch.newer)return verTry();
  try{const r=await fetch('/api/whoami',{cache:'no-store'});if(!r.ok)return;const v=(await r.json()).version;
    if(v&&v!==SPARK_VER){verWatch.newer=v;verTry()}}catch{}}
setInterval(verCheck,300e3);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){verWatch.back=Date.now();verCheck()}});
window.addEventListener('pageshow',e=>{if(e.persisted){verWatch.back=Date.now();verCheck()}});
window.addEventListener('focus',()=>{verWatch.back=Date.now();verCheck()});
// Theme button: system -> light -> dark -> system; kept per browser.
$('themebtn').onclick=()=>{const cur=document.documentElement.dataset.theme||'auto',nx={auto:'light',light:'dark',dark:'auto'}[cur];
  if(nx==='auto')delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=nx;
  try{localStorage.setItem('theme',nx)}catch{}
  $('themebtn').title={auto:t('Farbschema: wie das System','Theme: follow the system'),light:t('Farbschema: hell','Theme: light'),dark:t('Farbschema: dunkel','Theme: dark')}[nx]};
// 428: the change needs a current code from the authenticator app (second login step); asked here, then sent again.
const api=async(p,o={},code)=>{const r=await fetch(p,code?Object.assign({},o,{headers:Object.assign({},o.headers||{},{'X-Speech-Code':code})}):o);
  if(r.status===428){const wrong=/wrong/.test(await r.text());
    const c=prompt((wrong?t('Code falsch. ','Wrong code. '):'')+t('Bitte den aktuellen Code aus deiner Authenticator-App eingeben (oder einen Wiederherstellungscode):','Please enter the current code from your authenticator app (or a recovery code):'));
    if(c&&c.trim())return api(p,o,c.trim());throw new Error(t('Abgebrochen: ohne Code keine Änderung.','Cancelled: no change without a code.'))}
  if(r.status===401&&!/^\/api\/(login|password|profile)/.test(p)&&window.showLogin)showLogin();if(!r.ok){let t=await r.text();try{t=JSON.parse(t).detail||t}catch{}throw new Error(t)}
  if(o.method&&o.method!=='GET'&&/^\/api\/(config|admin\/|profile\/)/.test(p))whoSoon();   // a switch may have changed
  return r};
// Main menu (design „Klar“, V01.0.145): on a computer a sidebar with Assistent and Ich for oneself, then
// "Spark verwalten" with Zustand, Einstellungen, Profile und Geräte, Einbinden; on phones a bar at the bottom.
const NI={chat:'<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',me:'<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
  mon:'<path d="M3 12h4l3 7 4-14 3 7h4"/>',cfg:'<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  prof:'<circle cx="9" cy="8" r="3.5"/><path d="M2 20c0-3.5 3-5.5 7-5.5s7 2 7 5.5M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c2.4.6 4 2.4 4 5.2"/>',int:'<path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5"/>',
  more:'<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>'};
document.querySelectorAll('i.ni').forEach(e=>e.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'+(NI[e.dataset.ni]||'')+'</svg>');
// the phone bar marks the page that is open (Ich while its window is open, else the section's menu entry)
function mbarMark(g){document.querySelectorAll('#mbar button').forEach(x=>x.classList.toggle('on',x.dataset.m===({chat:'chat',mon:'mon',me:'me'}[g]||'more')))}
// Main menu: five entries; Übersicht and Einbinden hold several pages behind a sub-tab bar. The cloned voices
// are a settings page (Einstellungen → Stimmen), not under Profile.
const GROUPS={chat:[['chat','']],mon:[['mon',t('Monitoring','Monitoring')],['test',t('Prüfen','Checks')],['logs',t('Logs','Logs')]],
  cfg:[['cfg','']],prof:[['prof','']],int:[['int',t('Anleitungen','Guides')],['apps',t('Apps und Schnittstellen','Apps and interfaces')]]};
const lastSec={};
function showSec(s){document.querySelectorAll('section').forEach(x=>x.classList.toggle('on',x.id===s));
  document.body.classList.toggle('inchat',s==='chat');
  if(s==='cfg'){document.querySelector('.cfgwrap').classList.remove('sub');loadCfg();mfaShow('admmfa','/api/mfa');if($('pane-voices').classList.contains('on'))loadClone();if($('pane-upd').classList.contains('on'))loadSys()}if(s==='chat')chatTab();if(s==='test'){loadVoices();instrHint();loadLive();loadBench()}if(s==='prof')loadProf();if(s==='logs')loadLogs();if(s==='apps')loadInt();}
// Zustand and Einbinden have several pages: computers show them as a second column like Einstellungen, phones as a
// list with one line of state that opens the page, with "back" on top (V01.0.207, same pattern everywhere)
const NARROW=()=>matchMedia('(max-width:760px)').matches;
const SUBDESC={mon:()=>($('ztitle')||{}).textContent||'',test:()=>t('Funktionsprüfung, Qualitätstest, Leistung messen, ausprobieren','Function check, quality test, performance, try out'),
  logs:()=>t('Was die Dienste schreiben, mit Diagnose-Filter','What the services write, with diagnosis filter'),int:()=>t('Zu jedem Dienst: einrichten, benutzen, ausschalten','For every service: set up, use, switch off'),
  apps:()=>t('Open WebUI, andere Apps, Pebble, Siri, curl und Python','Open WebUI, other apps, Pebble, Siri, curl and Python')};
const GNAME={mon:t('Zustand','Status'),int:t('Einbinden','Connect')};
function subnav(g,s){const items=GROUPS[g],bar=$('subnav'),many=items.length>1;bar.hidden=!many;document.querySelector('main').classList.toggle('hassub',many);
  if(!many)document.querySelector('main').classList.remove('sublist');
  bar.innerHTML=!many?'':items.map(([id,l])=>`<button type="button" data-sub="${id}"${id===s?' class="on"':''}>${esc(l)}<small class="gls">${esc(SUBDESC[id]?SUBDESC[id]():'')}</small></button>`).join('');
  $('subback').querySelector('span').textContent=GNAME[g]||'';
  bar.querySelectorAll('button').forEach(b=>b.onclick=()=>{lastSec[g]=b.dataset.sub;subnav(g,b.dataset.sub);document.querySelector('main').classList.remove('sublist');showSec(b.dataset.sub);if(NARROW())window.scrollTo(0,0)});updBadge(window.UPD)}
$('subback').onclick=()=>{const m=document.querySelector('main');m.classList.add('sublist');const z=bar=>bar&&bar.querySelector('[data-sub=mon] small');const sm=z($('subnav'));if(sm)sm.textContent=SUBDESC.mon();window.scrollTo(0,0)};
let goDirect=false;
document.querySelectorAll('nav button[data-s]').forEach(b=>b.onclick=()=>{const g=b.dataset.s,s=lastSec[g]||g;
  if($('profmodal').style.display==='grid'&&window.closeProf)closeProf();   // Ich is a page beside the menu: another entry closes it
  const direct=goDirect;goDirect=false;
  document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('on',x===b));subnav(g,s);showSec(s);mbarMark(g);
  document.querySelector('main').classList.toggle('sublist',!direct&&NARROW()&&GROUPS[g].length>1)});
window.goSec=s=>{if(s==='sys'){goCfg('upd');return}   // update and backups moved to Einstellungen (V01.0.207)
  goDirect=true;const g=Object.keys(GROUPS).find(k=>GROUPS[k].some(x=>x[0]===s));lastSec[g]=s;document.querySelector(`nav button[data-s=${g}]`).click()};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// for a value inside onclick="f('…')": a JavaScript string first, then HTML (a name with ' or \ stays text)
const escq=s=>esc(JSON.stringify(String(s??'')).slice(1,-1).replace(/'/g,"\\'"));
const pill=(s)=>{const c={active:'ok',ready:'ok',loading:'warn',activating:'warn',blocked:'bad',error:'bad',failed:'bad'}[s]||'';return `<span class="pill ${c}">${esc(s)}</span>`};
// The panel runs on plain http in the LAN, where navigator.clipboard is not available.
// navigator.clipboard needs https or localhost; the panel is usually plain http on the LAN,
// so there the copy event gets the text directly (copying a selection is unreliable)
function copyString(t,btn){const label=btn.textContent;const done=ok=>{btn.textContent=ok?t('kopiert','copied'):t('Markiert, jetzt Strg+C','Selected, now press Ctrl+C');setTimeout(()=>btn.textContent=label,2000)};
  if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(t).then(()=>done(true),()=>done(false));return true}
  const onCopy=e=>{e.clipboardData.setData('text/plain',t);e.preventDefault()};
  document.addEventListener('copy',onCopy);let ok=false;try{ok=document.execCommand('copy')}catch{}document.removeEventListener('copy',onCopy);
  done(ok);return ok}
function copyEl(id,btn){const el=$(id);if(!copyString(el.innerText||el.textContent,btn)){
  const sel=window.getSelection(),r=document.createRange();r.selectNodeContents(el);sel.removeAllRanges();sel.addRange(r)}}
window.copyString=copyString;window.copyEl=copyEl;
const fmt=(v,u='',d=0)=>v==null?'–':(+v).toFixed(d)+u;

function spark(svg,vals,max){const w=300,h=60;svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('preserveAspectRatio','none');
  const v=vals.filter(x=>x!=null);if(v.length<2){svg.innerHTML='';return}
  const m=max??(Math.max(...v)*1.1||1);const pts=vals.map((x,i)=>x==null?null:[i*w/(vals.length-1),h-2-(x/m)*(h-4)]).filter(Boolean);
  const d='M'+pts.map(p=>p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' L');
  svg.innerHTML=`<path d="${d} L${w} ${h} L0 ${h}Z" fill="var(--acc)" opacity=".12"/><path d="${d}" fill="none" stroke="var(--acc)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;}
