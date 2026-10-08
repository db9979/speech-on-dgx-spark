// Search over the settings: Einstellungen (admin) and the Ich window. Runs only in the browser over the
// labels already on the page; a hit opens its page, unfolds what hides it and marks it for a moment.
const norm=s=>(s||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'').replace(/ß/g,'ss').replace(/\s+/g,' ').trim();
const visText=e=>e?(e.firstChild&&e.firstChild.nodeType===3?e.firstChild.nodeValue:e.textContent).trim():'';
function sHits(index,q){const w=norm(q).split(' ').filter(Boolean);if(!w.length)return [];
  const seen=new Set();return index.filter(x=>{const k=norm(x.label+' '+x.page+' '+(x.more||''));return w.every(p=>k.includes(p))})
    .sort((a,b)=>(norm(a.label).startsWith(norm(q))?0:1)-(norm(b.label).startsWith(norm(q))?0:1))
    .filter(x=>{const k=x.label+'|'+x.page;if(seen.has(k))return false;seen.add(k);return true}).slice(0,8)}
function sBox(ph,index,go){const w=document.createElement('div');w.className='sbox';
  w.innerHTML=`<input type="search" placeholder="${esc(ph)}" autocomplete="off" aria-label="${esc(ph)}"><div class="sres" hidden></div>`;
  const inp=w.querySelector('input'),res=w.querySelector('.sres');let hits=[];
  const show=()=>{hits=sHits(index(),inp.value);res.hidden=!inp.value.trim();
    res.innerHTML=hits.map((h,i)=>`<button type="button" data-i="${i}"><b>${esc(h.label)}</b><span>${esc(h.page)}</span></button>`).join('')||`<div class="mut">${esc(t('Nichts gefunden.','Nothing found.'))}</div>`;
    res.querySelectorAll('button').forEach(b=>b.onclick=()=>{const h=hits[+b.dataset.i];inp.value='';res.hidden=true;go(h)})};
  inp.oninput=show;inp.onkeydown=e=>{if(e.key==='Enter'&&hits[0]){e.preventDefault();const h=hits[0];inp.value='';res.hidden=true;go(h)}if(e.key==='Escape'){inp.value='';res.hidden=true}};
  inp.addEventListener('blur',()=>setTimeout(()=>{res.hidden=true},200));return w}
function sFlash(el){if(!el)return;el.scrollIntoView({block:'center',behavior:'smooth'});el.classList.remove('sflash');void el.offsetWidth;el.classList.add('sflash');
  setTimeout(()=>el.classList.remove('sflash'),2200)}
// ---------------------------------------------------------------- Einstellungen
function cfgIndex(){const out=[];
  document.querySelectorAll('#cfgnav button[data-p]').forEach(b=>{const p=b.dataset.p,pane=$('pane-'+p),page=visText(b);if(!pane)return;
    out.push({label:page,page:t('Seite','Page'),p,el:null});
    pane.querySelectorAll('.setrow .lbl>b, label, h2:not(.pt), summary, .fgrp>summary b').forEach(e=>{const l=visText(e);if(!l||l.length>90)return;
      const row=e.closest('.setrow')||e,hint=row.querySelector&&row.querySelector('.lbl>span');out.push({label:l,page,p,el:row,more:hint?hint.textContent:''})})});
  GUIDES.forEach(g=>{if(g.sw&&$(g.sw)){const pane=$(g.sw).closest('.pane');if(pane)out.push({label:gT(g.t),page:t('Funktionen','Features'),p:pane.id.slice(5),el:$(g.sw).closest('.setrow')||$(g.sw)})}});
  return out}
function cfgGo(h){const b=document.querySelector(`#cfgnav button[data-p="${h.p}"]`);if(b)b.click();if(!h.el)return;
  let el=h.el;const dep=el.closest('[data-show]');                       // a detail of a switch that is off: show the switch
  if(dep&&dep.style.display==='none'){const sw=$(dep.dataset.show);if(sw)el=sw.closest('.setrow')||sw}
  for(let d=el.closest('details');d;d=d.parentElement.closest('details'))d.open=true;
  setTimeout(()=>sFlash(el),60)}
function cfgSearchMount(){const nav=$('cfgnav');if(!nav||nav.querySelector('.sbox'))return;
  nav.prepend(sBox(t('Einstellung suchen …','Search settings …'),cfgIndex,cfgGo))}
// ---------------------------------------------------------------- Ich window
function meIndex(){const out=[];(typeof ME_ITEMS!=='undefined'?ME_ITEMS:[]).forEach(([id,page])=>{const box=$(id);if(!box)return;
  out.push({label:page,page:t('Seite','Page'),id,el:null});
  box.querySelectorAll('.setrow .lbl>b, label, summary').forEach(e=>{if(e.closest('details.guide'))return;const l=visText(e);if(!l||l.length>90)return;
    const row=e.closest('.setrow')||e,hint=row.querySelector&&row.querySelector('.lbl>span');out.push({label:l,page,id,el:row,more:hint?hint.textContent:''})})});
  return out}
function meGo(h){meLast=h.id;ptab(h.id);if(!h.el)return;
  const sp=h.el.closest('.setpane');if(sp){const bar=sp.parentElement.querySelector(':scope>.ptabs'),i=[...sp.parentElement.querySelectorAll(':scope>.setpane')].indexOf(sp);
    if(bar&&bar.children[i])bar.children[i].click()}
  for(let d=h.el.closest('details');d;d=d.parentElement.closest('details'))d.open=true;
  setTimeout(()=>sFlash(h.el),60)}
function meSearchMount(){const nav=$('ptabs');if(!nav||nav.querySelector('.sbox')||(typeof ME_ITEMS!=='undefined'&&ME_ITEMS.length<4))return;
  nav.prepend(sBox(t('In Ich suchen …','Search in Me …'),meIndex,meGo))}
cfgSearchMount();
