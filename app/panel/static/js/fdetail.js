// Funktionen als Liste + Detail (plaene/einstellungen-neu.md, Paket 3): on a wide page the open function shows on the
// right (its sentence, who may use it, its settings, its guide), the list on the left stays one line per function. On a
// narrow page it opens below its line as before. The rows are moved, not copied: ids, loading, saving, "braucht dich"
// and the search work unchanged, and closing puts them back into the item. "Wer darf es" uses the same endpoints as
// the table "Wer darf was" (/api/admin/features, …/profiles/<id>) and works at once, without the save bar. What the
// Spark allows works for every profile at once (Dominik 2026-10-13); a chip only blocks one profile (on = may use it).
(()=>{
const pane=$('pane-feat');if(!pane)return;
const side=document.createElement('aside');side.id='fdet';side.className='fdet';
const inner=document.createElement('div');inner.className='fdin';side.appendChild(inner);pane.appendChild(side);
let cur=null,split=false;
const nameOf=it=>{const b=it.querySelector(':scope>.setrow .lbl>b');return b?(b.firstChild&&b.firstChild.nodeValue||b.textContent).trim():''};
const textOf=el=>el?[...el.childNodes].filter(n=>n.nodeType===3).map(n=>n.nodeValue).join('').trim():'';
function empty(){inner.textContent='';const p=document.createElement('div');p.className='fdempty';
  const b=document.createElement('b');b.textContent=t('Funktion antippen','Tap a function');
  const s=document.createElement('span');s.textContent=t('Hier stehen dann ihre Erklärung, wer sie nutzen darf, ihre Einstellungen und die Anleitung.','Its explanation, who may use it, its settings and the guide then show here.');
  p.append(b,s);inner.appendChild(p)}
function head(it){const row=it.firstElementChild,h=document.createElement('div');h.className='fdhead';
  const top=document.createElement('div');top.className='fdtop';const b=document.createElement('b');b.textContent=nameOf(it);
  const x=document.createElement('button');x.type='button';x.className='fdx';x.setAttribute('aria-label',t('Schließen','Close'));x.textContent='×';x.onclick=()=>featOpen(it,false);
  top.append(b,x);h.appendChild(top);
  const s=textOf(row.querySelector('.lbl>span'));if(s){const p=document.createElement('p');p.textContent=s;h.appendChild(p)}
  const tags=row.querySelector('.ftags');if(tags)h.appendChild(tags.cloneNode(true));
  const g=row.querySelector('.gbtn');if(g){const a=document.createElement('button');a.type='button';a.className='b fdguide';a.textContent=t('Anleitung','Guide');
    a.onclick=()=>{g.click();const box=[...inner.querySelectorAll('.guide.inline')][0];if(box&&!box.hidden)box.scrollIntoView({block:'nearest'})};h.appendChild(a)}
  return h}
function out(it){if(cur===it)return;back();cur=it;it._kids=[...it.children].slice(1);inner.textContent='';
  const body=document.createElement('div');body.className='fdbody';body.append(...it._kids);inner.append(head(it),body);it.classList.add('fside');inner.scrollTop=0}
function back(){if(!cur)return;const it=cur;cur=null;const body=inner.querySelector('.fdbody');if(body)it.append(...body.children);it.classList.remove('fside');empty()}
// ---------------------------------------------------------------- Wer darf es
let WD=null;
async function whoData(){try{WD=await (await api('/api/admin/features')).json()}catch{WD=null}return WD}
const inItem=(it,el)=>!!el&&(it.contains(el)||(cur===it&&inner.contains(el)));
async function who(it){let box=[...it.children].find(x=>x.classList.contains('fwho'))||(cur===it&&inner.querySelector('.fwho'));
  if(!box){box=document.createElement('div');box.className='fwho';box.dataset.nodirty='1';
    const body=cur===it&&inner.querySelector('.fdbody');body?body.prepend(box):it.firstElementChild.after(box)}
  const d=WD||await whoData();if(!d){box.hidden=true;return}
  // the function itself and the switches inside it that show now (a sub-switch hides while the one it builds on is off)
  const shown=el=>{for(let x=el.closest('[data-show]');x;x=x.parentElement&&x.parentElement.closest('[data-show]'))if(x.style.display==='none')return false;return true};
  const fs=d.features.filter(f=>{if(f.blockable===false)return false;const el=$('chat.'+f.switch);return inItem(it,el)&&('chat.'+f.switch===it.dataset.sw||shown(el))});if(!fs.length){box.hidden=true;return}
  box.hidden=false;box.textContent='';const h=document.createElement('div');h.className='fwhoh';
  h.innerHTML=`<b>${esc(t('Wer darf es','Who may use it'))}</b><span>${esc(t('wirkt sofort','applies at once'))}</span>`;box.appendChild(h);
  for(const f of fs){const r=document.createElement('div');r.className='fwrow';
    if(fs.length>1){const n=document.createElement('div');n.className='fwname';n.textContent=f.name[L==='en'?1:0];r.appendChild(n)}
    const chips=document.createElement('div');chips.className='fwchips';
    const nm=f.name[L==='en'?1:0];
    for(const p of d.profiles){const inh=!!(f.inherited&&f.inherited[p.id]),on=!!f.cells[p.id];
      chips.appendChild(chip(p.name,on&&!inh,f.spark&&!inh,`${nm} – ${p.name}`,async()=>{
        await api(`/api/admin/features/${encodeURIComponent(f.key)}/profiles/${encodeURIComponent(p.id)}`,xjson('PUT',{on:!on}));f.cells[p.id]=!on}))}
    r.appendChild(chips);box.appendChild(r)}
  const n=document.createElement('div');n.className='mut fwg';
  n.textContent=fs.some(f=>!f.spark)?t('Gilt für alle Profile, sobald der Schalter der Funktion an und gespeichert ist; hier sperrst du dann einzelne Profile.','Applies to every profile once the function\'s switch is on and saved; here you then block single profiles.')
    :t('Gilt sofort für alle Profile; hier sperrst du einzelne Profile.','Applies to every profile at once; here you block single profiles.');box.appendChild(n)
  const g=document.createElement('div');g.className='mut fwg';g.textContent=t('Gäste: nie (nur Fragen und Antworten)','Guests: never (questions and answers only)');box.appendChild(g)
  // a jump from Wer darf was scrolled to its row before this box was filled and pushed the row down: scroll again
  // (until the user moves himself, so a later refresh by a chip does not move the page; the flash alone was too
  // short on a slow device with many profiles)
  const j=typeof WHO_LAST!=='undefined'&&WHO_LAST;if(j&&typeof whoKeepJump==='function'&&whoKeepJump()&&inItem(it,j))j.scrollIntoView({block:'center'})
  function chip(label,on,can,aria,act,cls){if(can&&!on)cls=(cls?cls+' ':'')+'blk';const b=document.createElement('button');b.type='button';b.className='fwc'+(on?' on':'')+(cls?' '+cls:'');
    b.textContent=label;b.disabled=!can;b.setAttribute('aria-pressed',on?'true':'false');b.setAttribute('aria-label',`${aria}: ${on?t('darf es','may use it'):can?t('gesperrt','blocked'):t('geht nicht','not possible')}`);
    b.onclick=async()=>{b.disabled=true;try{await act();who(it)}catch(e){alert(e.message);b.disabled=false}};return b}}
// ---------------------------------------------------------------- open, close, wide or narrow
window.featSide=(it,on)=>{if(on){if(split){if(cur&&cur!==it)featOpen(cur,false);out(it)}WD=null;who(it)}else if(cur===it)back()};
window.featCur=()=>cur;
function layout(){const w=pane.getBoundingClientRect().width;if(!w)return;const s=w>=740&&!document.body.classList.contains('appview');if(s===split)return;
  split=s;pane.classList.toggle('fsplit',s);
  if(!s){back();return}
  const open=[...pane.querySelectorAll('.fitem.open')];open.slice(1).forEach(x=>featOpen(x,false));if(open[0])out(open[0])}
empty();new ResizeObserver(layout).observe(pane);
// Vorgaben, which are a function of their own (Rückfrage ohne Weckwort, Eigene Stimme überhören): the preset for the
// profiles sits in that function's detail, not twice under Vorgaben (plaene/einstellungen-anordnung.md, Umzug 3)
const PRESET={follow:'chat.follow_up',echo:'chat.no_self_echo'};
// (drawn anew on every load: the row moved last time goes, the new one from Vorgaben takes its place; looked up inside
// #chatdefaults, because the old one comes first in the page and would hide it)
window.presetMove=()=>{for(const [k,sw] of Object.entries(PRESET)){const e=$('chatdefaults').querySelector('#set_chatdefaults_'+k),it=$(sw)&&$(sw).closest('.fitem');
  if(!e)continue;document.querySelectorAll(`#pane-feat [data-preset="${k}"]`).forEach(x=>x.remove());
  const row=e&&e.closest('.setrow');if(!row||!it||row.dataset.preset)continue;row.dataset.preset=k;row.classList.add('fpreset');
  const b=row.querySelector('.lbl>b'),s=row.querySelector('.lbl>span');if(b)b.textContent=t('Vorgabe für Profile','Default for profiles');
  if(s)s.textContent=t('Gilt für Profile, die unter Ich selbst nichts geändert haben.','For profiles that have not changed it themselves under Me.');
  const body=cur===it&&inner.querySelector('.fdbody');body?body.appendChild(row):it.appendChild(row)}};
})();
