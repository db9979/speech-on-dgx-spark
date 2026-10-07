// Shared helpers: theme, API calls, main menu, copying, small formatters.
// Installable as an app ("Add to home screen"); the service worker caches nothing.
if('serviceWorker' in navigator&&window.isSecureContext)navigator.serviceWorker.register('/sw.js').catch(()=>{}).catch(()=>{});
// Theme button: system -> light -> dark -> system; kept per browser.
$('themebtn').onclick=()=>{const cur=document.documentElement.dataset.theme||'auto',nx={auto:'light',light:'dark',dark:'auto'}[cur];
  if(nx==='auto')delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=nx;
  try{localStorage.setItem('theme',nx)}catch{}
  $('themebtn').title={auto:t('Farbschema: wie das System','Theme: follow the system'),light:t('Farbschema: hell','Theme: light'),dark:t('Farbschema: dunkel','Theme: dark')}[nx]};
const api=async(p,o={})=>{const r=await fetch(p,o);if(r.status===401&&!/^\/api\/(login|password|profile)/.test(p)&&window.showLogin)showLogin();if(!r.ok){let t=await r.text();try{t=JSON.parse(t).detail||t}catch{}throw new Error(t)}return r};
// Main menu: five entries; Übersicht, Nutzer and Einbinden hold several pages behind a sub-tab bar.
const GROUPS={chat:[['chat','']],mon:[['mon',t('Monitoring','Monitoring')],['sys',t('System und Update','System and update')],['logs',t('Logs','Logs')]],
  cfg:[['cfg','']],prof:[['prof',t('Profile und Geräte','Profiles and devices')],['voices',t('Stimmen','Voices')]],int:[['int',t('Anleitungen','Guides')],['test',t('Testen','Test')]]};
const lastSec={};
function showSec(s){document.querySelectorAll('section').forEach(x=>x.classList.toggle('on',x.id===s));
  document.body.classList.toggle('inchat',s==='chat');
  if(s==='cfg')loadCfg();if(s==='chat')chatTab();if(s==='test'){loadVoices();instrHint()}if(s==='voices')loadClone();if(s==='prof')loadProf();if(s==='logs')loadLogs();if(s==='int')loadInt();if(s==='sys')loadSys()}
function subnav(g,s){const items=GROUPS[g],bar=$('subnav');bar.hidden=items.length<2;
  bar.innerHTML=items.length<2?'':items.map(([id,l])=>`<button type="button" data-sub="${id}"${id===s?' class="on"':''}>${esc(l)}${id==='sys'?' <span class="pill warn subbadge" style="display:none">Update</span>':''}</button>`).join('');
  bar.querySelectorAll('button').forEach(b=>b.onclick=()=>{lastSec[g]=b.dataset.sub;subnav(g,b.dataset.sub);showSec(b.dataset.sub)});updBadge(window.UPD)}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{const g=b.dataset.s,s=lastSec[g]||g;
  document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('on',x===b));subnav(g,s);showSec(s)});
window.goSec=s=>{const g=Object.keys(GROUPS).find(k=>GROUPS[k].some(x=>x[0]===s));lastSec[g]=s;document.querySelector(`nav button[data-s=${g}]`).click()};
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
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
