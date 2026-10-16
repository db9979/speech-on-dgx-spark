// Gehäuse (gehaeuse.py, plan Raspberry-Pi split B7): Funktionen → Gehäuse, the case of the panel computer. The settings
// are saved like every switch; "Einrichten", "Entfernen" and "Neu starten" leave a wish for the fixed root unit and ask
// for the code. The line below shows what the Pi reports: set up, restart needed, display and LEDs (words only).
function gehShow(d){const m=$('gehmsg');if(!m)return;
  const w={an:t('an','on'),aus:t('aus','off'),fehlt:t('nicht gefunden','not found'),fehler:t('Fehler','error')};
  m.textContent=!d.pi?t('Kein Raspberry Pi: hier gibt es nichts einzurichten.','Not a Raspberry Pi: nothing to set up here.')
    :[d.eingerichtet?t('Eingerichtet','Set up'):t('Nicht eingerichtet','Not set up'),
      d.neustart?t('Neustart nötig','Restart needed'):'',
      t('Display ','Display ')+(w[d.oled]||d.oled)+(d.addr?' ('+d.addr+')':''),t('LEDs ','LEDs ')+(w[d.led]||d.led)].filter(Boolean).join(' · ');
  $('gehein').disabled=!d.pi;$('gehaus').disabled=!d.pi||!d.eingerichtet;$('gehneu').hidden=!d.neustart}
async function gehLoad(){if(!$('gehbox')||document.body.classList.contains('mgr'))return;
  try{gehShow(await (await api('/api/admin/gehaeuse')).json())}catch{}gehVor()}
// B7b: the pages as small pictures (drawn by gehaeuse.vorschau exactly as on the display, upright), a tap switches
// one on or off, dragging or ◀ ▶ changes the order; both only fill the two hidden fields, "Speichern" saves them.
// The big picture shows what the display shows now. Refreshed every 5 s while the block is on the screen.
const GEH={d:null,timer:0,drag:''};
const gehList=id=>$(id).value.split(/[\s,;]+/).filter(Boolean);
function gehSet(id,v){$(id).value=v.join(', ');$(id).dispatchEvent(new Event('input',{bubbles:true}))}
function gehDraw(cv,b64,w,h){const x=cv.getContext('2d'),img=x.createImageData(w,h);let raw='';try{raw=atob(b64||'')}catch{}
  for(let y=0;y<h;y++)for(let i=0;i<w;i++){const byte=raw.charCodeAt(y*(w>>3)+(i>>3))||0,on=byte>>(7-(i&7))&1,p=(y*w+i)*4;
    img.data[p]=img.data[p+1]=img.data[p+2]=on?235:0;img.data[p+3]=255}
  if(cv.width!==w){const tmp=document.createElement('canvas');tmp.width=w;tmp.height=h;tmp.getContext('2d').putImageData(img,0,0);
    x.imageSmoothingEnabled=false;x.clearRect(0,0,cv.width,cv.height);x.drawImage(tmp,0,0,cv.width,cv.height)}else x.putImageData(img,0,0)}
function gehOrder(){const all=(GEH.d?.seiten||[]).map(p=>p.id),f=gehList('chat.gehaeuse_reihenfolge').filter(k=>all.includes(k));
  return [...new Set(f),...all.filter(k=>!f.includes(k))]}
function gehMove(k,to){const o=gehOrder().filter(x=>x!==k);o.splice(Math.max(0,Math.min(o.length,to)),0,k);gehSet('chat.gehaeuse_reihenfolge',o);gehRender()}
function gehToggle(k){const off=gehList('chat.gehaeuse_seiten_aus'),n=(GEH.d?.seiten||[]).length;
  if(off.includes(k))gehSet('chat.gehaeuse_seiten_aus',off.filter(x=>x!==k));
  else if(off.length+1<n)gehSet('chat.gehaeuse_seiten_aus',[...off,k]);
  else{$('gehjetztt').textContent=t('Mindestens eine Seite bleibt an.','At least one page stays on.');return}
  gehRender()}
function gehRender(){const box=$('gehvor'),d=GEH.d;if(!box||!d)return;const off=gehList('chat.gehaeuse_seiten_aus'),by=Object.fromEntries(d.seiten.map(p=>[p.id,p]));
  box.textContent='';gehOrder().forEach((k,i,o)=>{const p=by[k];if(!p)return;const on=!off.includes(k),el=document.createElement('div');
    el.className='gehtile'+(on?' on':'')+(d.jetzt===k?' now':'');el.draggable=true;el.dataset.k=k;el.tabIndex=0;el.setAttribute('role','button');el.setAttribute('aria-pressed',on);
    const cv=document.createElement('canvas');cv.width=d.w;cv.height=d.h;gehDraw(cv,p.bits,d.w,d.h);el.appendChild(cv);
    const cap=document.createElement('div');cap.className='gehcap';const nm=document.createElement('span');nm.textContent=(i+1)+'. '+(L==='en'?p.name[1]:p.name[0])+' · '+(on?t('an','on'):t('aus','off'));
    const l=document.createElement('button');l.type='button';l.textContent='◀';l.title=t('Weiter nach vorn','Move forward');l.disabled=i===0;
    const r=document.createElement('button');r.type='button';r.textContent='▶';r.title=t('Weiter nach hinten','Move back');r.disabled=i===o.length-1;
    l.onclick=e=>{e.stopPropagation();gehMove(k,i-1)};r.onclick=e=>{e.stopPropagation();gehMove(k,i+1)};
    cap.append(l,nm,r);el.appendChild(cap);
    el.onclick=()=>gehToggle(k);el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();gehToggle(k)}};
    el.ondragstart=e=>{GEH.drag=k;el.classList.add('drag');try{e.dataTransfer.setData('text/plain',k)}catch{}};el.ondragend=()=>el.classList.remove('drag');
    el.ondragover=e=>e.preventDefault();el.ondrop=e=>{e.preventDefault();if(GEH.drag&&GEH.drag!==k)gehMove(GEH.drag,gehOrder().indexOf(k));GEH.drag=''};
    box.appendChild(el)});
  const cv=$('gehjetztc');gehDraw(cv,d.jetzt_bits,d.w,d.h);
  $('gehjetztt').textContent=d.jetzt?t('Jetzt am Display: ','On the display now: ')+(L==='en'?by[d.jetzt]?.name[1]:by[d.jetzt]?.name[0]||d.jetzt)
    :d.dunkel?t('Das Display ist gerade dunkel (Nacht oder „nur bei Problemen“).','The display is dark right now (night or "only on problems").')
    :t('Das Display zeigt gerade nichts (aus, nicht gefunden oder noch nicht eingerichtet).','The display shows nothing right now (off, not found or not set up yet).')}
async function gehVor(){clearTimeout(GEH.timer);const box=$('gehvor');if(!box||document.body.classList.contains('mgr'))return;
  if(box.offsetParent){try{GEH.d=await (await api('/api/admin/gehaeuse/vorschau')).json();gehRender()}catch{}}
  GEH.timer=setTimeout(gehVor,5000)}

const gehDo=(path,ask)=>async()=>{if(ask&&!confirm(ask))return;$('gehmsg').textContent=t('Einen Moment …','One moment …');
  try{gehShow(await (await api('/api/admin/gehaeuse/'+path,{method:'POST'})).json());setTimeout(gehLoad,4000)}catch(e){$('gehmsg').textContent=e.message}};
if($('gehein'))$('gehein').onclick=gehDo('einrichten');
if($('gehaus'))$('gehaus').onclick=gehDo('entfernen',t('Die Einträge des Gehäuses aus config.txt nehmen? Danach ist ein Neustart nötig.','Take the case entries out of config.txt? A restart is needed then.'));
if($('gehneu'))$('gehneu').onclick=gehDo('neustart',t('Den Panel-Rechner jetzt neu starten? Das Panel ist etwa eine Minute weg.','Restart the panel computer now? The panel is gone for about a minute.'));
window.gehLoad=gehLoad;
