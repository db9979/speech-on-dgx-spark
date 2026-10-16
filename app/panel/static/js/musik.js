// Musik machen (musik.py, plan musik M1): Ich → Musik (a wish in, the song out, the own songs as a list with a
// player, details, download and delete) and the card under an answer while a song is made (SSE "musik").
// Wishes, descriptions and lyrics are the person's or the model's words: set with textContent only, never as HTML.
let MUSIK_ON=false;   // Musik machen (who.musik)
const MU={d:null,sel:''};
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
function muJobLine(j){return j.state==='error'?(L==='en'&&j.error_en?j.error_en:j.error)||t('Ging nicht.','Did not work.'):t(...(MUSTATE[j.state]||MUSTATE.wait))}

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
async function showMusik(){const box=$('musikbox');if(!box)return;if(!PROFILE||!MUSIK_ON){box.textContent='';return}
  const r=await apiTry('/api/musik');box.textContent='';
  if(!r.r.ok){box.appendChild(icEmpty(String(r.d.detail||t('Gerade nicht erreichbar.','Not reachable right now.'))));return}
  const d=MU.d=r.d,lim=d.limits;
  box.appendChild(icEl('div','intro',t('Beschreib ein Lied, der Spark macht es selbst (ACE-Step 1.5), ohne Internet. Im Gespräch geht es auch: „Mach mir ein Lied über unsere Katze“. Ohne Gesang wird es instrumental. Jedes Lied ist als KI-erzeugt gekennzeichnet; Sexuelles, Gewalt, Hass und Lieder „im Stil von“ einem Künstler macht er nicht. Namen im Liedtext gehen.',
    'Describe a song and the Spark makes it itself (ACE-Step 1.5), without the internet. It works in the conversation too: "Make me a song about our cat". Without singing it is instrumental. Every song is marked as made by an AI; the Spark makes nothing sexual, violent or hateful and nothing "in the style of" an artist. Names in the lyrics are fine.')));
  const sub=t(`${muMb(d.used)} von ${lim.store_mb} MB · heute ${d.today} von ${lim.day}`,`${muMb(d.used)} of ${lim.store_mb} MB · today ${d.today} of ${lim.day}`);
  box.appendChild(icCard('spark',t(`${d.songs.length} Lieder`,`${d.songs.length} songs`),sub,[],
    d.songs.length?[{label:t('Alle Lieder löschen','Delete all songs'),danger:true,act:muClear}]:[]));
  // a new song
  const f=icEl('div','blnew');const lbl=icEl('label','',t('Was für Musik soll ich machen?','What kind of music shall I make?'));lbl.htmlFor='muwish';
  const ta=document.createElement('textarea');ta.id='muwish';ta.rows=2;ta.maxLength=lim.wish;ta.placeholder=t('z. B. Ruhiges Klavierstück mit Streichern zum Einschlafen','e.g. Calm piano piece with strings for falling asleep');
  const len=document.createElement('select');len.id='mulen';len.setAttribute('aria-label',t('Länge','Length'));
  for(const s of [30,60,120,180,240,300,420,600].filter(s=>s<=lim.max_s)){const o=document.createElement('option');o.value=s;o.textContent=muLen(s);o.selected=s===lim.default_s;len.appendChild(o)}
  const sungL=icEl('label','muchk');const sung=document.createElement('input');sung.type='checkbox';sung.id='musung';sungL.append(sung,document.createTextNode(' '+t('Mit Gesang','With singing')));
  const lang=document.createElement('select');lang.id='mulang';lang.setAttribute('aria-label',t('Sprache','Language'));
  for(const k of d.langs){const o=document.createElement('option');o.value=k;o.textContent=k;o.selected=k===(L==='en'?'en':'de');lang.appendChild(o)}
  const lyL=icEl('label','',t('Liedtext','Lyrics'));lyL.htmlFor='mulyrics';const ly=document.createElement('textarea');ly.id='mulyrics';ly.rows=5;ly.maxLength=lim.lyrics;
  ly.placeholder=t('[verse]\nErste Strophe …\n[chorus]\nRefrain …','[verse]\nFirst verse …\n[chorus]\nChorus …');
  const lyBox=icEl('div','');lyBox.append(lyL,ly);lyBox.hidden=true;lang.hidden=true;
  sung.onchange=()=>{lyBox.hidden=!sung.checked;lang.hidden=!sung.checked};
  const go=icEl('button','b p',t('Lied machen','Make the song'));go.type='button';go.id='mugo';const msg=icEl('div','fh');msg.id='mumsg';msg.setAttribute('role','status');
  const row=icEl('div','row blrow');row.append(len,sungL,lang,go);f.append(lbl,ta,row,lyBox,msg);box.appendChild(f);
  go.onclick=async()=>{const w=ta.value.trim();if(!w){ta.focus();return}if(sung.checked&&!ly.value.trim()){ly.focus();return}
    go.disabled=true;msg.textContent=t('wird angenommen …','being accepted …');
    const r2=await apiTry('/api/musik',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({wunsch:w,sekunden:+len.value,gesang:sung.checked,sprache:lang.value,liedtext:sung.checked?ly.value:''})});
    if(!r2.r.ok){msg.textContent=String(r2.d.detail||t('Ging nicht.','Did not work.'));go.disabled=false;return}
    ta.value='';ly.value='';muFollow(r2.d.id,msg,j=>{msg.textContent=muJobLine(j);if(j.state==='done'){go.disabled=false;MU.sel=j.song.id;showMusik()}else if(j.state==='error')go.disabled=false})};
  for(const j of d.jobs.filter(j=>j.state==='wait'||j.state==='run')){go.disabled=true;
    muFollow(j.id,msg,x=>{msg.textContent=muJobLine(x);if(x.state==='done'){MU.sel=x.song.id;showMusik()}else if(x.state==='error')go.disabled=false})}
  if(!d.songs.length){box.appendChild(icEmpty(t('Noch keine Lieder.','No songs yet.')));return}
  // the list and the details of one song (list with detail, ld-)
  const wrap=icEl('div','ld-box'),split=icEl('div','ld-split'),list=icEl('div','ld-list'),det=icEl('div','ld-detail');det.hidden=true;
  split.append(list,det);wrap.appendChild(split);box.appendChild(wrap);
  const open=s=>{MU.sel=s.id;list.querySelectorAll('.ld-row').forEach(x=>x.classList.toggle('on',x.dataset.id===s.id));wrap.classList.add('ld-sel');det.hidden=false;det.textContent='';
    const back=icEl('button','b ld-back',t('‹ Alle Lieder','‹ All songs'));back.type='button';back.onclick=()=>{MU.sel='';det.hidden=true;wrap.classList.remove('ld-sel')};
    const facts=document.createElement('dl');facts.className='ld-facts';
    const fact=(k,v)=>{if(!v)return;facts.append(icEl('dt','',k),icEl('dd','',String(v)))};
    fact(t('Wunsch','Wish'),s.wish);fact(t('Beschreibung','Description'),s.caption!==s.wish?s.caption:'');
    fact(t('Gemacht','Made'),muWhen(s.t));fact(t('Länge','Length'),muLen(s.length_s)+' · '+(s.sung?t('mit Gesang','with singing')+(s.language?' ('+s.language+')':''):t('instrumental','instrumental'))+' · '+muMb(s.bytes));
    fact(t('Dauer','Time'),s.seconds!=null?String(s.seconds).replace('.',L==='en'?'.':',')+' s':'');fact(t('Modell','Model'),s.model);
    const acts=icEl('div','ld-acts');const dl=document.createElement('a');dl.className='b p';dl.href=muFile(s.id,1);dl.textContent=t('Herunterladen','Download');
    const del=icEl('button','b ic-red',t('Löschen','Delete'));del.type='button';del.onclick=async()=>{if(!confirm(t('Dieses Lied löschen?','Delete this song?')))return;
      const r3=await apiTry('/api/musik/'+encodeURIComponent(s.id),{method:'DELETE'});if(!r3.r.ok){alert(String(r3.d.detail||''));return}MU.sel='';showMusik()};
    acts.append(dl,del);det.append(back,muAudio(s.id),facts,acts);
    if(s.lyrics){const lt=icEl('pre','mulyr',s.lyrics);det.appendChild(lt)}};
  for(const s of d.songs){const b=icEl('button','ld-row');b.type='button';b.dataset.id=s.id;
    b.append(icEl('b','',s.wish||s.caption||t('Lied','Song')),icEl('span','mut',' · '+muLen(s.length_s)+' · '+muWhen(s.t)));b.onclick=()=>open(s);list.appendChild(b)}
  const pick=d.songs.find(s=>s.id===MU.sel);if(pick)open(pick)}
async function muClear(){if(!confirm(t('Alle deine Lieder löschen? Das lässt sich nicht rückgängig machen.','Delete all your songs? This cannot be undone.')))return;
  const r=await apiTry('/api/musik',{method:'DELETE'});if(!r.r.ok){alert(String(r.d.detail||''));return}MU.sel='';showMusik()}
