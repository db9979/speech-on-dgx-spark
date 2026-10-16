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
document.addEventListener('input',e=>{if(e.target.type!=='checkbox'&&e.target.id!=='findq'&&e.target.id!=='palq')verWatch.edit=Date.now()},true);
function sparkBusy(){try{return !!(chat.rec||chat.resumeMic||chat.ctrl||chat.asrBusy||chat.busy||playing()||wake.on||room.on)}catch{return true}}
// the page is going away (reload, new version): a request it cut off is no error worth an alert
let LEAVING=false;addEventListener('pagehide',()=>{LEAVING=true});
// Stelle merken (plaene/ruhige-seiten.md, Dominik 14.10.2026: „nichts soll an den Seitenanfang zurückspringen“): a reload
// the page does itself (new version, functions changed, update finished) comes back to the same place: the page, the
// settings page, the open function, person or Ich area and how far it was scrolled (start.js placeBack). Only names of
// pages and numbers, in this tab's sessionStorage, never contents. `to`: the page a click was going to (then no scroll).
function placeNow(to){const p={};try{const s=document.querySelector('section.on'),fm=document.querySelector('.cfgwrap.featmode');
    p.sec=to||(s&&s.id==='cfg'&&fm?'feat':s&&s.id);
    const pane=document.querySelector('#cfg .pane.on');if(pane&&p.sec==='cfg')p.pane=pane.id.slice(5);
    const it=document.querySelector('#pane-feat .fitem.open');if(it&&it.dataset.sw&&p.sec==='feat')p.feat=it.dataset.sw;
    if(typeof PL!=='undefined'&&PL.open&&p.sec==='prof')p.person=PL.open;
    if(!to&&$('profmodal')&&$('profmodal').style.display==='grid'){const b=document.querySelector('#ptabs button.on'),mb=document.querySelector('#profmodal .mebody');
      p.me=b?b.dataset.t:'';if(mb)p.mey=Math.round(mb.scrollTop)}
    if(!to)p.y=Math.round(window.scrollY)}catch{}return p}
// `to` as an object ({me:'mailbox'}): stay on this page and open that instead
function verReload(to){LEAVING=true;const o=to&&typeof to==='object';
  try{sessionStorage.setItem('place',JSON.stringify(o?{...placeNow(),y:undefined,mey:undefined,...to}:placeNow(to)))}catch{}location.reload()}
// the update window is open (admin.js ulShow): everything else keeps still, it alone says what goes on (no band, no bar,
// no reload of its own, no polling behind it)
const updBusy=()=>{const u=$('updlock');return !!u&&u.style.display!=='none'};
function verBar(text){let b=$('verbanner');if(b)return;
  b=document.createElement('div');b.id='verbanner';b.className='updbanner';
  const sp=document.createElement('span');sp.textContent=text;
  const go=document.createElement('button');go.type='button';go.className='b p';go.textContent=t('Neu laden','Reload');go.onclick=verReload;
  b.append(sp,go);$('updbanner').before(b)}
function verTry(){if(updBusy())return;const now=Date.now(),calm=!sparkBusy()&&now-verWatch.edit>600e3;
  if(calm&&(document.visibilityState==='hidden'||now-verWatch.back<5000||now-verWatch.seen>120e3))return verReload();
  verBar(t('Neue Version ist da: ','A new version is here: ')+verWatch.newer)}
// Switched a function on or off in the settings: the page reads the switches once at start (start.js), so
// after a saved change it compares them with the Spark and loads itself again when one differs (no F5).
// "rights" (features.stamp) changes with every switch under Gesperrte Funktionen that touches this profile. The face
// counts as the Spark's (face_spark): the profile's own pick (Ich → Gespräch) shows at once without a reload.
const whoFlags=w=>JSON.stringify(Object.keys(w||{}).sort().filter(k=>typeof w[k]==='boolean'||k==='face_spark'||k==='rights').map(k=>[k,w[k]]));
let WHO_FLAGS=null,whoT=null;
// who is signed in, set by start.js; declared here, before the other scripts: a timer or answer of an earlier script
// could run before start.js on a slow machine ("ADMIN is not defined", GitHub V01.0.421)
let ADMIN=false,PUBLIC=true,GATE=false;
// functions the admin blocked for this profile that still hold its own data (whoami "locked"): Ich shows „Daten löschen“
let ME_OWN=[];
async function whoCheck(){if(WHO_FLAGS===null)return;
  try{const r=await fetch('/api/whoami',{cache:'no-store'});if(!r.ok)return;const w=await r.json();
    if(window.confirmShow)confirmShow(w.confirm_until||0);
    if(whoFlags(w)===WHO_FLAGS)return;
    // only this profile's own switches moved (it switched them here): the page already shows them, no reload
    if(whoFlags(Object.assign({},w,{rights:0}))===whoFlags(Object.assign(JSON.parse(WHO_FLAGS).reduce((o,[k,v])=>(o[k]=v,o),{}),{rights:0}))){WHO_FLAGS=whoFlags(w);return}
    // saved here: the open page stays as it is (nothing closes, nothing jumps); the menu takes the new functions
    // with the next change of page, which then loads itself again right there (whoPendingGo)
    WHO_FLAGS=whoFlags(w);WHO_PENDING=true}catch{}}
// a page change while saved functions wait: load the page that was clicked, with the new menu
let WHO_PENDING=false;
function whoPendingGo(to){if(!WHO_PENDING||LEAVING||sparkBusy()||updBusy())return false;WHO_PENDING=false;verReload(to);return true}
document.addEventListener('click',e=>{if(!WHO_PENDING)return;const b=e.target.closest&&e.target.closest('nav button[data-s],.subnav button[data-sub]');if(!b)return;
  if(typeof dirtyPanes==='function'&&dirtyPanes().length)return;   // unsaved changes: admin.js asks first, the reload waits
  const to=b.dataset.sub||lastSec[b.dataset.s]||b.dataset.s;if(whoPendingGo(to)){e.stopImmediatePropagation();e.preventDefault()}},true);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')whoPendingGo()});
const whoSoon=()=>{clearTimeout(whoT);whoT=setTimeout(whoCheck,300)};
// Changed elsewhere (the admin under Gesperrte Funktionen, the profile on another device): checked every minute, on
// coming back and on focus, with the same calm rules as a new version (never mid-conversation or while typing).
// whoLocal(): this page itself just changed what /api/whoami says (Mein Notaus on or off): for 10 s such a change
// is taken as seen, not as "changed elsewhere" (the confirm dialog's focus would otherwise reload the page)
let WHO_LOCAL=0;function whoLocal(){WHO_LOCAL=Date.now()}
function flagsAway(w){if(WHO_FLAGS===null||whoFlags(w)===WHO_FLAGS||updBusy())return;
  if(Date.now()-WHO_LOCAL<10e3){WHO_FLAGS=whoFlags(w);return}
  const now=Date.now(),calm=!sparkBusy()&&now-verWatch.edit>600e3;
  if(calm&&(document.visibilityState==='hidden'||now-verWatch.back<5000||now-verWatch.seen>120e3)){try{sessionStorage.setItem('flagsreload','away')}catch{}return verReload()}
  verBar(t('Deine Funktionen wurden geändert, neu laden zeigt sie: ','Your functions were changed, reload shows them: '))}
async function verCheck(){if(!SPARK_VER)return;if(verWatch.newer)return verTry();
  try{const r=await fetch('/api/whoami',{cache:'no-store'});if(!r.ok)return;const w=await r.json(),v=w.version;
    if(v&&v!==SPARK_VER){verWatch.newer=v;verTry()}else flagsAway(w)}catch{}}
setInterval(verCheck,60e3);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){verWatch.back=Date.now();verCheck()}});
window.addEventListener('pageshow',e=>{if(e.persisted){verWatch.back=Date.now();verCheck()}});
window.addEventListener('focus',()=>{verWatch.back=Date.now();verCheck()});
// Theme button: system -> light -> dark -> system; kept per browser.
$('themebtn').onclick=()=>{const cur=document.documentElement.dataset.theme||'auto',nx={auto:'light',light:'dark',dark:'auto'}[cur];
  if(nx==='auto')delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=nx;
  try{localStorage.setItem('theme',nx)}catch{}
  $('themebtn').title={auto:t('Farbschema: wie das System','Theme: follow the system'),light:t('Farbschema: hell','Theme: light'),dark:t('Farbschema: dunkel','Theme: dark')}[nx]};
// What went wrong, as a plain sentence in the page's language (B2 of the review of 11.10.2026): a FastAPI 422 list
// names the fields (never "[object Object]"), short technical answers become sentences, the panel's German
// sentences come out in English from the EN table, and a page that is no answer of the panel (a proxy, a crash)
// says only what kind of error it was. The panel's own words stay in e.detail for the checks of the callers.
const ERR_PLAIN=[[/^(too large|too big)$/i,'Das ist zu groß.','That is too large.'],
  [/^folder name: 1 to 40/,'Ordnername: 1 bis 40 Buchstaben oder Ziffern (auch Leerzeichen . , & ( ) + \' -), kein / und keine anderen Zeichen.','Folder name: 1 to 40 letters or digits (also space . , & ( ) + \' -), no / or other marks.'],
  [/^'.*' is a folder of the mail program$/,'Diesen Namen hat schon ein Ordner des Mailprogramms (Posteingang, Gesendet, Papierkorb …). Bitte einen anderen wählen.','A folder of the mail program already has this name (inbox, sent, trash …). Please pick another.'],
  [/^at most \d+ own folders$/,'Es gibt schon 20 eigene Ordner. Bitte erst einen entfernen.','There are 20 own folders already. Please remove one first.'],
  [/^only folders you added yourself can be removed$/,'Nur selbst angelegte Ordner lassen sich entfernen.','Only folders you added yourself can be removed.'],
  [/^(invalid JSON|not JSON|JSON (object )?expected)$/i,'Die Anfrage kam nicht vollständig an. Bitte die Seite neu laden und noch einmal versuchen.','The request did not arrive complete. Please reload the page and try again.'],
  [/^(not found|no such [a-z ]+|unknown [a-z ]+)$/i,'Nicht gefunden, vielleicht schon gelöscht. Bitte die Seite neu laden.','Not found, maybe deleted already. Please reload the page.'],
  [/^(login required|no profile)$/i,'Bitte zuerst anmelden.','Please sign in first.'],
  [/^wrong code$/i,'Der Code stimmt nicht. Bitte den nächsten Code versuchen.','The code is wrong. Please try the next code.'],
  [/^code required$/i,'Dafür braucht es deinen Code aus der Authenticator-App.','This needs your code from the authenticator app.'],
  [/^too many requests/i,'Zu viele Anfragen in kurzer Zeit. Bitte einen Moment warten.','Too many requests in a short time. Please wait a moment.'],
  [/^the assistant is busy/i,'Der Assistent ist gerade beschäftigt. Bitte gleich noch einmal.','The assistant is busy right now. Please try again in a moment.'],
  [/not reachable/i,'Der Dienst ist gerade nicht erreichbar. Bitte Adresse und Netz prüfen.','The service cannot be reached right now. Please check the address and the network.'],
  [/rejects? the (user name or password|token)|rejected the token/i,'Benutzername, Passwort oder Token werden abgelehnt.','The user name, password or token is refused.'],
  [/^[a-z][\w ]* (are|is) turned off\b/i,'Diese Funktion ist ausgeschaltet (Funktionen bzw. Ich).','This function is switched off (Features or Me).']];
function errSay(status,d,raw){
  if(Array.isArray(d)){const f=[...new Set(d.map(x=>x&&Array.isArray(x.loc)?x.loc.filter(k=>typeof k==='string'&&k!=='body').pop():'').filter(Boolean))];
    return f.length?t('Diese Angabe fehlt oder passt nicht: ','This entry is missing or does not fit: ')+f.join(', '):t('Die Eingabe passt nicht.','The input does not fit.')}
  if(d&&typeof d==='object')d=d.message||d.why||d.detail||'';
  d=typeof d==='string'?d.trim():'';
  if(!d||d===raw&&/<|^\s*$/.test(raw)||d.length>400){
    return status===413?t('Das ist zu groß.','That is too large.'):status===429?t('Zu viele Anfragen in kurzer Zeit. Bitte einen Moment warten.','Too many requests in a short time. Please wait a moment.')
      :status>=502&&status<=504?t('Der Spark antwortet gerade nicht. Bitte gleich noch einmal.','The Spark is not answering right now. Please try again in a moment.')
      :status>=500?t('Auf dem Spark ist ein Fehler passiert. Bitte später noch einmal.','An error happened on the Spark. Please try again later.'):t('Ging nicht (Fehler ','Did not work (error ')+status+').'}
  let m=/^too many wrong attempts, try again in (.+)$/.exec(d);
  if(m)return t('Zu viele falsche Versuche. Wieder möglich in ','Too many wrong attempts. Possible again in ')+m[1]+'.';
  m=/^restore failed: (.+)$/.exec(d);
  if(m)return t('Wiederherstellen ging nicht: ','Restore failed: ')+m[1];
  for(const [re,de,en] of ERR_PLAIN)if(re.test(d))return t(de,en);
  return L==='en'&&typeof EN!=='undefined'&&EN[d]||d}
const errRaw=e=>String(e&&(e.detail!==undefined?e.detail:e.message)||'');
// 428: the change needs a current code from the authenticator app (second login step); asked here, then sent again.
// With a passkey (passkey.py) the 428 answer carries its challenge; confirmAsk (mfa.js) offers it next to the code.
const api=async(p,o={},code)=>{const hd=!code?null:typeof code==='string'?{'X-Speech-Code':code}:{'X-Speech-Passkey':code.pk};
  // window.lzFetch (laden.js): the loading bar on top, 30 s at most for a read, the band when the Spark is gone
  const r=await (window.lzFetch||fetch)(p,hd?Object.assign({},o,{headers:Object.assign({},o.headers||{},hd)}):o);
  if(r.status===428){const wrong=/wrong/.test(await r.text());let opt=null;
    const b64j=h=>JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(h.replace(/-/g,'+').replace(/_/g,'/')+'==='.slice((h.length+3)%4)),c=>c.charCodeAt(0))));
    try{const h=r.headers.get('X-Speech-Passkey-Options');if(h)opt=b64j(h)}catch{}
    let info=null;try{const h=r.headers.get('X-Speech-Confirm');if(h)info=b64j(h)}catch{}   // whose code, what for, how long (stufen.py)
    const a=window.confirmAsk?await confirmAsk(wrong,opt,info):null;
    if(a){const r2=await api(p,o,a.code||{pk:a.pk});if(window.confirmRefresh)confirmRefresh();return r2}throw new Error(t('Abgebrochen: ohne Code keine Änderung.','Cancelled: no change without a code.'))}
  if(r.status===503&&window.notausLoad)notausLoad();   // the Notaus holds this off: band and page show it (notaus.js)
  if(r.status===401&&!/^\/api\/(login|password|profile)/.test(p)&&window.showLogin){if(typeof elevated==='function'&&elevated()){location.reload();return r}showLogin()}if(!r.ok){const raw=await r.text();let d=raw;try{d=JSON.parse(raw).detail??raw}catch{}
    const e=new Error(errSay(r.status,d,raw));e.detail=typeof d==='string'?d:JSON.stringify(d);e.status=r.status;throw e}
  if(o.method&&o.method!=='GET'&&/^\/api\/(config|admin\/|profile\/)/.test(p)&&!/^\/api\/profile\/(setup|handoff)/.test(p))whoSoon();   // a switch may have changed
  return r};
// like fetch(...) plus .json(), but with api()'s code prompt (428): {r, d}; errors come back as d.detail
const apiTry=async(p,o)=>{try{const r=await api(p,o);return {r,d:await r.json()}}catch(e){return {r:{ok:false,status:0},d:{detail:e.message}}}};
// Main menu (design „Klar“, V01.0.145; plan „Bedienung gesamt“ V01.0.265): on a computer a sidebar with the search
// (Strg K), Assistent and Ich for oneself, then "Spark verwalten" with Zustand, Funktionen, Personen und Geräte,
// Einstellungen; on phones a bar at the bottom. Einbinden is gone: Anleitungen sit under Funktionen, Apps und
// Schnittstellen under Personen und Geräte.
const NI={chat:'<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  chats:'<path d="M17 9h2a2 2 0 0 1 2 2v9l-3-3h-7a2 2 0 0 1-2-2v-1"/><path d="M15 4H5a2 2 0 0 0-2 2v9l3-3h9a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2z"/>',me:'<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
  mon:'<path d="M3 12h4l3 7 4-14 3 7h4"/>',cfg:'<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
  prof:'<circle cx="9" cy="8" r="3.5"/><path d="M2 20c0-3.5 3-5.5 7-5.5s7 2 7 5.5M16 4.5a3.5 3.5 0 0 1 0 7M18 14.8c2.4.6 4 2.4 4 5.2"/>',int:'<path d="M9 2v5M15 2v5M6 7h12v4a6 6 0 0 1-12 0zM12 17v5"/>',
  feat:'<rect x="3" y="4" width="18" height="6" rx="3"/><circle cx="16" cy="7" r="1.6"/><rect x="3" y="14" width="18" height="6" rx="3"/><circle cx="8" cy="17" r="1.6"/>',
  more:'<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>'};
document.querySelectorAll('i.ni').forEach(e=>e.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'+(NI[e.dataset.ni]||'')+'</svg>');
// the phone bar marks the page that is open (Ich while its window is open, else the section's menu entry)
function mbarMark(g){document.querySelectorAll('#mbar button').forEach(x=>x.classList.toggle('on',x.dataset.m===({chat:'chat',chats:'chats',mon:'mon',me:'me'}[g]||'more')))}
// Main menu: Zustand, Funktionen and Personen und Geräte hold several pages behind a sub-tab bar. Funktionen is the
// page "feat" of the settings form (saved with it), shown alone without the settings menu (class featmode).
const GROUPS={chat:[['chat','']],chats:[['chats','']],mon:[['mon',t('Monitoring','Monitoring')],['live',t('Live','Live')],['test',t('Prüfen','Checks')],['logs',t('Logs','Logs')],['verb',t('Verbessern','Improve')],['usage',t('Verbrauch','Usage')],['models',t('Modelle','Models')],['tech',t('Technik','Architecture')]],
  feat:[['feat',t('Funktionen','Features')],['route',t('Weiche','Switch')],['int',t('Anleitungen','Guides')]],
  prof:[['prof',t('Personen und Geräte','People and devices')],['apps',t('Apps und Schnittstellen','Apps and interfaces')]],cfg:[['cfg','']]};
const lastSec={};
// Seiten sichtbar laden (laden.js): what a page loads when it is opened shows placeholders, „wird aktualisiert …“,
// „dauert länger als sonst …“ or its error in the page itself. The settings form keeps its fields (no placeholders).
// a short line at the bottom of the page (update finished, saved, reloaded); a newer one replaces it
function sayToast(text,ms){const e=$('updtoast');if(!e)return;e.textContent=text;e.style.display='block';clearTimeout(sayToast.t);sayToast.t=setTimeout(()=>e.style.display='none',ms||4000)}
// writes HTML only when it differs from what this place shows (polled tables: marking, focus and hover stay)
function setHtml(el,h){if(el&&el._h!==h){el.innerHTML=h;el._h=h}}
const lzb=(box,load,o)=>window.ladeBox?ladeBox(box,load,o):load();
const LZ_CFG={skel:false,stale:false,top:true};
function showSec(s){const sec=s==='feat'?'cfg':s;document.querySelectorAll('section').forEach(x=>x.classList.toggle('on',x.id===sec));
  document.body.classList.toggle('inchat',s==='chat');if(s!=='tech'&&window.tkFull)tkFull(false);document.body.classList.toggle('inchats',s==='chats');
  const cw=document.querySelector('.cfgwrap');cw.classList.toggle('featmode',s==='feat');
  if(s==='feat'){cw.classList.add('sub');lzb($('cfg'),loadCfg,LZ_CFG);if(typeof cfgPane==='function')cfgPane('feat')}
  if(s==='cfg'&&$('pane-feat').classList.contains('on')&&typeof cfgPane==='function')cfgPane('start');
  if(s==='cfg'){cw.classList.remove('sub');lzb($('cfg'),loadCfg,LZ_CFG);mfaShow('admmfa','/api/mfa');if($('pane-voices').classList.contains('on'))loadClone();if($('pane-upd').classList.contains('on')||$('pane-bak').classList.contains('on'))loadSys()}if(s==='chat')chatTab();if(s==='test'){loadVoices();instrHint();loadLive();loadBench();loadVorrang();musikTestLoad();if(typeof sprAdmin==='function')sprAdmin()}if(s==='prof'){lzb($('proflist'),loadProf,{form:'tabelle'});if(window.loadWho)lzb($('whobox'),loadWho);if(typeof joinAdmin==='function')joinAdmin()}if(s==='logs')lzb($('logout'),loadLogs);if(s==='live'&&window.liveOpen){if(window.lzSkelIn)lzSkelIn($('lvroot'),'karten',4);liveOpen()}if(s==='apps'){lzb($('int-ep'),loadInt,{form:'tabelle'});if(window.appTiles)appTiles();if(typeof loadMcpAdmin==='function')loadMcpAdmin();if(typeof loadMyMcpAdmin==='function')loadMyMcpAdmin()}if(s==='route'&&window.loadWeiche)lzb($('whbox'),loadWeiche,{at:$('whlist')});if(s==='verb'&&window.loadVerb)loadVerb();if(s==='usage'&&window.loadUsage)lzb($('usgbox'),loadUsage);if(s==='models'&&window.loadModelle)lzb($('mdbox'),loadModelle);if(s==='tech'&&window.loadTechnik)lzb($('tkview'),loadTechnik);if(window.cxShown)cxShown(s==='chats')}
// Zustand, Funktionen and Personen und Geräte have several pages: computers show them as a second column like Einstellungen, phones as a
// list with one line of state that opens the page, with "back" on top (V01.0.207, same pattern everywhere)
const NARROW=()=>matchMedia('(max-width:760px)').matches;
const SUBDESC={mon:()=>($('ztitle')||{}).textContent||'',test:()=>t('Funktionsprüfung, Qualitätstest, Leistung messen, ausprobieren','Function check, quality test, performance, try out'),
  live:()=>t('Wer gerade fragt, welchen Weg die Anfrage nimmt, was der Wächter entscheidet','Who is asking, which way the request takes, what the guard decides'),
  logs:()=>t('Was die Dienste schreiben, mit Diagnose-Filter','What the services write, with diagnosis filter'),
  verb:()=>t('Fälle, Vorschläge und Nachkontrolle des Einstellungs-Assistenten','Cases, proposals and re-check of the settings assistant'),
  usage:()=>t('Tokens und Sekunden je Modell, Bereich und Profil','Tokens and seconds per model, area and profile'),models:()=>t('Katalog, laufende Modelle, Speicher-Budget, Messung','Catalog, running models, memory budget, measurement'),int:()=>t('Zu jedem Dienst: einrichten, benutzen, ausschalten','For every service: set up, use, switch off'),
  feat:()=>t('Was der Assistent können soll, für den Spark und jedes Profil','What the assistant may do, for the Spark and each profile'),
  route:()=>t('Welche Werkzeuge eine Frage bekommt, mit Testsätzen','Which tools a question gets, with test sentences'),
  prof:()=>t('Profile, Gäste und Geräte mit Schlüssel','Profiles, guests and devices with a key'),
  apps:()=>t('Open WebUI, andere Apps, Pebble, Siri, curl und Python','Open WebUI, other apps, Pebble, Siri, curl and Python')};
const GNAME={mon:t('Zustand','Status'),feat:t('Funktionen','Features'),prof:t('Personen und Geräte','People and devices')};
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
// One row for every setting (plan „Vereinheitlichen“ Phase 4, V01.0.270): label, one sentence, the control on the
// right. l, h and ctl are HTML (callers escape). A locked row stays visible with its reason (o.why, from the panel's
// rules in features.py, never from the model) and a disabled control; o.extra goes below the sentence.
const setRow=(l,h,ctl,o={})=>{if(o.why)ctl=ctl.replace(/<(input|select|textarea)\b/g,'<$1 disabled');
  return `<div class="setrow${o.why?' locked':''}"><div class="lbl"><b>${l}</b>${h||o.why?`<span>${h||''}${o.why?`<em class="why">${esc(o.why)}</em>`:''}</span>`:''}${o.extra||''}</div>${ctl}</div>`};
// Every field of a settings row has a name for screen readers (B6 of the review of 11.10.2026): a control after the
// row's title without a label of its own (a switch's label.tgl has no text) gets the title's words as aria-label.
// Rows come from index.html and from the scripts, so this follows the page (once per frame at most).
function rowLabels(){document.querySelectorAll('.setrow').forEach(r=>{const b=r.querySelector(':scope>.lbl>b');if(!b)return;
  const c=[...r.querySelectorAll('input:not([type=hidden]),select,textarea')].find(x=>!x.closest('.lbl'));
  if(!c||c.hasAttribute('aria-label')||c.hasAttribute('aria-labelledby')||[...(c.labels||[])].some(x=>x.textContent.trim()))return;
  const name=[...b.childNodes].filter(n=>n.nodeType===3).map(n=>n.nodeValue).join('').trim();if(name)c.setAttribute('aria-label',name)})}
{let q=0;const later=()=>{if(!q)q=requestAnimationFrame(()=>{q=0;rowLabels()})};later();
 new MutationObserver(later).observe(document.body,{childList:true,subtree:true})}
const tglIn=(attrs,on)=>`<label class="tgl"><input type="checkbox" ${attrs}${on?' checked':''}><i></i></label>`;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
// Strict CSP (plan „Bedienung gesamt“ D1 Stufe 2, V01.0.286): no inline handlers. A generated button names a function
// of ON and its arguments, data-on="bakDel" data-args="[…]" (JSON through esc, so a name with ' or " stays text);
// one listener calls it with the button first. Only functions put into ON can be called this way.
const ON=Object.create(null);
const onAttr=(name,...args)=>`data-on="${esc(name)}" data-args="${esc(JSON.stringify(args))}"`;
document.addEventListener('click',e=>{const b=e.target.closest('[data-on]');if(!b||b.disabled||typeof ON[b.dataset.on]!=='function')return;
  let a;try{a=JSON.parse(b.dataset.args||'[]')}catch{return}if(Array.isArray(a))ON[b.dataset.on](b,...a)});
const pill=(s)=>{const c={active:'ok',ready:'ok',loading:'warn',activating:'warn',blocked:'bad',error:'bad',failed:'bad'}[s]||'';return `<span class="pill ${c}">${esc(s)}</span>`};
// The panel runs on plain http in the LAN, where navigator.clipboard is not available.
// navigator.clipboard needs https or localhost; the panel is usually plain http on the LAN,
// so there the copy event gets the text directly (copying a selection is unreliable)
function copyString(text,btn){const label=btn.textContent;const done=ok=>{btn.textContent=ok?t('kopiert','copied'):t('Markiert, jetzt Strg+C','Selected, now press Ctrl+C');setTimeout(()=>btn.textContent=label,2000)};
  if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(text).then(()=>done(true),()=>done(false));return true}
  const onCopy=e=>{e.clipboardData.setData('text/plain',text);e.preventDefault()};
  document.addEventListener('copy',onCopy);let ok=false;try{ok=document.execCommand('copy')}catch{}document.removeEventListener('copy',onCopy);
  done(ok);return ok}
function copyEl(id,btn){const el=$(id);if(!copyString(el.innerText||el.textContent,btn)){
  const sel=window.getSelection(),r=document.createRange();r.selectNodeContents(el);sel.removeAllRanges();sel.addRange(r)}}
window.copyString=copyString;window.copyEl=copyEl;
ON.copyEl=(b,id)=>copyEl(id,b);ON.findClose=()=>{$('findmodal').style.display='none'};
const fmt=(v,u='',d=0)=>v==null?'–':(+v).toFixed(d)+u;

function spark(svg,vals,max){const w=300,h=60;svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('preserveAspectRatio','none');
  const v=vals.filter(x=>x!=null);if(v.length<2){svg.innerHTML='';return}
  const m=max??(Math.max(...v)*1.1||1);const pts=vals.map((x,i)=>x==null?null:[i*w/(vals.length-1),h-2-(x/m)*(h-4)]).filter(Boolean);
  const d='M'+pts.map(p=>p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' L');
  svg.innerHTML=`<path d="${d} L${w} ${h} L0 ${h}Z" fill="var(--acc)" opacity=".12"/><path d="${d}" fill="none" stroke="var(--acc)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;}
