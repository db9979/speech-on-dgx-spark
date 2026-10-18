// Ich → Dokumente → Ausgelassene Ordner (auslassen.py, plan plaene/ordner-auslassen.md): folders and names the Spark
// never reads. A name counts everywhere ("Archiv", "Alt*" = begins with Alt); a folder with everything below it.
// The tree of a Wissensordner shows each sub folder with "Auslassen" / "Zulassen"; before leaving one out the page
// says how many documents leave the search. Nothing changes at the place. Server text is text (esc).
// reMarkable ("rm") and the Begleiter's folder "Spark-Wissen" ("pc") show the folders the Spark already knows
// (/api/profile/auslassen/tree), the Wissensordner ask the place itself (/api/profile/nasquelle/tree).
let AU=null,AUCUR=null,AUASK=null;
const auSay=(x,err)=>{const m=$('auslmsg');if(m){m.className=err?'err':'mut';m.textContent=String(x||'').slice(0,300)}};
const auIs=(nas,p)=>AU&&AU.folders.some(f=>f.ort===nas&&f.path===p);
async function auShow(){const box=$('auslbox');if(!box)return;
  const r=await apiTry('/api/profile/auslassen');if(!r.r.ok){box.hidden=true;return}
  AU=r.d;box.hidden=!(AU.sources.length||AU.folders.length||AU.names.length);if(box.hidden)return;
  if(AUCUR&&!AU.sources.some(s=>s.nas===AUCUR.nas))AUCUR=null;
  auDraw()}
function auDraw(){const box=$('auslin');if(!box||!AU)return;
  const names=AU.names.map(n=>`<span class="chip"><b>${esc(n)}</b> <button class="b" type="button" data-auname="${esc(n)}" aria-label="${esc(t('Regel entfernen','Remove rule'))}">✕</button></span>`).join('');
  const rows=AU.folders.map(f=>`<div class="zrow"><span class="pill">${esc(f.place||t('Ort','Place'))}</span><span><b>${esc(f.path)}</b></span><button class="b" type="button" data-auort="${esc(f.ort)}" data-aupath="${esc(f.path)}">${esc(t('Wieder zulassen','Let in again'))}</button></div>`).join('');
  const srcs=AU.sources.map((s,i)=>s.tree===false?'':`<option value="${i}">${esc((s.place?s.place+' · ':'')+s.path+(s.haus?' · '+t('Haushaltsordner','household folder'):''))}</option>`).join('');
  box.innerHTML=`<div class="intro">${esc(t('Ordner, die der Spark nie liest. Was schon gelesen war, verschwindet sofort aus der Suche, aus „Erst lokal“ und dem Wissensbuch. Am Ort ändert sich nichts; „Wieder zulassen“ liest neu.','Folders the Spark never reads. What was already read leaves the search, "Local first" and the knowledge book at once. Nothing changes at the place; "Let in again" reads anew.'))}</div>
    <h3>${esc(t('Ordnernamen, die überall ausgelassen werden','Folder names left out everywhere'))}</h3>
    <div class="chips" style="justify-content:flex-start">${names||`<span class="mut">${esc(t('Noch keine.','None yet.'))}</span>`}</div>
    <div class="rowin" style="margin-top:6px"><input id="auslname" maxlength="81" placeholder="${esc(t('Name, z. B. Archiv oder Alt*','Name, e.g. Archive or Old*'))}" autocomplete="off"><button class="b" id="auslnameadd" type="button">${esc(t('Hinzufügen','Add'))}</button></div>
    <div class="fh">${esc(t(`Groß und klein egal, * am Ende heißt „beginnt mit“. Höchstens ${AU.max_names}.`,`Case does not matter, * at the end means "begins with". At most ${AU.max_names}.`))}</div>
    <h3>${esc(t('Ausgelassene Ordner','Left-out folders'))}</h3>
    ${rows||`<div class="mut">${esc(t('Noch keiner. Unten im Ordnerbaum „Auslassen“ wählen.','None yet. Pick "Leave out" in the folder tree below.'))}</div>`}
    ${AU.sources.some(s=>s.tree)?`<h3>${esc(t('Ordner ansehen und auslassen','Look at folders and leave them out'))}</h3>
    <select id="auslsrc" aria-label="${esc(t('Wissensordner','Knowledge folder'))}">${srcs}</select><div id="ausltree" class="aultree"></div>`:''}
    <h3>${esc(t('Immer ausgelassen','Always left out'))}</h3>
    <div class="chips" style="justify-content:flex-start">${AU.always.map(x=>`<span class="chip">${esc(x)}</span>`).join('')}</div>
    <div class="fh">${esc(t('Feste Regel im Panel, lässt sich nicht abschalten.','A fixed rule in the panel; it cannot be switched off.'))}</div>
    <div id="auslmsg" class="mut" role="status"></div>`;
  auBind(box);if($('auslsrc')){if(AUCUR){const i=AU.sources.findIndex(s=>s.nas===AUCUR.nas&&AUCUR.path.startsWith(s.path==='/'?'':s.path));if(i>=0)$('auslsrc').value=String(i)}auTree()}}
async function auTree(){const out=$('ausltree');if(!out)return;const s=AU.sources[+$('auslsrc').value||0];if(!s)return;
  if(!AUCUR||AUCUR.nas!==s.nas||!(AUCUR.path+'/').startsWith(s.path==='/'?'/':s.path+'/'))AUCUR={nas:s.nas,path:s.path==='/'?'':s.path,root:s.path==='/'?'':s.path};
  out.textContent=t('Lese die Ordner …','Reading the folders …');
  const own=AUCUR.nas==='rm'||AUCUR.nas==='pc';
  const r=await apiTry(own?'/api/profile/auslassen/tree?ort='+AUCUR.nas+'&path='+encodeURIComponent(AUCUR.path||'/')
    :'/api/profile/nasquelle/tree?nas='+encodeURIComponent(AUCUR.nas)+'&path='+encodeURIComponent(AUCUR.path||'/'));
  if(!r.r.ok){out.textContent='';auSay((r.d&&r.d.detail)||t('Der Ort antwortet nicht.','The place does not answer.'),true);return}
  const d=r.d,here=AUCUR.path;
  const up=here&&here!==AUCUR.root?`<div class="zrow"><button class="b" type="button" data-auup="1">↑ ${esc(t('nach oben','up'))}</button><span class="mut">${esc(here)}</span></div>`:`<div class="zrow"><span class="mut">${esc(here||'/')}</span></div>`;
  out.innerHTML=up+d.dirs.map(n=>{const p=here+'/'+n,w=(d.out||{})[n];
    const right=w==='ordner'&&auIs(AUCUR.nas,p)?`<button class="b" type="button" data-auin="${esc(p)}">${esc(t('Zulassen','Let in'))}</button>`
      :w==='ordner'?`<span class="pill warn">${esc(t('Ordner darüber ausgelassen','folder above left out'))}</span>`
      :w==='name'?`<span class="pill warn">${esc(t('Namensregel','name rule'))}</span>`
      :`<button class="b" type="button" data-auout="${esc(n)}">${esc(t('Auslassen','Leave out'))}</button>`;
    return `<div class="zrow" data-aurow="${esc(n)}"><button class="b${w?' mut':''}" type="button" data-audir="${esc(n)}">📁 ${esc(n)}</button><span></span>${right}</div>`}).join('')
    +`<div class="fh">${esc((own?(d.dirs.length?'':t('Keine Unterordner bekannt.','No sub folders known.')):t(`${d.files} Dateien direkt hier`,`${d.files} files right here`))+(d.more?' · '+t('nur die ersten 500 Ordner','only the first 500 folders'):''))}</div>`;
  out.querySelectorAll('[data-audir]').forEach(b=>b.onclick=()=>{AUCUR.path=here+'/'+b.dataset.audir;auTree()});
  out.querySelectorAll('[data-auup]').forEach(b=>b.onclick=()=>{AUCUR.path=here.split('/').slice(0,-1).join('/');if(AUCUR.path.length<AUCUR.root.length)AUCUR.path=AUCUR.root;auTree()});
  out.querySelectorAll('[data-auin]').forEach(b=>b.onclick=()=>auIn({ort:AUCUR.nas,path:b.dataset.auin}));
  out.querySelectorAll('[data-auout]').forEach(b=>b.onclick=()=>auAsk(b.dataset.auout,b.closest('.zrow')))}
// before leaving a folder out: how many documents leave the search, and "only this folder" or "every folder of this name"
async function auAsk(n,row){const p=AUCUR.path+'/'+n;document.querySelectorAll('.auask').forEach(x=>x.remove());
  let one=0,all=0;try{one=(await (await api('/api/profile/auslassen',xjson('POST',{ort:AUCUR.nas,path:p,probe:true}))).json()).docs;
    all=(await (await api('/api/profile/auslassen',xjson('POST',{name:n,probe:true}))).json()).docs}catch(e){auSay(e.message,true);return}
  const box=document.createElement('div');box.className='auask use';AUASK={ort:AUCUR.nas,path:p,name:n};
  box.innerHTML=`<b>${esc(t(`„${n}“ auslassen?`,`Leave out "${n}"?`))}</b><div class="mut">${esc(t(`${one} Dokumente aus diesem Ordner verschwinden sofort aus Suche, „Erst lokal“ und Wissensbuch. Neue Dateien darin liest der Spark nicht mehr. Am Ort wird nichts gelöscht.`,`${one} documents from this folder leave the search, "Local first" and the knowledge book at once. The Spark reads no new files in it. Nothing is deleted at the place.`))}</div>
    <div class="row" style="margin-top:6px"><button class="b p" type="button" data-auyes="ordner">${esc(t('Nur diesen Ordner','Only this folder'))}</button><button class="b" type="button" data-auyes="name">${esc(t(`Jeden Ordner „${n}“ (${all} Dokumente)`,`Every folder "${n}" (${all} documents)`))}</button><button class="b" type="button" data-auyes="">${esc(t('Abbrechen','Cancel'))}</button></div>`;
  row.after(box);box.querySelectorAll('[data-auyes]').forEach(b=>b.onclick=()=>{const k=b.dataset.auyes;box.remove();
    if(k)auOut(k==='name'?{name:AUASK.name}:{ort:AUASK.ort,path:AUASK.path})})}
async function auOut(body){try{const r=await (await api('/api/profile/auslassen',xjson('POST',body))).json();await auShow();
    auSay(t(`Ausgelassen, ${r.removed} Dokumente aus der Suche.`,`Left out, ${r.removed} documents out of the search.`));if(typeof showDocs==='function')showDocs()}
  catch(e){auSay(e.message,true)}}
async function auIn(q){try{await api('/api/profile/auslassen?'+new URLSearchParams(q),{method:'DELETE'});await auShow();
    auSay(t('Wieder zugelassen. Der nächste Abgleich liest den Ordner neu.','Let in again. The next reading reads the folder anew.'))}
  catch(e){auSay(e.message,true)}}
function auBind(box){
  box.querySelectorAll('[data-auname]').forEach(b=>b.onclick=()=>auIn({name:b.dataset.auname}));
  box.querySelectorAll('[data-auort]').forEach(b=>b.onclick=()=>auIn({ort:b.dataset.auort,path:b.dataset.aupath}));
  const add=$('auslnameadd');if(add)add.onclick=async()=>{const v=$('auslname').value.trim();if(!v)return;
    let n=0;try{n=(await (await api('/api/profile/auslassen',xjson('POST',{name:v,probe:true}))).json()).docs}catch(e){auSay(e.message,true);return}
    if(n&&!confirm(t(`„${v}“ überall auslassen? ${n} Dokumente verschwinden sofort aus der Suche; am Ort bleibt alles.`,`Leave out "${v}" everywhere? ${n} documents leave the search at once; everything stays at the place.`)))return;
    auOut({name:v})};
  const src=$('auslsrc');if(src)src.onchange=()=>{AUCUR=null;auTree()}}
