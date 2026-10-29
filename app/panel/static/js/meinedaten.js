// Ich → Sicherheit → Meine Daten (meinedaten.py, plan nutzerwissen Punkt 5, Dominik 2026-10-29): „Alle meine Daten
// herunterladen“. The areas with count and size (each can be left out), what stays out with the register's reason,
// then one ZIP after a fresh code (api() asks it, 428), without a second step after the PIN. The answer is a one-time
// pickup link (10 minutes, once); the browser follows it, the Android app hands it to its download manager. Names and
// reasons come from the Spark and are shown through textContent only.
const MD={d:null};
function mdSize(n){n=+n||0;return n>=1e9?(n/1e9).toFixed(1)+' GB':n>=1e6?Math.round(n/1e6)+' MB':n>=1e3?Math.round(n/1e3)+' KB':n+' B'}
function mdPick(x){return L==='en'?x[1]:x[0]}
async function mdLoad(){const {r,d}=await apiTry('/api/profile/export');if(!r.ok){$('mydmsg').textContent=d.detail||'';return}
  MD.d=d;const ul=$('mydareas');ul.textContent='';
  for(const a of d.bereiche){const li=icEl('li'),lab=icEl('label','md-a'),cb=document.createElement('input');cb.type='checkbox';cb.checked=a.dateien>0;cb.disabled=!a.dateien;cb.dataset.md=a.id;
    lab.append(cb,icEl('span','',' '+mdPick(a.name)+' '),icEl('small','mut',a.dateien?a.dateien+' '+(a.dateien===1?t('Datei','file'):t('Dateien','files'))+(a.bytes?' · '+mdSize(a.bytes):''):t('leer','empty')));
    li.appendChild(lab);ul.appendChild(li)}
  const out=$('mydoutlist');out.textContent='';
  for(const x of d.draussen){const li=icEl('li'),sp=icEl('span','',mdPick(x.was));sp.append(document.createElement('br'),icEl('small','mut',mdPick(x.grund)));li.appendChild(sp);out.appendChild(li)}
  $('mydpinrow').hidden=!!d.code;$('mydbox').hidden=false;mdSum()}
function mdSum(){if(!MD.d)return;const off=new Set([...document.querySelectorAll('#mydareas input[data-md]')].filter(c=>!c.checked).map(c=>c.dataset.md));
  const sum=MD.d.bereiche.filter(a=>!off.has(a.id)).reduce((s,a)=>s+a.bytes,0);
  $('mydmsg').textContent=t('Zusammen etwa ','Together about ')+mdSize(sum)+(sum>MD.d.grenze?t(' – zu groß, bitte Bereiche abwählen',' – too big, please leave areas out'):'');
  $('mydgo').disabled=sum>MD.d.grenze;return off}
$('mydopen')&&($('mydopen').onclick=()=>{if($('mydbox').hidden)mdLoad();else $('mydbox').hidden=true});
$('mydareas')&&$('mydareas').addEventListener('change',mdSum);
$('mydgo')&&($('mydgo').onclick=async()=>{const off=mdSum()||new Set(),b=$('mydgo');b.disabled=true;$('mydmsg').textContent=t('Packt …','Packing …');
  try{const d=await (await api('/api/profile/export',xjson('POST',{ohne:[...off],pin:$('mydpin').value||undefined}))).json();$('mydpin').value='';
    $('mydmsg').textContent=t('Fertig: ','Done: ')+d.dateien+t(' Dateien, ',' files, ')+mdSize(d.bytes)+t('. Der Download startet.','. The download starts.');
    const a=document.createElement('a');a.href=d.url;a.download='';a.rel='noopener';document.body.appendChild(a);a.click();a.remove()}
  catch(e){$('mydpin').value='';$('mydmsg').textContent=e.message}
  b.disabled=false});
