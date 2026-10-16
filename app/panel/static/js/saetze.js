// „Das kannst du auch sagen“ (saetze.py, plan plaene/funktionen-zeigen.md): the panel's fixed sentences for functions
// that are on but never used. Under an answer (follow-ups, „Meintest du …?“, „Neu bei dir“, „Was kannst du?“), „Probier
// mal“ in an empty chat and Ich → Was ich kann. A tap only puts the sentence into the field: the person sends it
// themselves, so it goes through the Weiche and every rule like a typed question; the page tells the panel which
// tool's sentence it was (counted by its name only).
let SATZ_ON=false,MORE_TAP=null;
const moreTxt=x=>(x.text||[])[L==='en'?1:0]||'';
function moreUse(x){const f=$('chattext');if(!f)return;const s=moreTxt(x);if(!s)return;
  const sec=$('chat');if(sec&&!sec.classList.contains('on')&&typeof goSec==='function')goSec('chat');
  f.value=s;MORE_TAP={tool:x.tool,text:s};f.focus();try{f.setSelectionRange(s.length,s.length)}catch{}}
// sent exactly as it was suggested: the tool's name goes along, nothing else
function moreTake(text){const m=MORE_TAP;MORE_TAP=null;return m&&String(text).trim()===m.text?m.tool:undefined}
function moreChips(items,box){for(const x of items){const b=document.createElement('button');b.type='button';b.className='b chb';b.textContent=moreTxt(x);
    b.title=t('Ins Eingabefeld setzen','Put into the input field');b.addEventListener('click',e=>{e.stopPropagation();moreUse(x)});box.appendChild(b)}}
// under the answer: one row, its kind decides the line above it
function moreRow(ev){const d=document.createElement('div');d.className='more';const items=(ev.items||[]).slice(0,12);
  const head=document.createElement('div');head.className='mut moreh';const n=items[0]&&(items[0].name||[])[L==='en'?1:0];
  head.textContent={near:t('Meintest du:','Did you mean:'),new:t('Neu bei dir: ','New for you: ')+(n||''),kann:t('Das kannst du zum Beispiel sagen:','For example you can say:')}[ev.kind]||t('Das kannst du auch sagen:','You can also say:');
  d.appendChild(head);const row=document.createElement('div');row.className='choice';moreChips(items,row);d.appendChild(row);return d}
// a new, empty chat: „Probier mal“ with three sentences, other ones each week (not while the page is hidden)
async function moreStart(){const old=$('morestart');if(old)old.remove();if(!SATZ_ON||!PROFILE||document.hidden)return;
  const log=$('chatlog');if(!log||log.children.length)return;
  let d;try{d=await (await api('/api/profile/saetze?nur=start')).json()}catch{return}
  if(!d.on||!d.start||!d.start.length||log.children.length)return;
  const box=document.createElement('div');box.id='morestart';box.className='more morestart';
  const h=document.createElement('div');h.className='mut moreh';h.textContent=t('Probier mal, das geht bei dir:','Try this, it works for you:');box.appendChild(h);
  const row=document.createElement('div');row.className='choice';moreChips(d.start,row);box.appendChild(row);log.appendChild(box)}
function moreStartGone(){const b=$('morestart');if(b)b.remove()}
// Ich → Was ich kann: every area with what this profile can say, unused and new marked, a search field
let KANN=null;
async function showKann(){const box=$('kannbox');if(!box)return;if(!PROFILE||!SATZ_ON){box.innerHTML='';return}
  try{KANN=await (await api('/api/profile/saetze')).json()}catch(e){box.innerHTML=`<div class="fh">${esc(e.message)}</div>`;return}
  box.innerHTML=`<div class="intro">${esc(t('Was du bei mir sagen kannst, nach Bereichen. Ein Tipp setzt den Satz ins Eingabefeld, du schickst ihn selbst ab. „noch nie benutzt“ steht bei dem, was du noch nicht ausprobiert hast.','What you can say to me, by area. A tap puts the sentence into the input field; you send it yourself. "never used" marks what you have not tried yet.'))}</div>`+
    `<input type="search" id="kannq" maxlength="60" placeholder="${esc(t('Suchen …','Search …'))}" aria-label="${esc(t('In der Liste suchen','Search the list'))}"><div id="kannlist"></div>`+
    `<div class="row"><button class="b" type="button" id="kanndel">${esc(t('Meine Zählung löschen','Delete my count'))}</button><span class="mut" id="kannmsg" role="status"></span></div>`;
  $('kannq').oninput=kannDraw;kannDraw();
  $('kanndel').onclick=async()=>{if(!confirm(t('Vergessen, welche Funktionen du schon benutzt hast? Dann kommen die Sätze wieder von vorn.','Forget which functions you used already? The sentences then start over.')))return;
    try{await api('/api/profile/saetze',{method:'DELETE'});$('kannmsg').textContent=t('Gelöscht.','Deleted.');showKann()}catch(e){$('kannmsg').textContent=e.message}}}
function kannDraw(){const list=$('kannlist');if(!list||!KANN)return;const q=($('kannq').value||'').trim().toLowerCase();list.textContent='';
  for(const a of KANN.areas||[]){const items=a.items.filter(x=>!q||(moreTxt(x)+' '+(x.name||[]).join(' ')).toLowerCase().includes(q));if(!items.length)continue;
    const c=document.createElement('div');c.className='card';const h=document.createElement('h3');h.textContent=(a.name||[])[L==='en'?1:0]||'';c.appendChild(h);
    for(const x of items){const r=document.createElement('div');r.className='kannrow';const b=document.createElement('button');b.type='button';b.className='b chb';b.textContent=moreTxt(x);
      b.addEventListener('click',()=>{moreUse(x);if(typeof closeProf==='function')closeProf()});
      const s=document.createElement('small');s.className='mut';s.textContent=' '+((x.name||[])[L==='en'?1:0]||'')+(x.new?' · '+t('neu','new'):'')+(x.used?'':' · '+t('noch nie benutzt','never used'));
      r.append(b,s);c.appendChild(r)}
    list.appendChild(c)}
  if(!list.children.length){const p=document.createElement('div');p.className='mut';p.textContent=q?t('Nichts gefunden.','Nothing found.'):t('Gerade ist nichts freigegeben, das du sagen kannst.','Nothing you can say is released right now.');list.appendChild(p)}}
