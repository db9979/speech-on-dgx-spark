// Bilder malen (bilder.py, plan bildgenerierung): Ich → Bilder (a wish in, the picture out, the own pictures as a
// gallery with details, download and delete) and the card under an answer while a picture is painted (SSE "bild").
// Prompts and wishes are the person's or the model's words: set with textContent or esc() only, never as HTML.
let BILD_ON=false,BILDAE_ON=false;   // Bilder malen, Bilder ändern (who.bilder, who.bilder_aendern)
const BL={d:null,sel:'',timer:0};
const blFile=(id,dl)=>'/api/bilder/'+encodeURIComponent(id)+'/datei'+(dl?'?dl=1':'');
const blWhen=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'}):'';
const blMb=b=>(b/1048576).toFixed(b<10485760?1:0).replace('.',L==='en'?'.':',')+' MB';
function blImg(p,cls){const i=document.createElement('img');i.src=blFile(p.id);i.alt=p.wish||p.prompt||t('Gemaltes Bild','Painted picture');
  i.loading='lazy';i.decoding='async';i.className=cls||'';if(p.w&&p.h){i.width=p.w;i.height=p.h}return i}
// follows one job until it ends; tick(job) on every look, stops when the element left the page
function blFollow(jid,el,tick){const look=async()=>{if(!el.isConnected)return;const r=await apiTry('/api/bilder/job/'+encodeURIComponent(jid));
    if(!r.r.ok){tick({state:'error',error:String(r.d.detail||'').slice(0,200)});return}
    tick(r.d);if(r.d.state==='wait'||r.d.state==='run')setTimeout(look,2500)};look()}
const BLSTATE={wait:['wartet auf eine Gesprächspause','waiting for a pause in the conversation'],run:['malt …','painting …'],change:['ändert …','changing …']};
function blJobLine(j){return j.state==='error'?(L==='en'&&j.error_en?j.error_en:j.error)||t('Ging nicht.','Did not work.'):t(...(j.state==='run'&&j.art==='aendern'?BLSTATE.change:BLSTATE[j.state]||BLSTATE.wait))}
// sends an own photo (Ich → Bilder „Eigenes Foto hochladen“) as it is; the panel cleans and keeps it as a PNG
async function blPhoto(file,msg){if(!file)return;if(!/^image\//.test(file.type||'')){msg.textContent=t('Das ist kein Bild.','That is not a picture.');return}
  msg.textContent=t('wird hochgeladen …','uploading …');const r=await apiTry('/api/bilder/foto',{method:'POST',headers:{'Content-Type':file.type},body:file});
  if(!r.r.ok){msg.textContent=String(r.d.detail||t('Ging nicht.','Did not work.'));return}BL.sel=r.d.id;showBilder()}

// ---------------------------------------------------------------- the card in the chat
function bildCard(ev){const d=icEl('div','hcard blcard');const h=icEl('h4','',ev.art==='aendern'?t('Bild ändern','Changing the picture'):t('Bild','Picture'));const st=icEl('div','hmsg mut',t('wartet …','waiting …'));
  st.setAttribute('role','status');const pr=icEl('div','hwhy',t('Prompt: ','Prompt: ')+String(ev.prompt||''));d.append(h,st,pr);
  blFollow(ev.job,d,j=>{if(j.state==='done'&&j.pic){st.remove();const a=document.createElement('a');a.href=blFile(j.pic.id);a.target='_blank';a.rel='noopener';
      a.appendChild(blImg(j.pic,'blbig'));d.insertBefore(a,pr);const row=icEl('div','row');const dl=document.createElement('a');dl.className='b';dl.href=blFile(j.pic.id,1);
      dl.textContent=t('Herunterladen','Download');const go=icEl('button','b',t('Alle Bilder','All pictures'));go.type='button';go.onclick=()=>openMe('bildbox');
      row.append(dl,go);d.appendChild(row)}
    else{st.textContent=blJobLine(j);st.classList.toggle('err',j.state==='error')}});
  return d}
// what stays under the answer in the history (profiles._att "bild"): the picture itself (its job leads to it, also
// after a reload and on every device), else the prompt and a way to the pictures
function bildAtt(a){const d=icEl('div','mem');d.appendChild(document.createTextNode('🖼 '+t('Bild: ','Picture: ')+String(a.p||'').slice(0,120)+' '));
  const b=icEl('button','mlink',t('Ansehen','View'));b.type='button';b.onclick=()=>openMe('bildbox');d.appendChild(b);
  if(a.j&&BILD_ON)setTimeout(()=>blFollow(a.j,d,j=>{if(j.state!=='done'||!j.pic)return;const l=document.createElement('a');l.href=blFile(j.pic.id);
    l.target='_blank';l.rel='noopener';l.className='blatt';l.appendChild(blImg(j.pic,'blbig'));d.prepend(l)}),0);
  return d}

// ---------------------------------------------------------------- Ich → Bilder
async function showBilder(){const box=$('bildbox');if(!box)return;if(!PROFILE||!BILD_ON){box.textContent='';return}
  const r=await apiTry('/api/bilder');box.textContent='';
  if(!r.r.ok){box.appendChild(icEmpty(String(r.d.detail||t('Gerade nicht erreichbar.','Not reachable right now.'))));return}
  const d=BL.d=r.d,lim=d.limits;
  box.appendChild(icEl('div','intro',t('Beschreib ein Bild, der Spark malt es selbst (FLUX.2 klein), ohne Internet. Im Gespräch geht es auch: „Mal mir eine Katze auf einem Skateboard“. Jedes Bild ist als KI-Bild gekennzeichnet; Nacktes, Gewalt und Personen, die der Spark kennt, malt er nicht.',
    'Describe a picture and the Spark paints it itself (FLUX.2 klein), without the internet. It works in the conversation too: "Paint me a cat on a skateboard". Every picture is marked as made by an AI; the Spark paints no nudity, no violence and no people it knows.')));
  if(BILDAE_ON)box.appendChild(icEl('div','fh',t('Ändern: Bild antippen und sagen, was anders sein soll, oder im Chat ein Foto anhängen und „Mach den Himmel blau“ schreiben. Das Original bleibt.',
    'Change: tap a picture and say what should be different, or attach a photo in the chat and write "Make the sky blue". The original stays.')));
  const sub=t(`${blMb(d.used)} von ${lim.store_mb} MB · heute ${d.today} von ${lim.day}`,`${blMb(d.used)} of ${lim.store_mb} MB · today ${d.today} of ${lim.day}`);
  box.appendChild(icCard('spark',t(`${d.pics.length} Bilder`,`${d.pics.length} pictures`),sub,[],
    d.pics.length?[{label:t('Alle Bilder löschen','Delete all pictures'),danger:true,act:blClear}]:[]));
  // a new picture
  const f=icEl('div','blnew');const lbl=icEl('label','',t('Was soll ich malen?','What shall I paint?'));lbl.htmlFor='blwish';
  const ta=document.createElement('textarea');ta.id='blwish';ta.rows=3;ta.maxLength=lim.wish;ta.placeholder=t('z. B. Ein Leuchtturm bei Sturm, Ölgemälde','e.g. A lighthouse in a storm, oil painting');
  const sel=document.createElement('select');sel.id='blfmt';sel.setAttribute('aria-label',t('Format','Format'));
  for(const [k,de,en] of d.formats){const o=document.createElement('option');o.value=k;o.textContent=L==='en'?en:de;sel.appendChild(o)}
  const go=icEl('button','b p',t('Malen','Paint'));go.type='button';go.id='blgo';const msg=icEl('div','fh');msg.id='blmsg';msg.setAttribute('role','status');
  const row=icEl('div','row blrow');row.append(sel,go);f.append(lbl,ta,row,msg);box.appendChild(f);
  // Bilder ändern: an own photo to change (kept like a painted picture, marked as uploaded)
  if(BILDAE_ON){const up=document.createElement('input');up.type='file';up.accept='image/jpeg,image/png,image/webp';up.id='blfoto';up.hidden=true;
    const ub=icEl('button','b',t('Eigenes Foto hochladen','Upload an own photo'));ub.type='button';ub.id='blfotogo';ub.onclick=()=>up.click();
    up.onchange=()=>{const fl=up.files&&up.files[0];up.value='';blPhoto(fl,msg)};row.append(ub,up)}
  go.onclick=async()=>{const w=ta.value.trim();if(!w){ta.focus();return}go.disabled=true;msg.textContent=t('wird angenommen …','being accepted …');
    const r2=await apiTry('/api/bilder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wunsch:w,format:sel.value})});
    if(!r2.r.ok){msg.textContent=String(r2.d.detail||t('Ging nicht.','Did not work.'));go.disabled=false;return}
    ta.value='';blFollow(r2.d.id,msg,j=>{msg.textContent=blJobLine(j);if(j.state==='done'){go.disabled=false;BL.sel=j.pic.id;showBilder()}else if(j.state==='error')go.disabled=false})};
  for(const j of d.jobs.filter(j=>j.state==='wait'||j.state==='run')){go.disabled=true;
    blFollow(j.id,msg,x=>{msg.textContent=blJobLine(x);if(x.state==='done'){BL.sel=x.pic.id;showBilder()}else if(x.state==='error')go.disabled=false})}
  if(!d.pics.length){box.appendChild(icEmpty(t('Noch keine Bilder.','No pictures yet.')));return}
  // the gallery and the details of one picture (list with detail, ld-)
  const wrap=icEl('div','ld-box'),split=icEl('div','ld-split'),list=icEl('div','ld-list blgrid'),det=icEl('div','ld-detail');det.hidden=true;
  split.append(list,det);wrap.appendChild(split);box.appendChild(wrap);
  const open=p=>{BL.sel=p.id;list.querySelectorAll('.bltile').forEach(x=>x.classList.toggle('on',x.dataset.id===p.id));wrap.classList.add('ld-sel');det.hidden=false;det.textContent='';
    const back=icEl('button','b ld-back',t('‹ Alle Bilder','‹ All pictures'));back.type='button';back.onclick=()=>{BL.sel='';det.hidden=true;wrap.classList.remove('ld-sel')};
    const a=document.createElement('a');a.href=blFile(p.id);a.target='_blank';a.rel='noopener';a.appendChild(blImg(p,'blbig'));
    const facts=document.createElement('dl');facts.className='ld-facts';
    const fact=(k,v)=>{if(!v)return;facts.append(icEl('dt','',k),icEl('dd','',String(v)))};
    const orig=p.von&&p.von!=='foto'?d.pics.find(x=>x.id===p.von):null;
    fact(t('Wunsch','Wish'),p.wish);fact('Prompt',p.art==='aendern'?'':p.prompt);
    fact(p.art==='foto'?t('Hochgeladen','Uploaded'):p.art==='aendern'?t('Geändert','Changed'):t('Gemalt','Painted'),blWhen(p.t));
    if(p.art==='aendern')fact(t('Original','Original'),p.von==='foto'?t('Foto aus dem Chat','Photo from the chat'):orig?'':t('gelöscht','deleted'));fact(t('Größe','Size'),p.w+' × '+p.h+' · '+blMb(p.bytes));
    fact(t('Dauer','Time'),p.seconds!=null?String(p.seconds).replace('.',L==='en'?'.':',')+' s':'');
    const acts=icEl('div','ld-acts');const dl=document.createElement('a');dl.className='b p';dl.href=blFile(p.id,1);dl.textContent=t('Herunterladen','Download');
    const del=icEl('button','b ic-red',t('Löschen','Delete'));del.type='button';del.onclick=async()=>{if(!confirm(t('Dieses Bild löschen?','Delete this picture?')))return;
      const r3=await apiTry('/api/bilder/'+encodeURIComponent(p.id),{method:'DELETE'});if(!r3.r.ok){alert(String(r3.d.detail||''));return}BL.sel='';showBilder()};
    acts.append(dl,del);
    if(orig){const ob=icEl('button','b',t('Original zeigen','Show the original'));ob.type='button';ob.onclick=()=>open(orig);acts.appendChild(ob)}
    det.append(back,a,facts,acts);
    // Bilder ändern: the person's own sentence; the result is a new picture, this one stays
    if(BILDAE_ON){const ch=icEl('div','blnew');const cl=icEl('label','',t('Was soll ich an diesem Bild ändern?','What shall I change in this picture?'));cl.htmlFor='blchange';
      const ct=document.createElement('textarea');ct.id='blchange';ct.rows=2;ct.maxLength=lim.wish;ct.placeholder=t('z. B. Mach den Himmel blau, als Aquarell','e.g. Make the sky blue, as a watercolour');
      const cg=icEl('button','b p',t('Ändern','Change'));cg.type='button';cg.id='blchangego';const cm=icEl('div','fh');cm.setAttribute('role','status');
      cg.onclick=async()=>{const w=ct.value.trim();if(!w){ct.focus();return}cg.disabled=true;cm.textContent=t('wird angenommen …','being accepted …');
        const r4=await apiTry('/api/bilder/'+encodeURIComponent(p.id)+'/aendern',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wunsch:w})});
        if(!r4.r.ok){cm.textContent=String(r4.d.detail||t('Ging nicht.','Did not work.'));cg.disabled=false;return}
        ct.value='';blFollow(r4.d.id,cm,j=>{cm.textContent=blJobLine(j);if(j.state==='done'){BL.sel=j.pic.id;showBilder()}else if(j.state==='error')cg.disabled=false})};
      const cr=icEl('div','row blrow');cr.appendChild(cg);ch.append(cl,ct,cr,cm);det.appendChild(ch)}};
  for(const p of d.pics){const b=icEl('button','bltile');b.type='button';b.dataset.id=p.id;b.title=p.wish||p.prompt||'';b.setAttribute('aria-label',p.wish||p.prompt||t('Bild','Picture'));
    b.appendChild(blImg(p,'blthumb'));b.onclick=()=>open(p);list.appendChild(b)}
  const pick=d.pics.find(p=>p.id===BL.sel);if(pick)open(pick)}
async function blClear(){if(!confirm(t('Alle deine Bilder löschen? Das lässt sich nicht rückgängig machen.','Delete all your pictures? This cannot be undone.')))return;
  const r=await apiTry('/api/bilder',{method:'DELETE'});if(!r.r.ok){alert(String(r.d.detail||''));return}BL.sel='';showBilder()}
