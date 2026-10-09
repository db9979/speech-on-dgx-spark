// Pictures for the assistant (images.py): attach a photo, then ask by typing or speaking. Only for
// profiles with the admin's and their own switch (ALLOW.images, S.images_on). The browser makes the
// picture smaller first; the Spark cleans it again and keeps it in memory only, 10 minutes after its
// last use, so follow-up questions about it work. Removing the chip (✕) or a new conversation drops it.
const pics={list:[],max:3,side:1280,keep:600};
function picsOn(){return !!(PROFILE&&ALLOW.images&&S.images_on)}
function picsShow(){const on=picsOn();$('chatpic').hidden=!on;$('mpic').hidden=!on;if(!on&&pics.list.length)picsClear();picsRender()}
function picsRender(){const box=$('chatpics');picsPrune();box.hidden=!pics.list.length;
  document.querySelector('.composer').classList.toggle('haspic',!!pics.list.length);
  box.innerHTML=pics.list.map((p,i)=>`<span class="pic"><img alt="" src="${esc(p.url)}"><button type="button" class="picx" data-picx="${i}" title="${t('Bild entfernen','Remove picture')}">✕</button></span>`).join('')+
    (pics.list.length?`<span class="mut">${t('Bleibt für Rückfragen, bis du es entfernst (höchstens 10 Minuten ohne Frage).','Kept for follow-up questions until you remove it (at most 10 minutes without a question).')}</span>`:'')}
function picsPrune(){const now=Date.now();for(const p of pics.list.filter(p=>now-p.used>pics.keep*1000))picDrop(p,true)}
function picDrop(p,quiet){pics.list=pics.list.filter(x=>x!==p);try{URL.revokeObjectURL(p.url)}catch{}
  if(!quiet)api('/api/chat/image/'+encodeURIComponent(p.id),{method:'DELETE'}).catch(()=>{})}
function picsClear(quiet){for(const p of pics.list.slice())picDrop(p,quiet);picsRender()}
// the ids for the next question; the Spark counts the 10 minutes from each use
function picIds(){picsPrune();const now=Date.now();pics.list.forEach(p=>p.used=now);return pics.list.map(p=>p.id)}
function picThumbs(){return pics.list.map(p=>p.url)}
async function picSmall(file){
  const bmp=await createImageBitmap(file,{imageOrientation:'from-image'});
  const k=Math.min(1,pics.side/Math.max(bmp.width,bmp.height)),c=document.createElement('canvas');
  c.width=Math.max(1,Math.round(bmp.width*k));c.height=Math.max(1,Math.round(bmp.height*k));
  const g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,c.width,c.height);g.drawImage(bmp,0,0,c.width,c.height);bmp.close&&bmp.close();
  return await new Promise((res,rej)=>c.toBlob(b=>b?res(b):rej(new Error('toBlob')),'image/jpeg',0.85))}
async function picAdd(file){if(!picsOn()||!file)return;
  if(!/^image\//.test(file.type||'')){chatSay(t('Das ist kein Bild.','That is not a picture.'));return}
  if(pics.list.length>=pics.max){chatSay(t('Höchstens 3 Bilder pro Frage.','At most 3 pictures per question.'));return}
  chatSay(t('Bild wird geladen …','Loading picture …'));
  try{let blob;try{blob=await picSmall(file)}catch{blob=file}
    const r=await (await api('/api/chat/image',{method:'POST',headers:{'Content-Type':blob.type||'image/jpeg'},body:blob})).json();
    pics.list.push({id:r.id,url:URL.createObjectURL(blob),used:Date.now()});picsRender();
    if(typeof MVIEW!=='undefined'&&MVIEW==='face'&&MOBILE.matches)setView('log');   // phone: the chip and the text field are in the conversation view
    chatSay(t('Bild angehängt. Jetzt fragen, getippt oder gesprochen.','Picture attached. Now ask, typed or spoken.'));$('chattext').focus()}
  catch(e){chatSay(t('Bild nicht angenommen: ','Picture not accepted: ')+e.message)}}
// a question about a picture that the Spark no longer has: say so and drop the chips
function picsGone(){picsClear(true);chatSay(t('Das Bild ist nicht mehr da (nach 10 Minuten). Bitte neu anhängen.','The picture is gone (after 10 minutes). Please attach it again.'))}
// the answer to a picture under "Meine Dokumente", only on the person's click (images.py keeps no picture)
async function picSave(text,btn){const name=t('Bild-Antwort ','Picture answer ')+new Date().toISOString().slice(0,16).replace('T',' ').replace(':','-')+'.txt';
  const f=new FormData();f.append('file',new Blob([text],{type:'text/plain'}),name);btn.disabled=true;
  try{await api('/api/profile/docs',{method:'POST',body:f});btn.textContent=t('Gespeichert unter „Meine Dokumente“','Stored under "My documents"')}
  catch(e){btn.disabled=false;btn.textContent=t('Nicht gespeichert: ','Not stored: ')+e.message}}
// the picture itself under "Meine Dokumente" (wissen.py): the language model reads it later in a quiet moment
async function picKeep(ids,btn){btn.disabled=true;
  try{for(const id of ids)await api('/api/profile/wissen/picture',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
    btn.textContent=t('Bild gespeichert, wird bald gelesen','Picture stored, read soon')}
  catch(e){btn.disabled=false;btn.textContent=t('Nicht gespeichert: ','Not stored: ')+e.message}}
$('chatpic').onclick=$('mpic').onclick=()=>$('chatpicfile').click();
$('chatpicfile').onchange=async()=>{for(const f of [...$('chatpicfile').files].slice(0,pics.max))await picAdd(f);$('chatpicfile').value=''};
$('chatpics').addEventListener('click',e=>{const b=e.target.closest('[data-picx]');if(!b)return;const p=pics.list[Number(b.dataset.picx)];if(p)picDrop(p);picsRender()});
// pasting or dropping a picture into the conversation
document.addEventListener('paste',e=>{if(!picsOn()||!$('chat').classList.contains('on'))return;
  const f=[...(e.clipboardData&&e.clipboardData.files||[])].find(x=>/^image\//.test(x.type));if(f){e.preventDefault();picAdd(f)}});
const pdrop=document.querySelector('.convo');
pdrop.addEventListener('dragover',e=>{if(picsOn()&&[...(e.dataTransfer&&e.dataTransfer.types||[])].includes('Files'))e.preventDefault()});
pdrop.addEventListener('drop',e=>{if(!picsOn())return;const f=[...(e.dataTransfer&&e.dataTransfer.files||[])].filter(x=>/^image\//.test(x.type));
  if(f.length){e.preventDefault();(async()=>{for(const x of f.slice(0,pics.max))await picAdd(x)})()}});
$('chatnew').addEventListener('click',()=>picsClear());
