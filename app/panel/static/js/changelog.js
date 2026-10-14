// "Was ist neu": the changelog of the installed version (GET /api/changelog, one line per version, newest first).
// Opens from the version line at the bottom and from Einstellungen → Update. Text only (esc), never HTML from the file.
// Lines newer than the version this browser saw last carry "neu" (localStorage "clseen", only a convenience).
const CL={data:null,shown:60,seen:null};
const clNum=v=>{const m=/^V(\d+)\.(\d+)\.(\d+)$/.exec(v||'');return m?[+m[1],+m[2],+m[3]]:null};
const clNewer=(a,b)=>{const x=clNum(a),y=clNum(b);if(!x||!y)return false;for(let i=0;i<3;i++)if(x[i]!==y[i])return x[i]>y[i];return false};
const clDate=d=>{const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(d||'');return m?(L==='en'?d:`${m[3]}.${m[2]}.${m[1]}`):''};
function clRender(){const list=$('cllist'),info=$('clinfo'),more=$('clmore'),d=CL.data;if(!d)return;
  const q=$('clq').value.trim().toLowerCase(),words=q.split(/\s+/).filter(Boolean);
  const hits=words.length?d.entries.filter(e=>words.every(w=>((e.version||'')+' '+e.date+' '+e.text).toLowerCase().includes(w))):d.entries;
  const n=words.length?Math.min(hits.length,200):Math.min(hits.length,CL.shown);
  let day=null;list.innerHTML=hits.slice(0,n).map(e=>{const head=e.date!==day?`<li class="cld">${esc(clDate(e.date))}</li>`:'';day=e.date;
    const isNew=CL.seen&&e.version&&clNewer(e.version,CL.seen);
    return head+`<li><span>${e.version?`<b>${esc(e.version)}</b> `:''}${isNew?`<em class="pill ok">${esc(t('neu','new'))}</em> `:''}${esc(e.text)}</span></li>`}).join('')
    ||`<li class="mut">${esc(words.length?t('Nichts gefunden.','Nothing found.'):t('Kein Changelog vorhanden.','No changelog available.'))}</li>`;
  more.hidden=!!words.length||n>=hits.length;
  info.textContent=t(`Installiert: ${d.version||'–'} · ${d.entries.length} Einträge`,`Installed: ${d.version||'–'} · ${d.entries.length} entries`)+
    (words.length?t(` · ${hits.length} gefunden`,` · ${hits.length} found`):'')}
async function clOpen(){if(typeof closeSheet==='function')closeSheet();$('clmodal').style.display='grid';$('clq').value='';CL.shown=60;
  if(!CL.data){$('cllist').innerHTML=`<li class="mut">${esc(t('Lädt …','Loading …'))}</li>`;$('clinfo').textContent='';$('clmore').hidden=true;
    try{const r=await /*raw: a guest gets a hint here, not the login*/fetch('/api/changelog',{cache:'no-store'});
      if(r.status===401||r.status===403)throw new Error(t('Zum Ansehen bitte mit deinem Profil anmelden.','Please sign in with your profile to see it.'));
      if(!r.ok)throw new Error(t('Changelog gerade nicht abrufbar.','Changelog not available right now.'));
      const d=await r.json();if(!d||!Array.isArray(d.entries))throw new Error(t('Changelog nicht lesbar.','Changelog not readable.'));CL.data=d}
    catch(x){$('cllist').innerHTML=`<li class="err">${esc(x.message)}</li>`;return}}
  if(CL.seen===null)try{CL.seen=localStorage.getItem('clseen')||''}catch{CL.seen=''}
  clRender();try{if(CL.data.version)localStorage.setItem('clseen',CL.data.version)}catch{}
  setTimeout(()=>$('clq').focus(),50)}
function clClose(){$('clmodal').style.display='none'}
ON.clOpen=()=>clOpen();ON.clClose=()=>clClose();ON.clMore=()=>{CL.shown+=200;clRender()};
$('clq').oninput=clRender;
$('clq').onkeydown=e=>{if(e.key==='Escape')clClose()};
$('clmodal').addEventListener('click',e=>{if(e.target===$('clmodal'))clClose()});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('clmodal').style.display==='grid')clClose()});
