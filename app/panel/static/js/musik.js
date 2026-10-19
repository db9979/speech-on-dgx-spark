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
const MU={d:null,sel:'',q:'',f:'all',play:'',au:null};
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
  head.appendChild(hl);if(d.songs.length)head.appendChild(icMenu([{label:t('Alle Lieder löschen','Delete all songs'),danger:true,act:muClear}]));wrap.appendChild(head);
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
  wrap.appendChild(f);pickLen(lim.default_s);showSung();
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
  const tools=icEl('div','ld-tools'+(d.songs.length<6?' few':''));const q=document.createElement('input');q.type='search';q.value=MU.q;
  q.placeholder=t('Lieder suchen','Search songs');q.setAttribute('aria-label',t('Lieder suchen','Search songs'));
  const chips=icEl('div','ld-chips');const nSung=d.songs.filter(s=>s.sung).length;
  for(const [k,de,en,n] of [['all','Alle','All',d.songs.length],['sung','Mit Gesang','With singing',nSung],['inst','Instrumental','Instrumental',d.songs.length-nSung]]){
    const b=icEl('button','ld-chip'+(MU.f===k?' on':''),t(de,en));b.type='button';b.dataset.f=k;b.setAttribute('aria-pressed',String(MU.f===k));b.appendChild(icEl('b','',' '+n));
    b.onclick=()=>{MU.f=k;chips.querySelectorAll('button').forEach(x=>{const o=x.dataset.f===k;x.classList.toggle('on',o);x.setAttribute('aria-pressed',String(o))});paint()};chips.appendChild(b)}
  tools.append(q,chips);wrap.appendChild(tools);
  const split=icEl('div','ld-split'),list=icEl('div','ld-list'),det=icEl('div','ld-detail');det.hidden=true;split.append(list,det);wrap.appendChild(split);
  const bar=icEl('div','mu-mini');bar.hidden=true;const bb=icEl('button','ld-ico mu');bb.type='button';bb.dataset.muplay='';
  bb.onclick=()=>{const s=d.songs.find(x=>x.id===MU.play);if(s)muToggle(s)};const bt=icEl('button','mu-mt');bt.type='button';bt.append(icEl('b'),icEl('small','mut'));
  bt.onclick=()=>{const s=d.songs.find(x=>x.id===MU.play);if(s)open(s)};bar.append(bb,bt);wrap.appendChild(bar);
  const open=s=>{MU.sel=s.id;list.querySelectorAll('.ld-row').forEach(x=>x.classList.toggle('on',x.dataset.id===s.id));wrap.classList.add('ld-sel');det.hidden=false;det.textContent='';
    const back=icEl('button','b ld-back',t('‹ Alle Lieder','‹ All songs'));back.type='button';back.onclick=()=>{MU.sel='';det.hidden=true;wrap.classList.remove('ld-sel');paint()};
    // the player: ▶/⏸, the time and a slider to jump; it plays through MU.au like the rows
    const pl=icEl('div','mu-player');pl.dataset.id=s.id;const pb=icEl('button','mu-pb');pb.type='button';pb.dataset.muplay=s.id;pb.onclick=()=>muToggle(s);
    const rg=document.createElement('input');rg.type='range';rg.min='0';rg.max=String(Math.round(s.length_s||0));rg.value='0';rg.setAttribute('aria-label',t('Stelle im Lied','Position in the song'));
    rg.oninput=()=>{if(MU.play!==s.id)muToggle(s);const a=muAu();if(isFinite(a.duration))a.currentTime=+rg.value};
    pl.append(pb,icEl('small','mu-t','0:00'),rg,icEl('small','',muClock(s.length_s)));
    const facts=document.createElement('dl');facts.className='ld-facts';
    const fact=(k,v)=>{if(!v)return;facts.append(icEl('dt','',k),icEl('dd','',String(v)))};
    fact(t('Gemacht','Made'),muWhen(s.t));fact(t('Länge','Length'),muLen(s.length_s)+' · '+muSing(s));fact(t('Größe','Size'),muMb(s.bytes));
    fact(t('Dauer','Time'),(s.seconds!=null?String(s.seconds).replace('.',L==='en'?'.':',')+' s':'')+(s.model?(s.seconds!=null?' · ':'')+s.model:''));
    const acts=icEl('div','ld-acts');const dl=document.createElement('a');dl.className='b p';dl.href=muFile(s.id,1);dl.textContent=t('Herunterladen','Download');
    const ag=icEl('button','b',t('Nochmal machen','Make it again'));ag.type='button';ag.onclick=()=>again(s);
    const del=icEl('button','b ic-red',t('Löschen','Delete'));del.type='button';del.onclick=async()=>{if(!confirm(t('Dieses Lied löschen?','Delete this song?')))return;
      const r3=await apiTry('/api/musik/'+encodeURIComponent(s.id),{method:'DELETE'});if(!r3.r.ok){alert(String(r3.d.detail||''));return}
      if(MU.play===s.id&&MU.au){MU.au.pause();MU.play=''}MU.sel='';showMusik()};
    acts.append(dl,ag,del);det.append(back,icEl('h3','',muTitle(s)),pl,facts,acts);
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
    const shown=d.songs.filter(s=>(MU.f==='all'||(MU.f==='sung')===!!s.sung)&&(!ql||[s.wish,s.caption,s.lyrics].some(v=>String(v||'').toLowerCase().includes(ql))));
    let grp='';for(const s of shown){const g=muGroup(s.t);if(g!==grp){grp=g;const h=icEl('div','ld-grp');h.append(icEl('span','',g),icEl('span','',String(shown.filter(x=>muGroup(x.t)===g).length)));list.appendChild(h)}
      const row=icEl('div','ld-row'+(MU.sel===s.id?' on':''));row.dataset.id=s.id;row.tabIndex=0;row.setAttribute('role','button');
      const pb=icEl('button','ld-ico mu');pb.type='button';pb.dataset.muplay=s.id;pb.onclick=e=>{e.stopPropagation();muToggle(s)};
      const mid=icEl('span','ld-mid');const b=icEl('b','',muTitle(s));b.title=muTitle(s);mid.append(b,icEl('small','',muLen(s.length_s)+' · '+muSing(s)));
      const right=icEl('span','ld-right');right.appendChild(icEl('span','ld-when',muShort(s.t)));row.append(pb,mid,right);
      row.onclick=()=>open(s);row.onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&e.target===row){e.preventDefault();open(s)}};list.appendChild(row)}
    if(!shown.length&&d.songs.length)list.appendChild(icEl('div','mut ld-empty',t('Nichts passt zu Suche und Filter.','Nothing fits the search and filter.')));
    muSync()};
  q.oninput=()=>{MU.q=q.value;paint()};paint();
  const pick=d.songs.find(s=>s.id===MU.sel);if(pick)open(pick)}
async function muClear(){if(!confirm(t('Alle deine Lieder löschen? Das lässt sich nicht rückgängig machen.','Delete all your songs? This cannot be undone.')))return;
  const r=await apiTry('/api/musik',{method:'DELETE'});if(!r.r.ok){alert(String(r.d.detail||''));return}if(MU.au){MU.au.pause();MU.play=''}MU.sel='';showMusik()}
