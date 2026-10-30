// Ich-Seiten aufräumen (ich-aufraeumen/plan.md, Paket 1): the building blocks every "Ich" page shares, so the pages
// look alike: sub-tabs with counts instead of little arrows, a status card with a "⋯" menu, list rows with small
// icon buttons, long lists that show the first ten and "Weitere … zeigen" instead of a scroll box inside the page,
// "add" forms as a button that opens a card, and a danger zone for what cannot be undone.
// Everything is built with createElement/textContent (strict CSP: no inline handlers).
(()=>{
// symbols: icons.js (one source); n is a fixed name of this page or of the server (offen.js VG_SYMS), never text
window.icSvg=(n,size=16)=>{const v=icNode(n);v.setAttribute('width',size);v.setAttribute('height',size);return v};
const el=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e};
window.icEl=el;
// small square button with an icon; label for screen readers and the tooltip
window.icBtn=(icon,label,act,cls='')=>{const b=el('button','ic-ib'+(cls?' '+cls:''));b.type='button';b.title=label;b.setAttribute('aria-label',label);
  b.appendChild(icSvg(icon));if(act)b.onclick=e=>{e.stopPropagation();act(b)};return b};
// ---------------------------------------------------------------- sub-tabs with counts
// items: [{k, label, n (count or ''), hot (needs you: orange), body: () => Node}]. Opens the tab chosen last on this
// page, else the first that needs you, else the first. The chosen tab survives a redraw of the page.
const MT={};
window.icTabs=(key,items)=>{const wrap=el('div','ic-tabwrap'),nav=el('div','ic-tabs');nav.setAttribute('role','tablist');const body=el('div','ic-tabbody');
  let cur=items.find(x=>x.k===MT[key])||items.find(x=>x.hot)||items[0];
  const draw=()=>{nav.querySelectorAll('button').forEach(b=>{const on=b.dataset.k===cur.k;b.classList.toggle('on',on);b.setAttribute('aria-selected',on?'true':'false')});
    // a box that lives in the page (Einstellungen: #mailbox, #calbox …) goes back home before the body is cleared, else
    // it left the document and the second visit of its tab found nothing (Dominik 2026-10-22: Einstellungen leer)
    for(const c of [...body.children])if(c._icHome){c.hidden=true;c._icHome.appendChild(c)}
    body.textContent='';const n=cur.body();if(n){if(n.isConnected&&!n._icHome)n._icHome=n.parentNode;body.appendChild(n)}};
  for(const it of items){const b=el('button');b.type='button';b.dataset.k=it.k;b.setAttribute('role','tab');b.appendChild(document.createTextNode(it.label));
    if(it.n!==''&&it.n!=null){const i=el('i',it.hot?'hot':'',String(it.n));b.appendChild(i)}
    b.onclick=()=>{cur=it;MT[key]=it.k;draw()};nav.appendChild(b)}
  wrap.append(nav,body);draw();return wrap};
window.icTabSet=(key,k)=>{MT[key]=k};
// ---------------------------------------------------------------- status card
// icon, title, line below, then the main controls; rare actions sit in the "⋯" menu (danger in red, with a question)
window.icCard=(icon,title,sub,ctl,menu)=>{const c=el('div','ic-card');const ic=el('span','ic-cico');ic.appendChild(icSvg(icon,18));
  const mid=el('div','ic-mid');mid.appendChild(el('b','',title));if(sub)mid.appendChild(el('span','',sub));c.append(ic,mid);
  (ctl||[]).forEach(x=>x&&c.appendChild(x));if(menu&&menu.length)c.appendChild(icMenu(menu));return c};
window.icMenu=items=>{const w=el('span','ic-menu');const b=icBtn('more',t('Mehr','More'),()=>{const open=!pop.hidden;document.querySelectorAll('.ic-pop').forEach(p=>p.hidden=true);pop.hidden=open},'v');
  b.setAttribute('aria-haspopup','true');const pop=el('div','ic-pop');pop.hidden=true;
  for(const it of items){const x=el('button',it.danger?'danger':'',it.label);x.type='button';x.onclick=()=>{pop.hidden=true;it.act()};pop.appendChild(x)}
  w.append(b,pop);return w};
document.addEventListener('click',e=>{if(!e.target.closest('.ic-menu'))document.querySelectorAll('.ic-pop').forEach(p=>p.hidden=true)});
// ---------------------------------------------------------------- list rows
// title (wraps) and a grey line below that ends with "…" when too long (the whole text is its tooltip)
window.icRow=(title,meta,acts,lead,one)=>{const r=el('div','ic-row');if(lead)(Array.isArray(lead)?lead:[lead]).forEach(x=>x&&r.appendChild(x));
  const m=el('div','ic-rmid');const tt=typeof title==='string'?el('span',one?'ic-one':'ic-t',title):title;if(one&&typeof title==='string')tt.title=title;m.appendChild(tt);
  if(meta){const s=el('small','ic-meta',meta);s.title=meta;m.appendChild(s)}r.appendChild(m);(acts||[]).forEach(x=>x&&r.appendChild(x));return r};
window.icList=rows=>{const l=el('div','ic-list');rows.forEach(x=>l.appendChild(x));return l};
window.icGroup=(title,n,link)=>{const g=el('div','ic-gl');g.appendChild(el('h4','',title+(n!=null&&n!==''?' · '+n:'')));if(link)g.appendChild(link);return g};
window.icLink=(text,act)=>{const a=el('button','ic-lnk',text);a.type='button';a.onclick=act;return a};
window.icEmpty=text=>el('div','ic-empty',text);
window.icNote=(title,sub,ctl)=>{const n=el('div','ic-note');n.appendChild(icSvg('spark',18));const m=el('div','ic-mid');m.appendChild(el('b','',title));
  if(sub)m.appendChild(el('span','',sub));n.appendChild(m);(ctl||[]).forEach(x=>x&&n.appendChild(x));return n};
window.icDanger=(title,sub,label,act)=>{const d=el('div','ic-danger');const m=el('div','ic-mid');m.appendChild(el('b','',title));m.appendChild(el('span','',sub));
  const b=el('button','b ic-red',label);b.type='button';b.onclick=act;d.append(m,b);return d};
window.icStats=xs=>{const s=el('div','ic-stats');for(const [v,l,hot] of xs){const c=el('div','ic-stat'+(hot?' hot':''));c.append(el('b','',String(v)),el('span','',l));s.appendChild(c)}return s};
window.icChip=(label,on,act,cls)=>{const b=el('button','ic-chip'+(on?' on':'')+(cls?' '+cls:''),label);b.type='button';b.setAttribute('aria-pressed',on?'true':'false');if(act)b.onclick=()=>act(b);return b};
window.icSearch=(ph,val,oninput,id)=>{const w=el('label','ic-search');w.appendChild(icSvg('search',15));
  const i=document.createElement('input');i.type='search';i.maxLength=120;i.placeholder=ph;i.value=val||'';i.autocomplete='off';i.setAttribute('aria-label',ph);if(id)i.id=id;
  i.oninput=()=>oninput(i.value,i);w.appendChild(i);return w};
// a checkbox look for selection (also half: a part of a folder is chosen)
window.icCheck=(state,label,act)=>{const b=el('button','ic-cb'+(state===true?' on':state==='half'?' half':''));b.type='button';b.setAttribute('role','checkbox');
  b.setAttribute('aria-checked',state===true?'true':state==='half'?'mixed':'false');b.setAttribute('aria-label',label);if(state===true)b.appendChild(icSvg('check',12));
  b.onclick=e=>{e.stopPropagation();act(b)};return b};
// ---------------------------------------------------------------- Liste + Detail (Klar 4, Redesign Stufe 4)
// The building blocks of every list page (Personen und Geräte, Offen, Chats; the look in app.css „Klar 4“): a row of
// one height with a symbol (ldIco) or initials (ldAva), a title, one line below and on the right the state as a dot
// with a word (ldSt), a time or a count; filters as one segment (ldSeg); an empty list says one sentence under its
// symbol (ldEmpty). Text from outside (names, titles) goes in as textContent only.
window.ldInit=n=>{const w=String(n||'?').trim().split(/\s+/).filter(Boolean);return ((w.length>1?w[0][0]+w[1][0]:(w[0]||'?').slice(0,2))||'?').toUpperCase()};
window.ldIco=n=>{const s=el('span','ld-ico');s.setAttribute('aria-hidden','true');s.appendChild(icSvg(n,16));return s};
window.ldAva=(name,icon)=>{const s=el('span','ld-ava',icon?null:ldInit(name));s.setAttribute('aria-hidden','true');if(icon)s.appendChild(icSvg(icon,16));return s};
window.ldSt=(kind,word)=>el('span','ld-st'+(kind?' '+kind:''),word);
window.ldEmpty=(icon,text)=>{const d=el('div','ld-empty');d.append(icSvg(icon,28),el('span','',text));return d};
// one row; act(row) on a click or Enter/Space (a button, link or field inside keeps its own click); without act it
// is a plain line (no pointer, no hover)
window.ldRow=(o)=>{const r=el('div','ld-row'+(o.on?' on':''));if(o.act){r.setAttribute('role','button');r.tabIndex=0}if(o.lead)r.appendChild(o.lead);
  const m=el('span','ld-mid');m.appendChild(el('b','',o.title));if(o.sub)m.appendChild(el('small','',o.sub));r.appendChild(m);
  const right=(o.right||[]).filter(Boolean);if(right.length){const x=el('span','ld-right');x.append(...right);r.appendChild(x)}
  if(o.act){r.onclick=e=>{if(e.target.closest('button,a,input,select,label'))return;o.act(r)};
    r.onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&e.target===r){e.preventDefault();o.act(r)}}}
  return r};
// filters as one segment: items [[key, label, count?]], the chosen one cur; act(key)
window.ldSeg=(items,cur,act,label)=>{const s=el('div','segc ld-seg');s.setAttribute('role','radiogroup');if(label)s.setAttribute('aria-label',label);
  for(const [k,l,n] of items){const b=el('button',k===cur?'on':'',l);b.type='button';b.setAttribute('role','radio');b.setAttribute('aria-checked',String(k===cur));
    if(n!=null&&n!=='')b.appendChild(el('i','',String(n)));b.onclick=()=>act(k);s.appendChild(b)}
  return s};
// A page drawn as headings with lists below (Aufträge, Nachrichten, Sicherheit): from the first h3 on, every heading
// becomes a tab and what follows it its panel. The nodes are moved, not copied (ids and handlers stay). A message
// line (id …msg) and what follows .ic-tabend stay below the tabs, visible whatever tab is open. hot: a selector that
// marks a panel as needing you (its count turns orange).
window.icAutoTabs=(box,key,hot)=>{const kids=[...box.children];const i=kids.findIndex(x=>x.tagName==='H3');if(i<0)return;
  const end=kids.findIndex(x=>x.classList&&x.classList.contains('ic-tabend'));const body=end<0?kids.slice(i):kids.slice(i,end);
  if(body.filter(x=>x.tagName==='H3').length<2)return;
  const secs=[],tail=[];let cur=null;
  for(const x of body){if(x.tagName==='H3'){cur={label:x.textContent.trim(),nodes:[]};secs.push(cur);x.remove();continue}
    if(/msg$/.test(x.id||'')&&x===body[body.length-1]){tail.push(x);continue}cur.nodes.push(x)}
  const wrap=el('div','ic-tabwrap'),nav=el('div','ic-tabs');nav.setAttribute('role','tablist');wrap.appendChild(nav);
  const count=p=>{const fix=p.querySelector('[data-tabcount]');if(fix)return fix.dataset.tabcount;const ul=p.querySelectorAll('ul.facts');if(!ul.length)return'';let n=0;ul.forEach(u=>n+=[...u.children].filter(li=>li.tagName==='LI'&&!li.classList.contains('mut')&&!li.classList.contains('ic-more')).length);return n};
  const items=secs.filter(x=>x.nodes.length).map(sc=>{const p=el('div','ic-panel');sc.nodes.forEach(n=>p.appendChild(n));wrap.appendChild(p);
    const b=el('button');b.type='button';b.setAttribute('role','tab');b.appendChild(document.createTextNode(sc.label));nav.appendChild(b);return {k:sc.label,p,b}});
  const show=it=>{items.forEach(x=>{const on=x===it;x.p.hidden=!on;x.b.classList.toggle('on',on);x.b.setAttribute('aria-selected',on?'true':'false')})};
  const badge=()=>items.forEach(x=>{let i=x.b.querySelector('i');const n=count(x.p),h=!!(hot&&x.p.querySelector(hot));
    if(n===''||n===0&&!h){if(i)i.remove();return}if(!i){i=el('i');x.b.appendChild(i)}if(i.textContent!==String(n))i.textContent=String(n);if(i.className!==(h?'hot':''))i.className=h?'hot':''});
  items.forEach(x=>x.b.onclick=()=>{MT[key]=x.k;show(x)});
  badge();show(items.find(x=>x.k===MT[key])||items.find(x=>hot&&x.p.querySelector(hot))||items[0]);
  wrap.icBadge=badge;const after=end<0?null:kids[end];after?box.insertBefore(wrap,after):box.appendChild(wrap);tail.forEach(x=>after?box.insertBefore(x,after):box.appendChild(x));return wrap};
// ---------------------------------------------------------------- every list, every arrow in Ich
// Lists (ul.facts) show the first ten and "Weitere … zeigen" under them; the page scrolls, never a box inside it.
// "Add" forms (Postfach hinzufügen, Kalender hinzufügen …) open from a button; other arrows become cards.
const N=10,ADD=/hinzufügen|anlegen|anbinden|verbinden|add |connect/i;
function limit(ul){if(ul.dataset.all||ul.closest('.ic-nolimit'))return;
  const lis=[...ul.children].filter(li=>li.tagName==='LI'&&!li.classList.contains('ic-more'));let more=ul.querySelector(':scope>li.ic-more');
  if(lis.length<=N+2){lis.forEach(li=>{if(li.dataset.icHid){li.hidden=false;delete li.dataset.icHid}});if(more)more.remove();return}
  lis.forEach((li,i)=>{const h=i>=N;if(h&&!li.hidden){li.hidden=true;li.dataset.icHid='1'}else if(!h&&li.dataset.icHid){li.hidden=false;delete li.dataset.icHid}});
  const txt=t(`Weitere ${lis.length-N} zeigen`,`Show ${lis.length-N} more`);
  if(more&&more.textContent===txt&&more===ul.lastElementChild)return;if(more)more.remove();
  more=el('li','ic-more');const b=el('button','ic-lnk',txt);b.type='button';
  b.onclick=()=>{ul.dataset.all='1';ul.querySelectorAll(':scope>li[data-ic-hid]').forEach(li=>{li.hidden=false;delete li.dataset.icHid});more.remove()};more.appendChild(b);ul.appendChild(more)}
function tidy(root){root.querySelectorAll('ul.facts').forEach(limit);root.querySelectorAll('.ic-tabwrap').forEach(w=>w.icBadge&&w.icBadge());
  root.querySelectorAll('details:not(.guide):not(.adv):not(.ic-d)').forEach(d=>{const s=d.querySelector(':scope>summary');d.classList.add('ic-d');
    if(s&&(ADD.test(s.textContent)||/add$/.test(d.id||'')))d.classList.add('ic-add')})}
const box=$('profmodal');
if(box){let tm=0;new MutationObserver(()=>{if(tm)return;tm=setTimeout(()=>{tm=0;tidy(box)},40)}).observe(box,{childList:true,subtree:true});tidy(box)}
window.icTidy=tidy;
// Sicherheit is static markup: its sections become tabs once (Mein Notaus stays below them).
const sb=$('secbox');if(sb&&!sb.querySelector('.ic-tabwrap'))icAutoTabs(sb,'sec');
})();
