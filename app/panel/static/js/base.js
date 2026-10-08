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
function verTry(){const now=Date.now(),calm=!sparkBusy()&&now-verWatch.edit>600e3;
  if(calm&&(document.visibilityState==='hidden'||now-verWatch.back<5000||now-verWatch.seen>120e3))return verReload();
  let b=$('verbanner');if(b)return;
  b=document.createElement('div');b.id='verbanner';b.className='updbanner';
  const sp=document.createElement('span');sp.textContent=t('Neue Version ist da: ','A new version is here: ')+verWatch.newer;
  const go=document.createElement('button');go.type='button';go.className='b p';go.textContent=t('Neu laden','Reload');go.onclick=verReload;
  b.append(sp,go);$('updbanner').before(b)}
async function verCheck(){if(!SPARK_VER)return;if(verWatch.newer)return verTry();
  try{const r=await fetch('/api/whoami',{cache:'no-store'});if(!r.ok)return;const v=(await r.json()).version;
    if(v&&v!==SPARK_VER){verWatch.newer=v;verTry()}}catch{}}
setInterval(verCheck,300e3);
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'){verWatch.back=Date.now();verCheck()}});
window.addEventListener('pageshow',e=>{if(e.persisted){verWatch.back=Date.now();verCheck()}});
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
  if(r.status===401&&!/^\/api\/(login|password|profile)/.test(p)&&window.showLogin)showLogin();if(!r.ok){let t=await r.text();try{t=JSON.parse(t).detail||t}catch{}throw new Error(t)}return r};
// Main menu: five entries; Übersicht and Einbinden hold several pages behind a sub-tab bar. The cloned voices
// are a settings page (Einstellungen → Stimmen), not under Profile.
const GROUPS={chat:[['chat','']],mon:[['mon',t('Monitoring','Monitoring')],['sys',t('System und Update','System and update')],['test',t('Prüfen','Checks')],['logs',t('Logs','Logs')]],
  cfg:[['cfg','']],prof:[['prof','']],int:[['int',t('Anleitungen','Guides')],['apps',t('Apps und Schnittstellen','Apps and interfaces')]]};
const lastSec={};
function showSec(s){document.querySelectorAll('section').forEach(x=>x.classList.toggle('on',x.id===s));
  document.body.classList.toggle('inchat',s==='chat');
  if(s==='cfg'){document.querySelector('.cfgwrap').classList.remove('sub');loadCfg();mfaShow('admmfa','/api/mfa');if($('pane-voices').classList.contains('on'))loadClone()}if(s==='chat')chatTab();if(s==='test'){loadVoices();instrHint();loadLive();loadBench()}if(s==='prof')loadProf();if(s==='logs')loadLogs();if(s==='apps')loadInt();if(s==='sys')loadSys()}
function subnav(g,s){const items=GROUPS[g],bar=$('subnav');bar.hidden=items.length<2;
  bar.innerHTML=items.length<2?'':items.map(([id,l])=>`<button type="button" data-sub="${id}"${id===s?' class="on"':''}>${esc(l)}${id==='sys'?' <span class="pill warn subbadge" style="display:none">Update</span>':''}</button>`).join('');
  bar.querySelectorAll('button').forEach(b=>b.onclick=()=>{lastSec[g]=b.dataset.sub;subnav(g,b.dataset.sub);showSec(b.dataset.sub)});updBadge(window.UPD)}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{const g=b.dataset.s,s=lastSec[g]||g;
  document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('on',x===b));subnav(g,s);showSec(s)});
window.goSec=s=>{const g=Object.keys(GROUPS).find(k=>GROUPS[k].some(x=>x[0]===s));lastSec[g]=s;document.querySelector(`nav button[data-s=${g}]`).click()};
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
