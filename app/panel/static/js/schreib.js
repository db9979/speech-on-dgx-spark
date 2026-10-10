// Ich → Schreibhilfe (schreib.py): a text in, the improved text out, with the changes marked by the panel.
// Nothing is kept on the Spark; a draft goes into the mailbox only on the person's click, never sent.
let WRITE_ON=false;
const WR={info:null,res:''};
async function showWrite(){const box=$('writebox');if(!box)return;if(!PROFILE||!WRITE_ON){box.innerHTML='';return}
  let d=null;try{d=await (await api('/api/write')).json()}catch{}
  WR.info=d;const on=!!(d&&d.on);
  const arts=d?d.arts:[],langs=d?d.langs:[];
  box.innerHTML=`<div class="intro">${t('Text hineinkopieren, Art wählen, fertig: korrigieren, glätten, kürzen, freundlicher oder förmlicher machen, übersetzen oder eine Antwort auf eine Mail entwerfen. Der Spark liest den Text nur, speichert nichts und sendet nie etwas.','Paste a text, pick what to do, done: correct, smooth, shorten, make friendlier or more formal, translate, or draft a reply to a mail. The Spark only reads the text, stores nothing and never sends anything.')}</div>
    ${xsw('write_on',t('Schreibhilfe für mich nutzen','Use the writing help for me'),t('Auch über „Dienste per MCP“ (Werkzeug „Text verbessern“), wenn du es dort einer Verbindung gibst.','Also over "Services over MCP" (tool "Improve text") when you give it to a connection there.'))}
    ${on?`<label for="wrart">${t('Was soll passieren?','What should happen?')}</label>
    <div class="two2"><div><select id="wrart">${arts.map(a=>`<option value="${esc(a.id)}">${esc(L==='en'?a.en:a.de)}</option>`).join('')}</select></div>
      <div id="wrlangbox" hidden><select id="wrlang" aria-label="${t('Sprache','Language')}"></select></div></div>
    <div id="wrmailbox" hidden><label for="wrmail">${t('Erhaltene Mail','Mail you received')}</label>
      <textarea id="wrmail" rows="6" maxlength="${d.max}" placeholder="${t('Die Mail, auf die du antwortest, hier hineinkopieren','Paste the mail you are answering here')}"></textarea>
      ${d.pics?`<div class="row" style="margin-top:4px"><button class="b" type="button" data-wrpic="wrmail">${t('Aus Bild lesen','Read from picture')}</button></div>`:''}</div>
    <label for="wrtext" id="wrtextlbl">${t('Dein Text','Your text')}</label>
    <textarea id="wrtext" rows="8" maxlength="${d.max}"></textarea>
    ${d.pics?`<div class="row" style="margin-top:4px"><button class="b" type="button" data-wrpic="wrtext">${t('Aus Bild lesen','Read from picture')}</button><span class="mut">${t('oder ein Bildschirmfoto einfügen (Strg+V)','or paste a screenshot (Ctrl+V)')}</span></div>`:''}
    <label for="wrwish">${t('Wunsch (frei)','Wish (optional)')}</label>
    <input id="wrwish" maxlength="300" autocomplete="off" placeholder="${t('z. B. mit Du, kurz halten, Gruß „Viele Grüße, Dominik“','e.g. informal, keep it short, sign "Best, Dominik"')}">
    <div class="row" style="margin-top:8px"><button class="b p" type="button" id="wrgo">${t('Los','Go')}</button><button class="b" type="button" id="wrclear">${t('Leeren','Clear')}</button></div>
    <div class="fh" id="wrmsg"></div>
    <div id="wrout" hidden>
      <label>${t('Vorschlag','Suggestion')}</label>
      <div id="wrdiff" class="wrdiff" hidden></div>
      <textarea id="wrres" rows="8"></textarea>
      <div class="row" style="margin-top:6px;flex-wrap:wrap;gap:6px"><button class="b p" type="button" id="wrcopy">${t('Kopieren','Copy')}</button><button class="b" type="button" id="wrtake">${t('Als meinen Text übernehmen','Use as my text')}</button></div>
      ${d.draft?`<details id="wrdraftbox" style="margin-top:10px"><summary>${t('Als Entwurf ins Postfach legen','Put into the mailbox as a draft')}</summary>
        <div class="two2"><div><label for="wrto">${t('An','To')}</label><input id="wrto" type="email" autocomplete="off" maxlength="300"></div><div><label for="wrsubj">${t('Betreff','Subject')}</label><input id="wrsubj" autocomplete="off" maxlength="200"></div></div>
        <div class="fh">${t('Der Entwurf landet im Ordner „Entwürfe“ deines Postfachs. Gesendet wird er nur von dir, im Mailprogramm.','The draft lands in your mailbox\'s drafts folder. Only you send it, in your mail program.')}</div>
        <div class="row" style="margin-top:6px"><button class="b" type="button" id="wrdraft">${t('Entwurf ablegen','Save draft')}</button></div></details>`:''}
    </div>
    <input type="file" id="wrfile" accept="image/*" hidden>`:''}`;
  xbind(box,showWrite);
  if(!on)return;
  const art=()=>$('wrart').value,lang=$('wrlang');
  const sync=()=>{const a=art(),reply=a==='antwort';$('wrmailbox').hidden=!reply;$('wrlangbox').hidden=!(reply||a==='uebersetzen');
    lang.innerHTML=(reply?`<option value="auto">${t('wie die Mail','like the mail')}</option>`:'')+langs.map(x=>`<option value="${esc(x.id)}">${esc(L==='en'?x.en:x.de)}</option>`).join('');
    if(a==='uebersetzen')lang.value=L==='en'?'de':'en';
    $('wrtextlbl').textContent=reply?t('Was soll drinstehen? (Stichpunkte, frei lassen für eine kurze Antwort)','What should it say? (notes, leave empty for a short reply)'):t('Dein Text','Your text')};
  $('wrart').onchange=sync;sync();
  $('wrgo').onclick=writeGo;
  $('wrclear').onclick=()=>{['wrtext','wrmail','wrwish'].forEach(id=>$(id).value='');$('wrout').hidden=true;xmsg('wrmsg','')};
  $('wrcopy').onclick=()=>copyString($('wrres').value,$('wrcopy'));
  $('wrtake').onclick=()=>{$('wrtext').value=$('wrres').value;$('wrdiff').hidden=true;xmsg('wrmsg',t('Übernommen. Du kannst ihn noch einmal bearbeiten lassen.','Taken over. You can have it worked on again.'))};
  if($('wrdraft'))$('wrdraft').onclick=writeDraft;
  box.querySelectorAll('[data-wrpic]').forEach(b=>b.onclick=()=>{WR.into=b.dataset.wrpic;$('wrfile').value='';$('wrfile').click()});
  $('wrfile').onchange=()=>{const f=$('wrfile').files[0];if(f)writePic(f,WR.into||'wrtext')};
  if(d.pics)['wrtext','wrmail'].forEach(id=>$(id).addEventListener('paste',e=>{const it=[...(e.clipboardData&&e.clipboardData.items||[])].find(x=>/^image\//.test(x.type));
    if(it){e.preventDefault();writePic(it.getAsFile(),id)}}))}
async function writeGo(){const a=$('wrart').value,body={art:a,text:$('wrtext').value,wunsch:$('wrwish').value};
  if(a==='antwort')body.mail=$('wrmail').value;if(!$('wrlangbox').hidden)body.sprache=$('wrlang').value;
  if(!body.text.trim()&&a!=='antwort'){xmsg('wrmsg',t('Erst einen Text hineinkopieren.','Paste a text first.'),true);return}
  const go=$('wrgo');go.disabled=true;xmsg('wrmsg',t('Der Spark schreibt …','The Spark is writing …'));
  try{const r=await (await api('/api/write/assist',xjson('POST',body))).json();WR.res=r.text;
    $('wrres').value=r.text;$('wrout').hidden=false;
    const dv=$('wrdiff');dv.hidden=!r.diff;if(r.diff)dv.innerHTML=r.diff.map(([k,s])=>k==='='?esc(s):k==='-'?`<del>${esc(s)}</del>`:`<ins>${esc(s)}</ins>`).join('');
    xmsg('wrmsg',(r.changes!=null?(r.changes?t(`${r.changes} Änderungen`,`${r.changes} changes`):t('Nichts zu ändern.','Nothing to change.'))+' · ':'')+(r.ms/1000).toFixed(1)+' s')}
  catch(e){xmsg('wrmsg',e.message,true)}finally{go.disabled=false}}
async function writePic(file,into){xmsg('wrmsg',t('Lese das Bild …','Reading the picture …'));
  try{let blob;try{blob=typeof picSmall==='function'?await picSmall(file):file}catch{blob=file}
    const up=await (await api('/api/chat/image',{method:'POST',headers:{'Content-Type':blob.type||'image/jpeg'},body:blob})).json();
    const r=await (await api('/api/write/picture',xjson('POST',{id:up.id}))).json();
    if(!r.text){xmsg('wrmsg',t('Im Bild war kein Text zu lesen.','No text could be read in the picture.'),true);return}
    const el=$(into);el.value=(el.value.trim()?el.value.trim()+'\n\n':'')+r.text;xmsg('wrmsg',t('Text aus dem Bild übernommen. Bitte kurz prüfen.','Text taken from the picture. Please check it.'))}
  catch(e){xmsg('wrmsg',t('Bild nicht gelesen: ','Picture not read: ')+e.message,true)}}
async function writeDraft(){const b=$('wrdraft');b.disabled=true;
  try{const r=await (await api('/api/write/draft',xjson('POST',{to:$('wrto').value,subject:$('wrsubj').value,text:$('wrres').value}))).json();
    xmsg('wrmsg',t(`Entwurf liegt im Ordner „${r.folder}“. Nicht gesendet.`,`Draft is in the folder "${r.folder}". Not sent.`))}
  catch(e){xmsg('wrmsg',t('Kein Entwurf: ','No draft: ')+e.message,true)}finally{b.disabled=false}}
