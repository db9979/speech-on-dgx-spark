// Gemerkt-Hinweis (gemerkt.py, plan nutzerwissen Punkt 1, Dominik 2026-10-29): what memory_save kept in an answer stands
// under it as a chip „✓ Gemerkt: … · Rückgängig · Ansehen“. The message keeps only the numbers (mem [{id, rev}]); the
// text comes from Ich → Gedächtnis when the conversation is drawn again, so every device shows the same. „Rückgängig“
// works only while the fact is unchanged since (the Spark checks rev, 409 otherwise). The fact is the person's own
// word: shown through textContent (icEl), never innerHTML.
const GM={facts:null,at:0,busy:null};
function gmFacts(){if(GM.facts&&Date.now()-GM.at<30e3)return Promise.resolve(GM.facts);if(GM.busy)return GM.busy;
  GM.busy=apiTry('/api/profile/memory').then(({r,d})=>{GM.busy=null;if(r.ok){GM.facts=new Map((d.facts||[]).map(f=>[f.id,f]));GM.at=Date.now()}return GM.facts||new Map()});
  return GM.busy}
window.gmChips=list=>{const box=icEl('div','gmbox');for(const x of list.slice(0,3))box.appendChild(gmChip(x));return box};
function gmChip(x){const c=icEl('div','gm'),txt=icEl('span','gm-t','✓ '+t('Gemerkt: ','Remembered: ')+(x.text||'…'));
  const undo=icEl('button','ic-lnk gm-b',t('Rückgängig','Undo'));undo.type='button';undo.hidden=x.undo===false;
  const note=icEl('span','mut gm-n','');
  if(!x.text)gmFacts().then(m=>{const f=m.get(x.id);if(f)txt.textContent='✓ '+t('Gemerkt: ','Remembered: ')+f.text;
    else{txt.textContent=t('Gemerkt, inzwischen nicht mehr im Gedächtnis','Remembered, no longer in the memory');undo.hidden=true}});
  undo.onclick=async()=>{undo.disabled=true;
    try{const d=await (await api('/api/profile/memory/'+encodeURIComponent(x.id)+'/undo',xjson('POST',{rev:x.rev}))).json();
      c.classList.add('gm-weg');txt.textContent='↺ '+(d.how==='zurueckgeholt'?t('Frühere Fassung wieder da','Earlier version is back'):t('Vergessen','Forgotten'));
      undo.hidden=true;GM.at=0}
    catch(e){undo.hidden=true;note.textContent=' · '+e.message}};
  const see=icLink(t('Ansehen','Show'),()=>{if(typeof openMe==='function')openMe('factbox')});see.classList.add('gm-b');
  c.append(txt,undo,note,see);return c}
