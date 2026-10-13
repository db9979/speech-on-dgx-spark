// Ich → Schreibhilfe (schreib.py): a text in, the improved text out, with the changes marked by the panel.
// Nothing is kept on the Spark; a draft goes into the mailbox only on the person's click, never sent.
let WRITE_ON=false;
const WR={info:null,res:''};
async function showWrite(){const box=$('writebox');if(!box)return;if(!PROFILE||!WRITE_ON){box.innerHTML='';return}
  let d=null;try{d=await (await api('/api/write')).json()}catch{}
  WR.info=d;const on=!!(d&&d.on);
  const arts=d?d.arts:[],langs=d?d.langs:[];
  box.innerHTML=`<div class="intro">${t('Text hineinkopieren, Art wählen, fertig: korrigieren, glätten, kürzen, freundlicher oder förmlicher machen, übersetzen oder eine Antwort auf eine Mail entwerfen. Der Spark liest den Text nur, speichert nichts und sendet nie etwas.','Paste a text, pick what to do, done: correct, smooth, shorten, make friendlier or more formal, translate, or draft a reply to a mail. The Spark only reads the text, stores nothing and never sends anything.')}</div>
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
    <input type="file" id="wrfile" accept="image/*" hidden>`:''}
    ${on&&d.apps_spark?`<h3 style="margin:18px 0 4px">${t('In anderen Programmen','In other programs')}</h3>
    <div id="wrapps"></div>`:''}`;
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
  if(d.apps)writeApps();
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
// ---------------------------------------------------------------- the programs (Mac, Windows, Office, browser, iPhone)
async function writeApps(){const box=$('wrapps');if(!box)return;
  let d={devices:[],minutes:10,windows:''};try{d=await (await api('/api/profile/write/devices')).json()}catch{}
  const https=location.protocol==='https:',o=encodeURIComponent(location.origin);
  const dl=(href,label,ext)=>`<a class="b" href="${esc(href)}"${ext?' target="_blank" rel="noopener"':' download'}>${esc(label)}</a>`;
  box.innerHTML=`<div class="fh">${t('1. Programm holen, 2. „Programm koppeln“ und die Zeile ins Programm einfügen. Die Zeile gilt '+d.minutes+' Minuten und nur einmal.','1. Get the program, 2. "Pair a program" and paste the line into it. The line works for '+d.minutes+' minutes and once.')}</div>
    <ul class="facts">
      <li><span><b>Mac</b><br><small class="mut">${t('Schnellaktion für Apple Mail, Pages, Word, Excel und alle anderen Programme: Text markieren, Rechtsklick → Dienste → „Mit Spark verbessern“.','Quick action for Apple Mail, Pages, Word, Excel and every other program: mark text, right-click → Services → "Mit Spark verbessern".')}</small></span>${dl('/api/write/download/mac',t('Laden','Download'))}</li>
      <li><span><b>Windows (x64 und ARM)</b><br><small class="mut">${t('Teil des Spark-Begleiters (Ich → Begleiter): Text markieren, Strg+Alt+S, Vorschlag übernehmen. Gekoppelt wird dort.','Part of the Spark companion (Me → Companion): mark text, Ctrl+Alt+S, take the suggestion. Pair it there.')}</small></span>${dl(d.windows,t('Zur Seite','Open page'),1)}</li>
      <li><span><b>Office-Add-in</b><br><small class="mut">${https?t('Knopf in Outlook (auch im Web), Word und Excel. Datei laden und in Office als eigenes Add-in hinzufügen.','Button in Outlook (also on the web), Word and Excel. Download the file and add it in Office as a custom add-in.'):t('Office braucht https: öffne das Panel über seine https-Adresse, dann gibt es hier die Dateien.','Office needs https: open the panel at its https address to get the files here.')}</small></span>${https?['outlook','word','excel'].map(a=>dl('/api/write/office/'+a+'.xml?base='+o,a[0].toUpperCase()+a.slice(1))).join(' '):''}</li>
      <li><span><b>${t('Browser','Browser')}</b><br><small class="mut">${t('Erweiterung für Chrome, Edge und Firefox: Rechtsklick auf markierten Text in Gmail, iCloud, GMX, web.de oder Outlook im Web.','Extension for Chrome, Edge and Firefox: right-click marked text in Gmail, iCloud, GMX, web.de or Outlook on the web.')}</small></span>${dl('/api/write/download/browser',t('Laden','Download'))}</li>
      <li><span><b>iPhone</b><br><small class="mut">${t('In der Spark-App: Kurzbefehl „Text mit Spark verbessern“ oder Teilen → Spark → Text verbessern. Braucht keine Kopplung.','In the Spark app: shortcut "Improve text with Spark" or Share → Spark → Improve text. Needs no pairing.')}</small></span></li>
    </ul>
    <div class="row" style="margin-top:8px"><button class="b p" type="button" id="wrpair">${t('Programm koppeln','Pair a program')}</button></div>
    <div id="wrsetupbox" hidden><label>${t('Einrichtungszeile','Setup line')}</label><div class="rowin"><code id="wrsetup" style="overflow-wrap:anywhere"></code><button class="b" type="button" id="wrsetupcopy">${t('Kopieren','Copy')}</button></div></div>
    <div class="fh" id="wrpmsg"></div>
    <label>${t('Gekoppelte Programme','Paired programs')}</label>
    <ul class="facts">${d.devices.map(x=>`<li><span>${esc(x.name.replace(/^Schreibhilfe /,''))}${x.last?`<br><small class="mut">${t('zuletzt ','last ')+esc(new Date(x.last*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}))}</small>`:''}</span><button class="b" type="button" data-wrdel="${esc(x.id)}">${t('Entfernen','Remove')}</button></li>`).join('')||`<li class="mut">${t('Noch keins.','None yet.')}</li>`}</ul>`;
  $('wrpair').onclick=async()=>{xmsg('wrpmsg','…');
    try{const r=await (await api('/api/profile/write/pair',xjson('POST',{base:location.origin}))).json();
      $('wrsetup').textContent=r.setup;$('wrsetupbox').hidden=false;
      xmsg('wrpmsg',t('Diese Zeile ins Programm einfügen (gilt '+r.minutes+' Minuten, einmal). Im Office-Add-in reicht der Code '+r.code+'.','Paste this line into the program (works '+r.minutes+' minutes, once). In the Office add-in the code '+r.code+' is enough.'))}
    catch(e){xmsg('wrpmsg',e.message,true)}};
  $('wrsetupcopy').onclick=()=>copyString($('wrsetup').textContent,$('wrsetupcopy'));
  box.querySelectorAll('[data-wrdel]').forEach(b=>b.onclick=async()=>{if(!confirm(t('Programm entfernen? Sein Schlüssel gilt dann nicht mehr.','Remove the program? Its key stops working.')))return;
    try{await api('/api/profile/write/devices/'+encodeURIComponent(b.dataset.wrdel),{method:'DELETE'});writeApps()}catch(e){xmsg('wrpmsg',e.message,true)}})}
