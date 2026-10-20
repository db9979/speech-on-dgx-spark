// Musik machen (musik.py, plan musik M1): Ich → Musik (a wish in, the song out, the own songs as a list with a
// player, details, download and delete) and the card under an answer while a song is made (SSE "musik").
// Wishes, descriptions and lyrics are the person's or the model's words: set with textContent only, never as HTML.
let MUSIK_ON=false;   // Musik machen (who.musik)
const muFile=(id,dl)=>'/api/musik/'+encodeURIComponent(id)+'/datei'+(dl?'?dl=1':'');
const muWhen=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}):'';
const muMb=b=>(b/1048576).toFixed(b<10485760?1:0).replace('.',L==='en'?'.':',')+' MB';
const muLen=s=>{s=Math.round(s||0);return s>=60?Math.floor(s/60)+':'+String(s%60).padStart(2,'0')+' min':s+' s'};
function muAudio(id){const a=document.createElement('audio');a.controls=true;a.preload='none';a.src=muFile(id);a.className='muplay';return a}
// follows one job until it ends; tick(job) on every look, stops when the element left the page (the first look waits
// until the card is in the answer, as in bilder.js)
function muFollow(jid,el,tick){const look=async()=>{if(!el.isConnected)return;const r=await apiTry('/api/musik/job/'+encodeURIComponent(jid));
    if(!r.r.ok){tick({state:'error',error:String(r.d.detail||'').slice(0,200)});return}
    tick(r.d);if(r.d.state==='wait'||r.d.state==='run')setTimeout(look,3000)};setTimeout(look,0)}
const MUSTATE={wait:['wartet auf eine Gesprächspause','waiting for a pause in the conversation'],run:['macht das Lied …','making the song …']};
function muJobLine(j){return schwerZeile(j)||(j.state==='error'?(L==='en'&&j.error_en?j.error_en:j.error)||t('Ging nicht.','Did not work.'):t(...(MUSTATE[j.state]||MUSTATE.wait)))}

// ---------------------------------------------------------------- the card in the chat
function musikCard(ev){const d=icEl('div','hcard mucard');const h=icEl('h4','',t('Lied','Song'));const st=icEl('div','hmsg mut',t('wartet …','waiting …'));
  st.setAttribute('role','status');const pr=icEl('div','hwhy',t('Beschreibung: ','Description: ')+String(ev.caption||''));d.append(h,st,pr);
  muFollow(ev.job,d,j=>{if(j.state==='done'&&j.song){st.remove();d.insertBefore(muAudio(j.song.id),pr);const row=icEl('div','row');
      const dl=document.createElement('a');dl.className='b';dl.href=muFile(j.song.id,1);dl.textContent=t('Herunterladen','Download');
      const go=icEl('button','b',t('Alle Lieder','All songs'));go.type='button';go.onclick=()=>openMe('musikbox');row.append(dl,go);d.appendChild(row)}
    else{st.textContent=muJobLine(j);st.classList.toggle('err',j.state==='error')}});
  return d}
// what stays under the answer in the history (profiles._att "musik"): the song itself (its job leads to it, also
// after a reload and on every device), else the description and a way to the songs
function musikAtt(a){const d=icEl('div','mem');d.appendChild(document.createTextNode('🎵 '+t('Lied: ','Song: ')+String(a.p||'').slice(0,120)+' '));
  const b=icEl('button','mlink',t('Anhören','Listen'));b.type='button';b.onclick=()=>openMe('musikbox');d.appendChild(b);
  if(a.j&&MUSIK_ON)muFollow(a.j,d,j=>{if(j.state==='done'&&j.song)d.appendChild(muAudio(j.song.id))});
  return d}

// ---------------------------------------------------------------- Ich → Musik
// Laid out like Dokumente and E-Mail (musik-seite/plan.md, Dominik 2026-10-19 "nach Empfehlung"): a head line with the
// count and the "⋯" menu, the form as a card (length as chips, singing as a switch), search and quick filters, the songs
// grouped by day as ld- rows with ▶ in front, the details beside (computer) or as their own page (phone). One player
// (MU.au) for the rows, the details and the bar "spielt gerade" at the bottom, so two songs never play at once.
const MU={d:null,sel:'',q:'',f:'all',play:'',au:null,ed:''};
const MULENS=[30,60,120,180,240,300,420,600];
const muDay=s=>{const d=new Date((s||0)*1000);d.setHours(0,0,0,0);return Math.round((new Date().setHours(0,0,0,0)-d)/864e5)};
// the time on the right of a row: today the clock, before that weekday and date
const muShort=s=>{if(!s)return '';const d=new Date(s*1000),loc=L==='en'?'en-GB':'de-DE';
  return muDay(s)<1?d.toLocaleTimeString(loc,{hour:'2-digit',minute:'2-digit'}):d.toLocaleDateString(loc,{weekday:'short',day:'2-digit',month:'2-digit'})};
const muGroup=s=>{const n=muDay(s);return n<1?t('Heute','Today'):n<2?t('Gestern','Yesterday'):n<7?t('Letzte 7 Tage','Last 7 days'):t('Älter','Older')};
const muSing=s=>s.sung?t('mit Gesang','with singing')+(s.language?' ('+s.language+')':''):t('instrumental','instrumental');
const muTitle=s=>s.wish||s.caption||t('Lied','Song');
const muClock=x=>{x=Math.max(0,Math.floor(x||0));return Math.floor(x/60)+':'+String(x%60).padStart(2,'0')};
function muIcon(on){const i=icEl('span','mu-ic'+(on?' pa':''));i.setAttribute('aria-hidden','true');return i}
function muAu(){if(MU.au)return MU.au;const a=MU.au=new Audio();a.preload='none';
  for(const e of ['play','pause','ended','timeupdate','loadedmetadata'])a.addEventListener(e,()=>{if(e==='ended')MU.play='';muSync()});return a}
// ▶/⏸ for one song: the same player everywhere; another song stops the one before
function muToggle(s){const a=muAu();if(MU.play===s.id){if(a.paused)a.play().catch(()=>{});else a.pause();return}
  MU.play=s.id;a.src=muFile(s.id);a.play().catch(()=>{});muSync()}
// draws the state of the one player into the rows, the details and the bar at the bottom
function muSync(){const box=$('musikbox');if(!box)return;const a=MU.au,on=id=>!!a&&MU.play===id&&!a.paused;
  box.querySelectorAll('[data-muplay]').forEach(b=>{const id=b.dataset.muplay;b.textContent='';b.appendChild(muIcon(on(id)));
    b.setAttribute('aria-label',on(id)?t('Anhalten','Pause'):t('Abspielen','Play'));b.classList.toggle('play',MU.play===id)});
  const cur=a&&MU.play?a.currentTime:0,dur=a&&isFinite(a.duration)?a.duration:0;
  box.querySelectorAll('.mu-player').forEach(p=>{const mine=p.dataset.id===MU.play;p.querySelector('.mu-t').textContent=muClock(mine?cur:0);
    const r=p.querySelector('input');if(mine&&dur){r.max=String(Math.floor(dur));if(!r.matches(':active'))r.value=String(Math.floor(cur))}else if(!mine)r.value='0'});
  const bar=box.querySelector('.mu-mini');if(bar){const s=MU.d&&MU.d.songs.find(x=>x.id===MU.play);
    bar.hidden=!s||MU.sel===MU.play&&!!box.querySelector('.ld-box.ld-sel,.ld-split:has(>.ld-detail:not([hidden]))');
    if(s){bar.querySelector('b').textContent=muTitle(s);bar.querySelector('small').textContent=muClock(cur)}}}

async function showMusik(){const box=$('musikbox');if(!box)return;if(!PROFILE||!MUSIK_ON){box.textContent='';if(MU.au)MU.au.pause();return}
  const r=await apiTry('/api/musik');box.textContent='';
  if(!r.r.ok){box.appendChild(icEmpty(String(r.d.detail||t('Gerade nicht erreichbar.','Not reachable right now.'))));return}
  const d=MU.d=r.d,lim=d.limits;
  const wrap=icEl('div','ld-box mu');box.appendChild(wrap);
  // the head: count, space and today's songs, the "⋯" menu
  const head=icEl('div','ld-head'),hl=icEl('div','mu-hl');hl.append(icEl('b','',t(`${d.songs.length} Lieder`,`${d.songs.length} songs`)),
    icEl('span','mut',' · '+t(`${muMb(d.used)} von ${lim.store_mb} MB · heute ${d.today} von ${lim.day}`,`${muMb(d.used)} of ${lim.store_mb} MB · today ${d.today} of ${lim.day}`)));
  head.appendChild(hl);const ed=d.edit||{on:false};const menu=[];if(ed.on)menu.push({label:t('Eigene Datei hochladen','Upload an own file'),act:()=>{up.hidden=false;up.querySelector('input').focus()}});
  if(d.songs.length)menu.push({label:t('Alle Lieder löschen','Delete all songs'),danger:true,act:muClear});if(menu.length)head.appendChild(icMenu(menu));wrap.appendChild(head);
  const up=muUpload(ed);
  // a new song: the wish grows with its text (feld.js), the length as chips, singing as a switch
  const f=icEl('div','mu-new');const ta=document.createElement('textarea');ta.id='muwish';ta.rows=2;ta.maxLength=lim.wish;
  ta.setAttribute('aria-label',t('Was für Musik soll ich machen?','What kind of music shall I make?'));
  ta.placeholder=t('Was für Musik soll ich machen? z. B. Ruhiges Klavierstück mit Streichern zum Einschlafen','What kind of music shall I make? e.g. Calm piano piece with strings for falling asleep');
  let secs=lim.default_s;const lens=icEl('div','ld-chips mu-len');lens.setAttribute('role','group');lens.setAttribute('aria-label',t('Länge','Length'));
  const pickLen=v=>{secs=v;lens.querySelectorAll('button').forEach(b=>{const o=+b.dataset.s===v;b.classList.toggle('on',o);b.setAttribute('aria-pressed',String(o))})};
  for(const s of MULENS.filter(s=>s<=lim.max_s)){const b=icEl('button','ld-chip',muLen(s).replace(' min',''));b.type='button';b.dataset.s=s;b.onclick=()=>pickLen(s);lens.appendChild(b)}
  const sungL=icEl('label','tgl');const sung=document.createElement('input');sung.type='checkbox';sung.id='musung';sungL.append(sung,icEl('i'),icEl('span','',t('Mit Gesang','With singing')));
  const lang=document.createElement('select');lang.id='mulang';lang.setAttribute('aria-label',t('Sprache','Language'));
  for(const k of d.langs){const o=document.createElement('option');o.value=k;o.textContent=k;o.selected=k===(L==='en'?'en':'de');lang.appendChild(o)}
  const lyL=icEl('label','',t('Liedtext','Lyrics'));lyL.htmlFor='mulyrics';const ly=document.createElement('textarea');ly.id='mulyrics';ly.rows=5;ly.maxLength=lim.lyrics;
  ly.placeholder=t('[verse]\nErste Strophe …\n[chorus]\nRefrain …','[verse]\nFirst verse …\n[chorus]\nChorus …');
  const lyBox=icEl('div','mu-lyr');lyBox.append(lyL,ly);const showSung=()=>{lyBox.hidden=!sung.checked;lang.hidden=!sung.checked};sung.onchange=showSung;
  const go=icEl('button','b p',t('Lied machen','Make the song'));go.type='button';go.id='mugo';ta.dataset.senden='mugo';
  const msg=icEl('div','fh');msg.id='mumsg';msg.setAttribute('role','status');
  const opts=icEl('div','mu-opts');opts.append(lens,sungL,lang,icEl('span','mu-sp'),go);
  f.append(ta,opts,lyBox,msg,icEl('div','fh',t('Ohne Gesang wird es instrumental. Jedes Lied ist als KI-erzeugt gekennzeichnet; Sexuelles, Gewalt, Hass und „im Stil von“ macht der Spark nicht.',
    'Without singing it is instrumental. Every song is marked as made by an AI; the Spark makes nothing sexual, violent, hateful or "in the style of".')));
  wrap.append(f,up);pickLen(lim.default_s);showSung();
  go.onclick=async()=>{const w=ta.value.trim();if(!w){ta.focus();return}if(sung.checked&&!ly.value.trim()){ly.focus();return}
    go.disabled=true;msg.textContent=t('wird angenommen …','being accepted …');
    const r2=await apiTry('/api/musik',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({wunsch:w,sekunden:secs,gesang:sung.checked,sprache:lang.value,liedtext:sung.checked?ly.value:''})});
    if(!r2.r.ok){msg.textContent=String(r2.d.detail||t('Ging nicht.','Did not work.'));go.disabled=false;return}
    ta.value='';ly.value='';showMusik()};
  // „Nochmal machen“: the form with the wish, length, singing and lyrics of a song; nothing is sent before „Lied machen“
  const again=s=>{ta.value=s.wish||s.caption||'';const l=MULENS.filter(x=>x<=lim.max_s).reduce((a,x)=>Math.abs(x-(s.length_s||0))<Math.abs(a-(s.length_s||0))?x:a,lim.default_s);
    pickLen(l);sung.checked=!!s.sung;if(s.language&&[...lang.options].some(o=>o.value===s.language))lang.value=s.language;ly.value=s.lyrics||'';showSung();
    MU.sel='';wrap.classList.remove('ld-sel');const det=wrap.querySelector('.ld-detail');if(det)det.hidden=true;
    f.scrollIntoView({block:'nearest'});ta.focus();ta.dispatchEvent(new Event('input'))};
  // songs being made: on top of the list, each with its line (place in the queue, about how long)
  const jobs=d.jobs.filter(j=>j.state==='wait'||j.state==='run');if(jobs.length)go.disabled=true;
  if(!d.songs.length&&!jobs.length){wrap.appendChild(icEmpty(t('Noch keine Lieder.','No songs yet.')));return}
  // Fassungen: a version lists under its song (root); one whose song was deleted stands on its own
  const ids=new Set(d.songs.map(x=>x.id)),rootOf=x=>x.root&&ids.has(x.root)?x.root:x.id,fam=id=>d.songs.filter(x=>rootOf(x)===id);
  const roots=d.songs.filter(x=>rootOf(x)===x.id),nUp=roots.filter(x=>x.kind==='upload').length,nEd=roots.filter(x=>fam(x.id).length>1).length;
  const tools=icEl('div','ld-tools'+(d.songs.length<6?' few':''));const q=document.createElement('input');q.type='search';q.value=MU.q;
  q.placeholder=t('Lieder suchen','Search songs');q.setAttribute('aria-label',t('Lieder suchen','Search songs'));
  const chips=icEl('div','ld-chips');const nSung=roots.filter(s=>s.sung).length;
  const fs=[['all','Alle','All',roots.length],['sung','Mit Gesang','With singing',nSung],['inst','Instrumental','Instrumental',roots.length-nSung]];
  if(nUp)fs.push(['up','Hochgeladen','Uploaded',nUp]);if(nEd)fs.push(['ed','Bearbeitet','Edited',nEd]);if(!fs.some(x=>x[0]===MU.f))MU.f='all';
  for(const [k,de,en,n] of fs){
    const b=icEl('button','ld-chip'+(MU.f===k?' on':''),t(de,en));b.type='button';b.dataset.f=k;b.setAttribute('aria-pressed',String(MU.f===k));b.appendChild(icEl('b','',' '+n));
    b.onclick=()=>{MU.f=k;chips.querySelectorAll('button').forEach(x=>{const o=x.dataset.f===k;x.classList.toggle('on',o);x.setAttribute('aria-pressed',String(o))});paint()};chips.appendChild(b)}
  tools.append(q,chips);wrap.appendChild(tools);
  const split=icEl('div','ld-split'),list=icEl('div','ld-list'),det=icEl('div','ld-detail');det.hidden=true;split.append(list,det);wrap.appendChild(split);
  const bar=icEl('div','mu-mini');bar.hidden=true;const bb=icEl('button','ld-ico mu');bb.type='button';bb.dataset.muplay='';
  bb.onclick=()=>{const s=d.songs.find(x=>x.id===MU.play);if(s)muToggle(s)};const bt=icEl('button','mu-mt');bt.type='button';bt.append(icEl('b'),icEl('small','mut'));
  bt.onclick=()=>{const s=d.songs.find(x=>x.id===MU.play);if(s)open(s)};bar.append(bb,bt);wrap.appendChild(bar);
  const open=s=>{MU.sel=s.id;list.querySelectorAll('.ld-row').forEach(x=>x.classList.toggle('on',x.dataset.id===rootOf(s)));wrap.classList.add('ld-sel');det.hidden=false;det.textContent='';
    const back=icEl('button','b ld-back',t('‹ Alle Lieder','‹ All songs'));back.type='button';back.onclick=()=>{MU.sel='';det.hidden=true;wrap.classList.remove('ld-sel');paint()};
    // the player: ▶/⏸, the time and a slider to jump; it plays through MU.au like the rows
    const pl=icEl('div','mu-player');pl.dataset.id=s.id;const pb=icEl('button','mu-pb');pb.type='button';pb.dataset.muplay=s.id;pb.onclick=()=>muToggle(s);
    const rg=document.createElement('input');rg.type='range';rg.min='0';rg.max=String(Math.round(s.length_s||0));rg.value='0';rg.setAttribute('aria-label',t('Stelle im Lied','Position in the song'));
    rg.oninput=()=>{if(MU.play!==s.id)muToggle(s);const a=muAu();if(isFinite(a.duration))a.currentTime=+rg.value};
    pl.append(pb,icEl('small','mu-t','0:00'),rg,icEl('small','',muClock(s.length_s)));
    const facts=document.createElement('dl');facts.className='ld-facts';
    const fact=(k,v)=>{if(!v)return;facts.append(icEl('dt','',k),icEl('dd','',String(v)))};
    if(s.kind==='edit'){const p=d.songs.find(x=>x.id===s.von);fact(t('Geändert','Changed'),muLabel(s)+(p?' · '+t('aus ','from ')+(p.kind==='edit'?muLabel(p):t('dem Original','the original')):''))}
    fact(s.kind==='upload'?t('Hochgeladen','Uploaded'):s.kind==='edit'?t('Bearbeitet','Edited'):t('Gemacht','Made'),muWhen(s.t));fact(t('Länge','Length'),muLen(s.length_s)+' · '+muSing(s));fact(t('Größe','Size'),muMb(s.bytes));
    fact(t('Tempo und Tonart','Tempo and key'),[s.bpm?s.bpm+' BPM':'',s.key||''].filter(Boolean).join(' · '));
    fact(t('Dauer','Time'),(s.seconds!=null?String(s.seconds).replace('.',L==='en'?'.':',')+' s':'')+(s.model?(s.seconds!=null?' · ':'')+s.model:''));
    const acts=icEl('div','ld-acts');const dl=document.createElement('a');dl.className='b p';dl.href=muFile(s.id,1);dl.textContent=t('Herunterladen','Download');
    const ag=icEl('button','b',t('Nochmal machen','Make it again'));ag.type='button';ag.onclick=()=>again(s);
    const del=icEl('button','b ic-red',t('Löschen','Delete'));del.type='button';del.onclick=async()=>{if(!confirm(t('Dieses Lied löschen?','Delete this song?')))return;
      const r3=await apiTry('/api/musik/'+encodeURIComponent(s.id),{method:'DELETE'});if(!r3.r.ok){alert(String(r3.d.detail||''));return}
      if(MU.play===s.id&&MU.au){MU.au.pause();MU.play=''}MU.sel='';showMusik()};
    acts.append(dl);if(s.kind!=='upload')acts.append(ag);
    if(ed.on&&s.kind==='edit'&&rootOf(s)!==s.id){const own=icEl('button','b',t('Als eigenes Lied','As a song of its own'));own.type='button';
      own.onclick=async()=>{const r3=await apiTry('/api/musik/'+encodeURIComponent(s.id)+'/eigenes',{method:'POST'});if(!r3.r.ok){alert(String(r3.d.detail||''));return}showMusik()};acts.appendChild(own)}
    if(ed.on&&!s.heard){const hr=icEl('button','b',t('Tempo und Tonart erkennen','Detect tempo and key'));hr.type='button';hr.disabled=jobs.length>0;
      hr.onclick=async()=>{hr.disabled=true;const r3=await apiTry('/api/musik/'+encodeURIComponent(s.id)+'/erkennen',{method:'POST'});if(!r3.r.ok){alert(String(r3.d.detail||''));hr.disabled=false;return}showMusik()};acts.appendChild(hr)}
    acts.appendChild(del);det.append(back,icEl('h3','',muTitle(s)),pl,facts,acts);
    if(s.kind==='edit')det.insertBefore(icEl('div','mut mu-lab',muLabel(s)),pl);
    if(ed.on)det.appendChild(muEditor(s,ed,lim,jobs.length>0));
    // the versions of this song: ▶ in each row plays through the one player, so original and version can be heard in turn
    const others=fam(rootOf(s)).filter(x=>x.id!==s.id);if(others.length){const fv=icEl('div','mu-fam');fv.appendChild(icEl('h4','',t(`Fassungen (${others.length+1})`,`Versions (${others.length+1})`)));
      for(const x of others.sort((a,b)=>(a.t||0)-(b.t||0))){const row=icEl('div','ld-row');row.dataset.id=x.id;row.tabIndex=0;row.setAttribute('role','button');
        const pb=icEl('button','ld-ico mu');pb.type='button';pb.dataset.muplay=x.id;pb.onclick=e=>{e.stopPropagation();muToggle(x)};
        const mid=icEl('span','ld-mid');mid.append(icEl('b','',x.kind==='edit'?muLabel(x):t('Original','Original')),icEl('small','',muLen(x.length_s)));
        const right=icEl('span','ld-right');right.appendChild(icEl('span','ld-when',muShort(x.t)));row.append(pb,mid,right);
        row.onclick=()=>open(x);row.onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&e.target===row){e.preventDefault();open(x)}};fv.appendChild(row)}
      det.appendChild(fv)}
    // the model's description (mostly long and English) and the lyrics: folded, open on a tap
    const more=(k,v,cls)=>{if(!v)return;const x=document.createElement('details');x.className='mu-more';x.append(icEl('summary','',k),icEl(cls||'p',cls?'mulyr':'',v));det.appendChild(x)};
    more(t('Beschreibung des Modells','Description by the model'),s.caption!==s.wish?s.caption:'');more(t('Liedtext','Lyrics'),s.lyrics,'pre');muSync()};
  // the list: jobs on top, then the songs by day; the search looks in wish, description and lyrics
  const paint=()=>{list.textContent='';const ql=MU.q.trim().toLowerCase();
    if(jobs.length){const g=icEl('div','ld-grp');g.append(icEl('span','',t('Wird gemacht','Being made')),icEl('span','',String(jobs.length)));list.appendChild(g)}
    for(const j of jobs){const row=icEl('div','ld-row mu-run');const ic=icEl('span','ld-ico','♪');ic.setAttribute('aria-hidden','true');const mid=icEl('span','ld-mid');
      const sm=icEl('small','',muJobLine(j));sm.setAttribute('role','status');mid.append(icEl('b','',j.caption||t('Lied','Song')),sm);row.append(ic,mid);list.appendChild(row);
      muFollow(j.id,sm,x=>{sm.textContent=muJobLine(x)+' · '+muLen(x.length_s)+' · '+(x.sung?t('mit Gesang','with singing'):t('instrumental','instrumental'));
        if(x.state==='done'){MU.sel=x.song.id;showMusik()}else if(x.state==='error')go.disabled=false})}
    const pass=s=>MU.f==='all'||MU.f==='up'?MU.f==='all'||s.kind==='upload':MU.f==='ed'?fam(s.id).length>1:(MU.f==='sung')===!!s.sung;
    const shown=roots.filter(s=>pass(s)&&(!ql||fam(s.id).some(x=>[x.wish,x.caption,x.lyrics,muLabel(x)].some(v=>String(v||'').toLowerCase().includes(ql)))));
    let grp='';for(const s of shown){const g=muGroup(s.t);if(g!==grp){grp=g;const h=icEl('div','ld-grp');h.append(icEl('span','',g),icEl('span','',String(shown.filter(x=>muGroup(x.t)===g).length)));list.appendChild(h)}
      const row=icEl('div','ld-row'+(MU.sel&&fam(s.id).some(x=>x.id===MU.sel)?' on':''));row.dataset.id=s.id;row.tabIndex=0;row.setAttribute('role','button');
      const pb=icEl('button','ld-ico mu');pb.type='button';pb.dataset.muplay=s.id;pb.onclick=e=>{e.stopPropagation();muToggle(s)};
      const mid=icEl('span','ld-mid');const b=icEl('b','',muTitle(s));b.title=muTitle(s);const nv=fam(s.id).length;
      mid.append(b,icEl('small','',muLen(s.length_s)+' · '+(s.kind==='upload'?t('hochgeladen','uploaded'):muSing(s))+(nv>1?' · '+t(`${nv} Fassungen`,`${nv} versions`):'')));
      const right=icEl('span','ld-right');right.appendChild(icEl('span','ld-when',muShort(s.t)));row.append(pb,mid,right);
      row.onclick=()=>open(s);row.onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&e.target===row){e.preventDefault();open(s)}};list.appendChild(row)}
    if(!shown.length&&d.songs.length)list.appendChild(icEl('div','mut ld-empty',t('Nichts passt zu Suche und Filter.','Nothing fits the search and filter.')));
    muSync()};
  q.oninput=()=>{MU.q=q.value;paint()};paint();
  const pick=d.songs.find(s=>s.id===MU.sel);if(pick)open(pick)}
async function muClear(){if(!confirm(t('Alle deine Lieder löschen? Das lässt sich nicht rückgängig machen.','Delete all your songs? This cannot be undone.')))return;
  const r=await apiTry('/api/musik',{method:'DELETE'});if(!r.r.ok){alert(String(r.d.detail||''));return}if(MU.au){MU.au.pause();MU.play=''}MU.sel='';showMusik()}

// ---------------------------------------------------------------- Musik bearbeiten
// (musik-experte/plan.md, Dominik 2026-10-20 „alles nach Empfehlung“) in the details of a song: the wave with the chosen
// part, the kind as chips with its few fields. With the music model a job (up to three suggestions, each a new version),
// cutting and tempo at once; the original always stays. The panel checks every number again with fixed rules.
const MUARTS=[['abschnitt','Abschnitt neu','Part anew',1],['verlaengern','Verlängern','Extend',1],['richtung','Musikrichtung','Genre',1],
  ['remix','Remix','Remix',1],['text','Text ändern','Change lyrics',1],['schneiden','Schneiden & Blenden','Cut & fade',0],['tempo','Tempo & Tonart','Tempo & key',0]];
// Text ändern (Dominik 2026-10-20 „texte anpassen strophen hinzufügen und verschieben … mit drag and drop“): the lyrics
// as parts ([verse], [chorus], …), each with its kind and text; moved by dragging the handle (mouse and finger, pointer
// events) or with ↑/↓, added and removed; then the song is made anew from them
const MUPARTS=[['verse','Strophe','Verse'],['chorus','Refrain','Chorus'],['pre-chorus','Vor-Refrain','Pre-chorus'],['bridge','Bridge','Bridge'],
  ['intro','Intro','Intro'],['outro','Outro','Outro'],['instrumental','Instrumental','Instrumental']];
function muParts(text){const out=[];let cur=null;for(const line of String(text||'').split('\n')){const m=line.trim().match(/^\[([a-z -]{2,20})\]$/i);
    if(m){cur={tag:m[1].toLowerCase(),text:''};out.push(cur);continue}if(!cur){if(!line.trim())continue;cur={tag:'verse',text:''};out.push(cur)}cur.text+=(cur.text?'\n':'')+line}
  for(const x of out)x.text=x.text.trim();return out}
const muJoin=parts=>parts.map(x=>'['+x.tag+']\n'+x.text.trim()).join('\n\n');
function muLyricsEditor(parts){const box=icEl('div','mu-parts');box.setAttribute('role','list');
  const draw=()=>{box.textContent='';parts.forEach((x,i)=>{const row=icEl('div','mu-part');row.setAttribute('role','listitem');row.dataset.i=i;
    const h=icEl('button','mu-grip','⠿');h.type='button';h.title=t('Ziehen zum Verschieben','Drag to move');h.setAttribute('aria-label',t('Verschieben','Move'));
    h.onpointerdown=e=>{e.preventDefault();h.setPointerCapture(e.pointerId);row.classList.add('drag');let to=i;
      // k: the place among the parts the pointer is over (before part k, or at the end); to: the part's new index
      h.onpointermove=ev=>{const rows=[...box.querySelectorAll('.mu-part')];let k=rows.findIndex(r=>{const b=r.getBoundingClientRect();return ev.clientY<b.top+b.height/2});
        if(k<0)k=rows.length;to=k>i?k-1:k;rows.forEach((r,n)=>r.classList.toggle('drop',n===k&&to!==i))};
      h.onpointerup=h.onpointercancel=()=>{h.onpointermove=h.onpointerup=h.onpointercancel=null;row.classList.remove('drag');
        if(to!==i&&to>=0){const [m]=parts.splice(i,1);parts.splice(to,0,m)}draw()}};
    const sel=document.createElement('select');sel.setAttribute('aria-label',t('Art des Teils','Kind of part'));
    for(const [k,de,en] of MUPARTS.concat(MUPARTS.some(p=>p[0]===x.tag)?[]:[[x.tag,x.tag,x.tag]])){const o=document.createElement('option');o.value=k;o.textContent=t(de,en);o.selected=k===x.tag;sel.appendChild(o)}
    sel.onchange=()=>{x.tag=sel.value};const ta=document.createElement('textarea');ta.rows=Math.min(8,Math.max(2,x.text.split('\n').length));ta.value=x.text;
    ta.setAttribute('aria-label',t('Text des Teils','Text of the part'));ta.oninput=()=>{x.text=ta.value};
    const mv=(d,lbl,ic)=>{const b=icEl('button','b mu-mv',ic);b.type='button';b.setAttribute('aria-label',lbl);b.disabled=i+d<0||i+d>=parts.length;
      b.onclick=()=>{const [m]=parts.splice(i,1);parts.splice(i+d,0,m);draw()};return b};
    const del=icEl('button','b mu-mv ic-red','✕');del.type='button';del.setAttribute('aria-label',t('Teil entfernen','Remove part'));del.onclick=()=>{parts.splice(i,1);draw()};
    const top=icEl('div','mu-part-h');top.append(h,sel,icEl('span','mu-sp'),mv(-1,t('Nach oben','Up'),'↑'),mv(1,t('Nach unten','Down'),'↓'),del);row.append(top,ta);box.appendChild(row)});
    const add=icEl('div','mu-opts');for(const [k,de,en] of MUPARTS.slice(0,4)){const b=icEl('button','b','+ '+t(de,en));b.type='button';b.onclick=()=>{parts.push({tag:k,text:''});draw();
      const l=box.querySelectorAll('textarea');if(l.length)l[l.length-1].focus()};add.appendChild(b)}box.appendChild(add)};
  draw();return box}
const muLabel=s=>{const l=s.label||[];return (L==='en'?l[1]:l[0])||l[0]||''};
const muSec=x=>(Math.round((x||0)*10)/10).toFixed(1).replace('.',L==='en'?'.':',');
function muField(lbl,el){const w=icEl('label','mu-f');w.append(icEl('span','',lbl),el);return w}
function muNumber(v,lo,hi,step){const i=document.createElement('input');i.type='number';i.className='num';i.min=String(lo);i.max=String(hi);i.step=String(step||1);i.value=String(v);return i}
function muChips(items,cur,pick,label){const c=icEl('div','ld-chips');c.setAttribute('role','group');c.setAttribute('aria-label',label);
  const set=k=>{c.querySelectorAll('button').forEach(b=>{const o=b.dataset.k===k;b.classList.toggle('on',o);b.setAttribute('aria-pressed',String(o))});pick(k)};
  for(const [k,de,en] of items){const b=icEl('button','ld-chip',t(de,en));b.type='button';b.dataset.k=k;b.onclick=()=>set(b.dataset.k===c.dataset.cur&&c.dataset.free?'':k);c.appendChild(b)}
  if(cur)set(cur);return c}
// the wave: the song decoded in the browser (nothing leaves the page), as peaks on a canvas; dragging picks the part
async function muWave(s,w){w.done=true;try{const r=await api(muFile(s.id));if(!r.ok)throw 0;const buf=await r.arrayBuffer();
    const C=window.OfflineAudioContext||window.webkitOfflineAudioContext;const a=await new C(1,1,44100).decodeAudioData(buf);
    const ch=a.getChannelData(0),n=400,step=Math.max(1,Math.floor(ch.length/n)),pk=new Float32Array(n);
    for(let i=0;i<n;i++){let m=0;const o=i*step;for(let k=0;k<step&&o+k<ch.length;k+=4){const v=Math.abs(ch[o+k]);if(v>m)m=v}pk[i]=m}w.peaks=pk;w.draw()}
  catch(e){w.cv.hidden=true}}
function muEditor(s,ed,lim,busy){const box=document.createElement('details');box.className='mu-edit';box.open=MU.ed===s.id;
  box.appendChild(icEl('summary','',t('Bearbeiten','Edit')));const len=s.length_s||0,R={a:0,b:len};
  // the part of the song: wave, from and to (also typed)
  const w={done:false,peaks:null,cv:document.createElement('canvas')};w.cv.className='mu-wave';w.cv.setAttribute('role','img');
  w.cv.setAttribute('aria-label',t('Welle des Liedes mit dem gewählten Bereich','Wave of the song with the chosen part'));
  const va=muNumber(0,0,len,0.5),vb=muNumber(Math.round(len*10)/10,0,len,0.5);va.setAttribute('aria-label',t('Von Sekunde','From second'));vb.setAttribute('aria-label',t('Bis Sekunde','To second'));
  const rl=icEl('small','mut');
  const show=()=>{va.value=String(Math.round(R.a*10)/10);vb.value=String(Math.round(R.b*10)/10);rl.textContent=t(`Bereich ${muSec(R.a)}–${muSec(R.b)} s (${muSec(R.b-R.a)} s)`,`Part ${muSec(R.a)}–${muSec(R.b)} s (${muSec(R.b-R.a)} s)`);w.draw()};
  w.draw=()=>{const cv=w.cv,dpr=window.devicePixelRatio||1,W=Math.max(1,cv.clientWidth||300),H=64;cv.width=W*dpr;cv.height=H*dpr;const g=cv.getContext('2d');if(!g)return;
    g.setTransform(dpr,0,0,dpr,0,0);g.clearRect(0,0,W,H);const css=getComputedStyle(cv),acc=css.getPropertyValue('--acc').trim()||'#2f6fde',mut=css.getPropertyValue('--mut').trim()||'#888';
    if(len>0){g.fillStyle=acc;g.globalAlpha=.16;g.fillRect(R.a/len*W,0,(R.b-R.a)/len*W,H);g.globalAlpha=1}
    const pk=w.peaks;if(!pk)return;const n=pk.length;let top=0;for(const v of pk)top=Math.max(top,v);top=top||1;
    for(let i=0;i<n;i++){const x=i/n*W,h=Math.max(1,pk[i]/top*(H-6)),sec=i/n*len;g.fillStyle=sec>=R.a&&sec<=R.b?acc:mut;g.fillRect(x,(H-h)/2,Math.max(1,W/n-1),h)}};
  const at=e=>{const r=w.cv.getBoundingClientRect();return Math.min(len,Math.max(0,(e.clientX-r.left)/Math.max(1,r.width)*len))};
  let from=null;w.cv.onpointerdown=e=>{from=at(e);w.cv.setPointerCapture(e.pointerId);R.a=from;R.b=Math.min(len,from+1);show()};
  w.cv.onpointermove=e=>{if(from===null)return;const x=at(e);R.a=Math.min(from,x);R.b=Math.max(from,x);show()};
  w.cv.onpointerup=()=>{from=null;if(R.b-R.a<1){R.b=Math.min(len,R.a+1);R.a=Math.min(R.a,R.b-1)}show()};
  const typed=()=>{let a=+va.value,b=+vb.value;if(!isFinite(a)||!isFinite(b))return;a=Math.max(0,Math.min(len,a));b=Math.max(0,Math.min(len,b));if(b<a)[a,b]=[b,a];R.a=a;R.b=b>=len-0.05?len:b;show()};
  va.onchange=typed;vb.onchange=typed;const all=icEl('button','b',t('Ganzes Lied','Whole song'));all.type='button';all.onclick=()=>{R.a=0;R.b=len;show()};
  const rng=icEl('div','mu-rng');rng.append(muField(t('Von (s)','From (s)'),va),muField(t('Bis (s)','To (s)'),vb),all,rl);
  // the kind and its fields
  let art=MUARTS.some(x=>x[0]===MU.art)?MU.art:'abschnitt';const opt=icEl('div','mu-opt');let get=()=>null;
  const msg=icEl('div','fh');msg.setAttribute('role','status');
  const go=icEl('button','b p','');go.type='button';
  const many=()=>{const sel=document.createElement('select');sel.setAttribute('aria-label',t('Vorschläge','Suggestions'));
    for(const n of [1,2,3]){const o=document.createElement('option');o.value=String(n);o.textContent=t(n===1?'1 Vorschlag':n+' Vorschläge',n===1?'1 suggestion':n+' suggestions');sel.appendChild(o)}return sel};
  const near=v=>{const r=document.createElement('input');r.type='range';r.min='0';r.max=String((ed.near||5)-1);r.value=String(v);r.setAttribute('aria-label',t('Frei bis nah am Original','Free to close to the original'));
    const f=icEl('div','mu-near');f.append(icEl('small','mut',t('frei','free')),r,icEl('small','mut',t('nah am Original','close to the original')));return [f,r]};
  const text=(ph,most)=>{const x=document.createElement('textarea');x.rows=2;x.maxLength=most||300;x.placeholder=ph;x.setAttribute('aria-label',ph);return x};
  const paint=()=>{MU.art=art;opt.textContent='';msg.textContent='';const model=MUARTS.find(x=>x[0]===art)[3];rng.hidden=!(art==='abschnitt'||art==='schneiden');
    go.textContent=model?t('Vorschläge machen','Make suggestions'):t('Neue Fassung','New version');go.disabled=model&&busy;
    if(model&&busy)msg.textContent=t('Erst wenn das laufende Lied fertig ist.','Once the running song is done.');
    if(art==='abschnitt'){const wi=text(t('Was soll in dem Teil anders sein? z. B. ruhiger, mit Gitarrensolo','What should be different in that part? e.g. calmer, with a guitar solo'));const n=many();
      opt.append(wi,muField(t('Vorschläge','Suggestions'),n));get=()=>{if(!wi.value.trim()){wi.focus();return null}return {von:R.a,bis:R.b,wunsch:wi.value,vorschlaege:+n.value}}}
    else if(art==='verlaengern'){let wo='hinten';const c=muChips([['vorne','Vorne','At the front'],['hinten','Hinten','At the end']],wo,k=>{wo=k},t('Wo','Where'));
      const sk=muNumber(30,5,ed.max_add||120,5),wi=text(t('Wie soll es weitergehen? (frei lassen: wie bisher)','How should it go on? (leave empty: as before)'));const n=many();
      opt.append(c,muField(t('Sekunden länger','Seconds longer'),sk),wi,muField(t('Vorschläge','Suggestions'),n));
      get=()=>({wo,sekunden:+sk.value,wunsch:wi.value,vorschlaege:+n.value})}
    else if(art==='richtung'){let g='';const c=muChips((ed.genres||[]).map(([k,de,en])=>[k,de,en]),'',k=>{g=k},t('Musikrichtung','Genre'));c.dataset.free='1';
      c.addEventListener('click',()=>{c.dataset.cur=g});
      const wo=document.createElement('input');wo.maxLength=300;wo.placeholder=t('oder eigene Worte, z. B. Bossa Nova mit Flöte','or own words, e.g. bossa nova with flute');wo.setAttribute('aria-label',wo.placeholder);
      const [nf,nr]=near(2);const bpm=muNumber('',40,220,1);bpm.placeholder=s.bpm?String(s.bpm):'';const n=many();
      opt.append(c,wo,nf,muField(t('Tempo (BPM, frei lassen: wie bisher)','Tempo (BPM, leave empty: as before)'),bpm),muField(t('Vorschläge','Suggestions'),n));
      get=()=>{if(!g&&!wo.value.trim()){wo.focus();msg.textContent=t('Bitte eine Musikrichtung wählen.','Please pick a genre.');return null}
        const b={richtung:g,worte:wo.value,nah:+nr.value,vorschlaege:+n.value};if(bpm.value)b.bpm=Math.round(+bpm.value);return b}}
    else if(art==='remix'){const wi=text(t('Wie soll der Remix klingen? (frei lassen: überraschen)','How should the remix sound? (leave empty: surprise me)'));const [nf,nr]=near(3);const n=many();
      opt.append(wi,nf,muField(t('Vorschläge','Suggestions'),n));get=()=>({wunsch:wi.value,nah:+nr.value,vorschlaege:+n.value})}
    else if(art==='text'){const parts=muParts(s.lyrics);if(!parts.length)parts.push({tag:'verse',text:''},{tag:'chorus',text:''});
      const lang=document.createElement('select');lang.setAttribute('aria-label',t('Sprache','Language'));
      for(const k of (MU.d&&MU.d.langs)||['de','en']){const o=document.createElement('option');o.value=k;o.textContent=k;o.selected=k===(s.language||(L==='en'?'en':'de'));lang.appendChild(o)}
      const [nf,nr]=near(1);const nw=document.createElement('input');nw.type='checkbox';const nl=icEl('label','mu-rights');
      nl.append(nw,icEl('span','',t('Ganz neu machen, mit eigener Länge (für zusätzliche Strophen)','Make it completely anew, with its own length (for added verses)')));
      const sk=muNumber(Math.max(30,Math.round(len)),30,lim.max_s,10);const skf=muField(t('Länge (s)','Length (s)'),sk);skf.hidden=true;nw.onchange=()=>{skf.hidden=!nw.checked;nf.hidden=nw.checked};
      opt.append(muLyricsEditor(parts),muField(t('Sprache','Language'),lang),nf,nl,skf);
      get=()=>{const text=muJoin(parts.filter(x=>x.text.trim()||x.tag==='instrumental'));if(!parts.some(x=>x.text.trim())){msg.textContent=t('Bitte den Liedtext schreiben.','Please write the lyrics.');return null}
        const b={liedtext:text,sprache:lang.value,nah:+nr.value};if(nw.checked){b.neu=true;b.sekunden=+sk.value}return b}}
    else if(art==='schneiden'){const fi=muNumber(0,0,30,0.5),fo=muNumber(0,0,30,0.5);
      opt.append(icEl('div','fh',t('Behalten wird der gewählte Bereich.','The chosen part is kept.')),muField(t('Einblenden (s)','Fade in (s)'),fi),muField(t('Ausblenden (s)','Fade out (s)'),fo));
      get=()=>({von:R.a,bis:R.b,einblenden:+fi.value||0,ausblenden:+fo.value||0})}
    else{const tp=muNumber(100,75,125,5),ht=muNumber(0,-4,4,1);
      opt.append(muField(t('Tempo (%)','Tempo (%)'),tp),muField(t('Tonart (Halbtöne)','Key (half tones)'),ht));get=()=>({tempo:Math.round(+tp.value),halbtoene:Math.round(+ht.value)})}};
  const arts=muChips(MUARTS.map(([k,de,en])=>[k,de,en]),art,k=>{art=k;paint()},t('Was ändern','What to change'));
  go.onclick=async()=>{const b=get();if(!b)return;go.disabled=true;msg.textContent=t('wird angenommen …','being accepted …');
    const r=await apiTry('/api/musik/'+encodeURIComponent(s.id)+'/bearbeiten',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({art},b))});
    if(!r.r.ok){msg.textContent=String(r.d.detail||t('Ging nicht.','Did not work.'));go.disabled=false;return}
    if(r.d.song)MU.sel=r.d.song.id;showMusik()};
  box.ontoggle=()=>{MU.ed=box.open?s.id:'';if(box.open){if(!w.done)muWave(s,w);requestAnimationFrame(show)}};
  box.append(arts,w.cv,rng,opt,icEl('div','fh',t('Teile außerhalb des Bereichs bleiben im Originalklang. Jede Änderung ist eine neue Fassung, das Original bleibt; KI-Fassungen sind gekennzeichnet.',
    'Parts outside the range keep the original sound. Every change is a new version, the original stays; AI versions are marked.')),go,msg);
  paint();if(box.open){muWave(s,w);requestAnimationFrame(show)}return box}
// Eigene Datei hochladen: only with the tick for the rights; the file goes as it is, the model computer reads it in
function muUpload(ed){const c=icEl('div','mu-new mu-up');c.hidden=true;if(!ed.on)return c;
  const f=document.createElement('input');f.type='file';f.accept='audio/*,.mp3,.wav,.flac,.m4a,.ogg';f.id='mufile';f.setAttribute('aria-label',t('Musikdatei','Music file'));
  const tl=icEl('label','mu-rights');const tk=document.createElement('input');tk.type='checkbox';tk.id='murechte';
  tl.append(tk,icEl('span','',t('Das ist meine eigene Aufnahme oder ich habe die Rechte daran.','This is my own recording or I own the rights to it.')));
  const go=icEl('button','b p',t('Hochladen','Upload'));go.type='button';go.id='muupgo';const no=icEl('button','b',t('Abbrechen','Cancel'));no.type='button';no.onclick=()=>{c.hidden=true};
  const msg=icEl('div','fh');msg.setAttribute('role','status');const ok=()=>{go.disabled=!(tk.checked&&f.files&&f.files.length)};f.onchange=ok;tk.onchange=ok;ok();
  go.onclick=async()=>{const fl=f.files&&f.files[0];if(!fl||!tk.checked)return;if(fl.size>(ed.upload_mb||30)*1048576){msg.textContent=t(`Höchstens ${ed.upload_mb} MB.`,`At most ${ed.upload_mb} MB.`);return}
    go.disabled=true;msg.textContent=t('wird hochgeladen und gelesen …','uploading and reading …');
    const r=await apiTry('/api/musik/hochladen?rechte=1&name='+encodeURIComponent(fl.name.slice(0,120)),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:fl});
    if(!r.r.ok){msg.textContent=String(r.d.detail||t('Ging nicht.','Did not work.'));ok();return}MU.sel=r.d.id;showMusik()};
  const row=icEl('div','mu-opts');row.append(f,icEl('span','mu-sp'),no,go);
  c.append(icEl('b','',t('Eigene Datei hochladen','Upload an own file')),icEl('div','fh',t(`${(ed.formats||[]).join(', ').toUpperCase()} bis ${ed.upload_mb} MB und 10 Minuten · heute ${ed.uploads} von ${ed.uploads_day}. Hochgeladene Lieder bekommen keine KI-Kennzeichnung, bis du sie bearbeitest.`,
    `${(ed.formats||[]).join(', ').toUpperCase()} up to ${ed.upload_mb} MB and 10 minutes · today ${ed.uploads} of ${ed.uploads_day}. Uploaded songs get no AI mark until you edit them.`)),row,tl,msg);return c}
