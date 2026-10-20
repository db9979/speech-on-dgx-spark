// Ich → Geteilt and the one dialog to share (geteilt.py, plan teilen-profile, Dominik 2026-10-20 „ok“): what the
// others share with this profile and what it shares, every kind on one page; taking back works at once. Names and
// titles come from other profiles: textContent only (ichteile.js builds every row that way).
let TEIL_ON=false,TEIL=null;
const TEIL_KIND={doc:[t('Dokument','Document'),'pdf'],cal:[t('Kalender','Calendar'),'cal'],list:[t('Liste','List'),'check']};
// the second level is called after its kind (Mitschreiben, Sehen + eintragen); documents have only „Sehen“ for now
const teilLevel=(kind,lv)=>lv==='see'?t('Sehen','See'):lv==='add'?(kind==='list'?t('Mitschreiben','Write along'):kind==='cal'?t('Sehen + eintragen','See + add'):t('Bearbeiten','Edit')):t('Aus','Off');
const teilMsg=(x,err)=>{const m=$('teilmsg');if(m){m.textContent=x||'';m.className='fh'+(err?' err':'')}};
async function showTeil(){const box=$('teilbox');if(!box)return;if(!PROFILE||!TEIL_ON){box.textContent='';return}
  if(!TEIL){box.textContent='';box.appendChild(icEl('div','fh',t('Einen Moment …','One moment …')))}
  const {r,d}=await apiTry('/api/profile/geteilt');
  if(!r.ok){box.textContent='';box.appendChild(icEl('div','fh err',errSay(r.status,d.detail,'')));return}
  TEIL=d;teilRender()}
// where a shared item opens: a document in Ich → Dokumente, a calendar or a list on its own page
function teilOpen(x){if(x.kind==='doc'){if(typeof ptab==='function'){meLast='docbox';ptab('docbox');if(typeof docOpen==='function')setTimeout(()=>docOpen(x.id),0)}return}
  const p=x.kind==='cal'?'cal':'listen';if($('profmodal').style.display==='grid'&&window.closeProf)closeProf();if(typeof goSec==='function')goSec(p)}
async function teilBack(kind,id,body){const {r,d}=await apiTry('/api/profile/teilen/'+kind+'/'+encodeURIComponent(id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!r.ok){teilMsg(t('Nicht zurückgezogen: ','Not taken back: ')+errSay(r.status,d.detail,''),true);return false}
  await showTeil();teilMsg(t('Zurückgezogen. Es ist dort sofort weg.','Taken back. It is gone there at once.'));if(kind==='doc'&&typeof showDocs==='function')showDocs();return true}
function teilRender(){const d=TEIL,box=$('teilbox'),E=icEl;if(!box||!d)return;box.textContent='';
  box.appendChild(E('h3','sec',t('Geteilt','Shared')));
  box.appendChild(E('div','intro',t('Was andere Profile mit dir teilen und was du teilst, an einem Ort. Geteiltes bleibt beim Besitzer; zurückziehen wirkt sofort. Gäste bekommen nie etwas Geteiltes.',
    'What other profiles share with you and what you share, in one place. Shared things stay with their owner; taking back works at once. Guests never get anything shared.')));
  const people=d.mine.reduce((n,x)=>n+x.people.length+(x.all?1:0),0);
  box.appendChild(icCard('spark',t('Geteilt','Shared'),t(`${d.theirs.length} mit dir geteilt · ${people} Freigaben von dir`,`${d.theirs.length} shared with you · ${people} shares of yours`),[]));
  const m=E('div','fh');m.id='teilmsg';box.appendChild(m);
  const theirs=()=>{if(!d.theirs.length)return icEmpty(t('Noch nichts. Teilt jemand ein Dokument, eine Liste oder einen Kalender mit dir, steht es hier.','Nothing yet. When someone shares a document, a list or a calendar with you, it is here.'));
    return icList(d.theirs.map(x=>{const k=TEIL_KIND[x.kind]||['',''];const lead=E('span','ic-cico');lead.appendChild(icSvg(k[1],16));
      const r=icRow(x.name,[x.who,k[0],x.all?t('für alle','for everyone'):teilLevel(x.kind,x.level),x.new?t('neu','new'):''].filter(Boolean).join(' · '),
        [icBtn('chev',t('Öffnen','Open'),()=>teilOpen(x))],lead);r.dataset.teilTheirs=x.kind+':'+x.id;r.onclick=()=>teilOpen(x);return r}))};
  const mine=()=>{const rows=[];
    for(const x of d.mine){const k=TEIL_KIND[x.kind]||['',''];
      if(x.all){const b=icBtn('x',t('Nicht mehr für alle','No longer for everyone'),()=>teilBack(x.kind,x.id,{all:false}));b.dataset.teilAll=x.id;
        rows.push(icRow(x.name,[k[0],t('Alle Profile','All profiles')].join(' · '),[b]))}
      for(const p of x.people){const b=icBtn('x',t('Zurückziehen','Take back'),()=>teilBack(x.kind,x.id,{to:p.id,level:''}));b.dataset.teilBack=x.kind+':'+x.id+':'+p.id;
        const acts=x.kind==='doc'?[icBtn('pen',t('Ändern','Change'),()=>shareOpen('doc',x.id)),b]:[b];
        rows.push(icRow(x.name,[k[0],p.name,teilLevel(x.kind,p.level)].join(' · '),acts))}}
    return rows.length?icList(rows):icEmpty(t('Du teilst noch nichts. Teilen geht am Dokument (Ich → Dokumente → Teilen), an einer Liste und an einem Kalender.','You share nothing yet. Share at a document (Me → Documents → Share), at a list and at a calendar.'))};
  box.appendChild(icTabs('teil',[{k:'theirs',label:t('Mit mir geteilt','Shared with me'),n:d.theirs.length,hot:d.new>0,body:theirs},
    {k:'mine',label:t('Von mir geteilt','Shared by me'),n:d.mine.length,body:mine}]));
  // Hinweis auf Geteiltes: a preference (on), the Spark tells unasked
  box.appendChild(icGroup(t('Hinweis','Note'),''));
  const sw=E('label','tgl'),inp=E('input');inp.type='checkbox';inp.id='teilnote';inp.checked=d.note!==false;sw.append(inp,E('i'));
  inp.onchange=async()=>{const {r,d:x}=await apiTry('/api/profile/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({'share_note':inp.checked})});
    if(!r.ok){teilMsg(errSay(r.status,x.detail,''),true);inp.checked=!inp.checked;return}teilMsg(t('Gespeichert.','Saved.'))};
  box.appendChild(icList([icRow(t('Mitteilung, wenn jemand etwas mit mir teilt','A note when someone shares something with me'),t('höchstens eine alle 10 Minuten, mehr werden gesammelt','at most one every 10 minutes, more are collected'),[sw])]))}
// the one dialog: every other profile with Aus / Sehen (/ the second level), and „Alle Profile“ where the kind has it
async function shareOpen(kind,id){const {r,d}=await apiTry('/api/profile/teilen/'+kind+'/'+encodeURIComponent(id));
  if(!r.ok){teilMsg(t('Nicht geöffnet: ','Not opened: ')+errSay(r.status,d.detail,''),true);if(typeof docErr==='function')docErr(new Error(errSay(r.status,d.detail,'')));return}
  const now={},was={};for(const p of d.people)if(p.level){now[p.id]=p.level;was[p.id]=p.level}
  let all=d.all;const lv=[['',t('Aus','Off')]].concat(d.levels.map(x=>[x,teilLevel(kind,x)]));
  const ov=document.createElement('div');ov.className='modal';ov.setAttribute('role','dialog');ov.setAttribute('aria-modal','true');ov.style.display='grid';
  const card=icEl('div','card modalcard teilcard');ov.appendChild(card);
  card.appendChild(icEl('h3','',t('„','"')+d.name+t('“ teilen','" share')));
  const find=icEl('input','teilfind');find.type='search';find.placeholder=t('Person suchen …','Find a person …');find.setAttribute('aria-label',t('Person suchen','Find a person'));find.autocomplete='off';
  const list=icEl('div','teilpeople');card.append(find,list);
  if(all!==null){const row=icEl('div','teilperson'),sw=icEl('label','tgl'),inp=icEl('input');inp.type='checkbox';inp.checked=!!all;inp.dataset.teilAllsw='1';sw.append(inp,icEl('i'));
    const lb=icEl('span','',t('Alle Profile','All profiles'));lb.appendChild(icEl('small','mut',' · '+t('wie „Für alle“, auch künftige Profile','like "For everyone", also future profiles')));
    row.append(lb,sw);inp.onchange=()=>{all=inp.checked};card.appendChild(row)}
  card.appendChild(icEl('div','fh',t('Der andere sieht es unter Ich → Geteilt, in seinen Dokumenten und in seiner Suche, solange du es teilst; für seinen Assistenten ist es nur Text. Gäste nie.',
    'The other one sees it under Me → Shared, in their documents and in their search while you share it; for their assistant it is only text. Guests never.')));
  const bar=icEl('div','row');bar.style.marginTop='10px';const go=icEl('button','b p',t('Speichern','Save'));go.type='button';go.id='teilgo';
  const no=icEl('button','b',t('Abbrechen','Cancel'));no.type='button';const msg=icEl('span','teilsharemsg');bar.append(go,no,msg);card.appendChild(bar);
  if(typeof codeLock==='function')codeLock(go,'confirm');
  document.body.appendChild(ov);
  const close=()=>{ov.remove();document.removeEventListener('keydown',key)},key=e=>{if(e.key==='Escape')close()};
  document.addEventListener('keydown',key);ov.onclick=e=>{if(e.target===ov)close()};no.onclick=close;
  const draw=()=>{const q=find.value.trim().toLowerCase();list.textContent='';
    const rows=d.people.filter(p=>!q||p.name.toLowerCase().includes(q)).sort((a,b)=>(was[b.id]?1:0)-(was[a.id]?1:0)||a.name.localeCompare(b.name));
    if(!rows.length){list.appendChild(icEl('div','mut',t('Niemand mit diesem Namen.','Nobody with this name.')));return}
    for(const p of rows){const row=icEl('div','teilperson'+(now[p.id]?' has':''));const nm=icEl('span','',p.name);
      if(!p.can)nm.appendChild(icEl('small','mut',' · '+t('kann Teilen nicht nutzen','cannot use sharing')));
      const seg=icEl('span','segc');seg.setAttribute('role','radiogroup');seg.setAttribute('aria-label',p.name);
      for(const [v,l] of lv){const b=icEl('button',(now[p.id]||'')===v?'on':'',l);b.type='button';b.dataset.to=p.id;b.dataset.lv=v;b.setAttribute('aria-pressed',(now[p.id]||'')===v?'true':'false');
        b.disabled=!p.can&&!!v;b.onclick=()=>{if(v)now[p.id]=v;else delete now[p.id];draw()};seg.appendChild(b)}
      row.append(nm,seg);list.appendChild(row)}};
  find.oninput=draw;draw();setTimeout(()=>find.focus(),0);
  go.onclick=async()=>{const ids=[...new Set([...Object.keys(was),...Object.keys(now)])].filter(x=>(was[x]||'')!==(now[x]||''));
    const jobs=ids.map(x=>({to:x,level:now[x]||''}));if(all!==null&&all!==d.all)jobs.push({all});
    go.disabled=true;
    for(const body of jobs){const {r,d:x}=await apiTry('/api/profile/teilen/'+kind+'/'+encodeURIComponent(id),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(!r.ok){msg.className='err';msg.textContent=t('Nicht geteilt: ','Not shared: ')+errSay(r.status,x.detail,'');go.disabled=false;return}
      if(body.to)was[body.to]=body.level}
    close();if(jobs.length){if(kind==='doc'&&typeof showDocs==='function')showDocs();if(TEIL)showTeil();
      if(typeof docMsg==='function')docMsg(t('Teilen gespeichert.','Sharing saved.'))}}}
