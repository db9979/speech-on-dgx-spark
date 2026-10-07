// First-start wizard for the admin: password, language model, voice, profiles, access and
// features, then a live check. Opens once after the first admin login; System und Update can
// start it again. Every step saves on "Weiter"; "Überspringen" leaves the step as it is.
const wiz={step:0,cfg:null,steps:['hello','pw','llm','voice','prof','feat','done']};
const jreq=(m,b)=>({method:m,headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
async function wizCfg(){wiz.cfg=await (await api('/api/config')).json();return wiz.cfg}
async function wizSave(change){const c=JSON.parse(JSON.stringify(await wizCfg()));change(c);
  await api('/api/config',jreq('PUT',c));wiz.cfg=c}
function wizMsg(x,err){$('wizmsg').className=err?'err':'mut';$('wizmsg').textContent=x||''}
async function wizShow(){const s=wiz.steps[wiz.step],b=$('wizbody');wizMsg('');
  $('wizstep').textContent=t('Schritt ','Step ')+(wiz.step+1)+t(' von ',' of ')+wiz.steps.length;
  $('wizback').style.visibility=wiz.step?'visible':'hidden';$('wizskip').style.display=['hello','done'].includes(s)?'none':'';
  $('wiznext').textContent=s==='done'?t('Fertig','Done'):t('Weiter','Next');
  const c=wiz.cfg||await wizCfg();
  if(s==='hello')b.innerHTML=`<h2>${t('Willkommen','Welcome')}</h2><div class="intro">${t('In ein paar Schritten ist der Assistent eingerichtet: Passwort, Sprachmodell, Stimme, Profile und Funktionen. Alles lässt sich später unter Einstellungen ändern.','A few steps set up the assistant: password, language model, voice, profiles and features. Everything can be changed later under Settings.')}</div>`;
  if(s==='pw')b.innerHTML=`<h2>${t('Panel-Passwort','Panel password')}</h2><div class="intro">${t('Das Passwort vom Installer ist zufällig. Wenn du ein eigenes willst, trag es hier ein; sonst überspringen.','The installer\'s password is random. Enter your own here if you like, otherwise skip.')}</div>
    <label>${t('Jetziges Passwort','Current password')}</label><input type="password" id="wpwold" autocomplete="current-password">
    <label>${t('Neues Passwort (mindestens 6 Zeichen)','New password (at least 6 characters)')}</label><input type="password" id="wpwnew" autocomplete="new-password">`;
  if(s==='llm')b.innerHTML=`<h2>${t('Sprachmodell','Language model')}</h2><div class="intro">${t('Der Assistent denkt mit dem LLM von dgx-spark-qwen38 (oder einem anderen OpenAI-kompatiblen Server).','The assistant thinks with the LLM of dgx-spark-qwen38 (or another OpenAI-compatible server).')}</div>
    <label>${t('Adresse','Address')}</label><input id="wllmurl" value="${esc(c.chat.llm_url)}">
    <label>${t('Schlüssel','Key')}</label><input type="password" id="wllmkey" placeholder="${c.chat.llm_key?t('gespeichert, leer lassen = behalten','stored, leave empty to keep'):t('leer, wenn keiner nötig','empty if none needed')}" autocomplete="new-password">
    <div class="row" style="margin-top:8px"><button class="b" id="wllmtest" type="button">${t('Verbindung prüfen','Test connection')}</button><span id="wllmres" class="mut"></span></div>`;
  if(s==='voice'){b.innerHTML=`<h2>${t('Stimme','Voice')}</h2><div class="intro">${t('Mit dieser Stimme antwortet der Assistent, solange ein Profil nichts anderes wählt. Die eingebauten Sprecher sind keine deutschen Muttersprachler; eine geklonte deutsche Stimme (Nutzer → Stimmen) klingt natürlicher.','The assistant answers with this voice unless a profile picks another. The built-in speakers are not native German speakers; a cloned German voice (Users → Voices) sounds more natural.')}</div>
    <label>${t('Stimme','Voice')}</label><div class="rowin"><select id="wvoice"></select><button class="b" id="wvplay" type="button">${t('Anhören','Listen')}</button></div><audio id="wvaudio" style="display:none"></audio>`;
    let v={voices:[]};try{v=await (await api('/api/tts/voices')).json()}catch{}
    $('wvoice').innerHTML=(v.voices||[]).map(x=>`<option${x===c.tts.default_voice?' selected':''}>${esc(x)}</option>`).join('')||`<option value="">${t('(Sprachausgabe lädt noch)','(speech output still loading)')}</option>`;
    $('wvplay').onclick=async()=>{wizMsg(t('spricht …','speaking …'));try{const r=await api('/api/test/tts',jreq('POST',{input:t('Hallo, ich bin dein Assistent auf dem Spark.','Hello, I am your assistant on the Spark.'),voice:$('wvoice').value||null,response_format:'wav'}));
      $('wvaudio').src=URL.createObjectURL(await r.blob());await $('wvaudio').play();wizMsg('')}catch(e){wizMsg(e.message,true)}}}
  if(s==='prof'){b.innerHTML=`<h2>${t('Profile','Profiles')}</h2><div class="intro">${t('Mit einem Profil merkt sich der Assistent Dinge nur für diese Person, mit eigenen Gesprächen, Dokumenten, Kalendern und Smart Home. Anmeldung mit Name und PIN.','With a profile the assistant remembers things just for that person, with their own conversations, documents, calendars and smart home. Sign-in with name and PIN.')}</div>
    <ul class="facts" id="wproflist"></ul><div class="two2"><div><label>Name</label><input id="wpname" autocomplete="off"></div><div><label>PIN</label><input id="wppin" type="password" autocomplete="new-password"></div></div>
    <div class="row" style="margin-top:8px"><button class="b" id="wpadd" type="button">${t('Profil anlegen','Create profile')}</button></div>`;
    const list=async()=>{const d=await (await api('/api/admin/profiles')).json();$('wproflist').innerHTML=d.users.map(u=>`<li><span>${esc(u.name)}</span></li>`).join('')||`<li class="mut">${t('Noch keins.','None yet.')}</li>`};
    await list();$('wpadd').onclick=async()=>{try{await api('/api/admin/profiles',jreq('POST',{name:$('wpname').value,pin:$('wppin').value}));$('wpname').value=$('wppin').value='';wizMsg(t('Angelegt.','Created.'));list()}catch(e){wizMsg(e.message,true)}}}
  if(s==='feat'){const ch=c.chat,sw=(k,l,h)=>`<label class="chk"><input type="checkbox" id="wf_${k}"${ch[k]?' checked':''}> ${l}</label><div class="fh">${h}</div>`;
    b.innerHTML=`<h2>${t('Zugang und Funktionen','Access and features')}</h2>`+
      sw('public',t('Assistent ohne Passwort','Assistant without password'),t('An: alle im Netz dürfen fragen, auch Gäste (es wird nichts für sie gespeichert). Aus: nur Profile. Hinter einem Proxy im Internet besser aus.','On: everyone on the network may ask, guests too (nothing is stored for them). Off: profiles only. Behind a proxy on the internet better off.'))+
      sw('memory',t('Gedächtnis','Memory'),t('Merkt sich Dinge pro Profil.','Remembers things per profile.'))+
      sw('history',t('Frühere Gespräche','Earlier conversations'),t('Schlägt in alten Gesprächen nach und lernt daraus.','Looks things up in old conversations and learns from them.'))+
      sw('reminders',t('Erinnerungen und Timer','Reminders and timers'),'')+sw('calendar',t('Kalender und Tagesbriefing','Calendar and daily briefing'),'')+
      sw('homeassistant','Home Assistant',t('Jedes Profil verbindet sein eigenes.','Each profile connects its own.'))+
      sw('search',t('Websuche','Web search'),t('Über deine SearXNG-Instanz:','Through your SearXNG instance:'))+`<input id="wf_search_url" placeholder="http://192.168.1.20:8080" value="${esc(ch.search_url||'')}">`}
  if(s==='done'){b.innerHTML=`<h2>${t('Fertig','Done')}</h2><div class="intro">${t('Zum Schluss probiert der Spark einmal alles aus: das Sprachmodell antwortet, die Sprachausgabe spricht, die Spracherkennung versteht es wieder.','Finally the Spark tries everything once: the language model answers, speech output speaks, speech recognition understands it again.')}</div><table><tbody id="wlive"></tbody></table>`;
    $('wlive').innerHTML=`<tr><td class="mut">${t('prüft …','checking …')}</td></tr>`;
    try{const r=await (await api('/api/livecheck',{method:'POST'})).json();
      $('wlive').innerHTML=(r.steps||[]).map(x=>`<tr><td style="width:40%">${x.ok===true?'✅':x.ok===false?'❌':'➖'} ${esc(LIVE[x.name]||x.name)}</td><td class="mut">${esc(x.detail||'')}</td></tr>`).join('')}catch(e){wizMsg(e.message,true)}}
  if($('wllmtest'))$('wllmtest').onclick=async()=>{$('wllmres').textContent=t('prüfe …','testing …');
    try{const r=await (await api('/api/setup/llm-test',jreq('POST',{url:$('wllmurl').value.trim(),key:$('wllmkey').value}))).json();
      $('wllmres').innerHTML=r.ok?'✅ '+esc(r.models.join(', ')):`<span class="err">${esc(r.error)}</span>`}catch(e){$('wllmres').innerHTML=`<span class="err">${esc(e.message)}</span>`}}}
async function wizApply(){const s=wiz.steps[wiz.step];
  if(s==='pw'&&$('wpwnew').value){await api('/api/password',jreq('POST',{old:$('wpwold').value,new:$('wpwnew').value}))}
  if(s==='llm'){const url=$('wllmurl').value.trim(),key=$('wllmkey').value;if(url!==wiz.cfg.chat.llm_url||key)await wizSave(c=>{c.chat.llm_url=url;if(key)c.chat.llm_key=key})}
  if(s==='voice'&&$('wvoice').value&&$('wvoice').value!==wiz.cfg.tts.default_voice)await wizSave(c=>{c.tts.default_voice=$('wvoice').value})
  if(s==='feat')await wizSave(c=>{for(const k of ['public','memory','history','reminders','calendar','homeassistant','search'])c.chat[k]=$('wf_'+k).checked;c.chat.search_url=$('wf_search_url').value.trim()})
  if(s==='done'){await api('/api/setup',jreq('POST',{done:true}));$('wizmodal').style.display='none';goSec('chat');return false}
  return true}
$('wiznext').onclick=async()=>{$('wiznext').disabled=true;try{if(await wizApply()){wiz.step++;await wizShow()}}catch(e){wizMsg(e.message,true)}$('wiznext').disabled=false};
$('wizskip').onclick=async()=>{wiz.step++;await wizShow()};
$('wizback').onclick=async()=>{wiz.step=Math.max(0,wiz.step-1);await wizShow()};
$('wizclose').onclick=async()=>{$('wizmodal').style.display='none';await api('/api/setup',jreq('POST',{done:true})).catch(()=>{})};
window.openWizard=async()=>{wiz.step=0;wiz.cfg=null;$('wizmodal').style.display='grid';await wizShow()};
async function wizCheck(){try{const s=await (await api('/api/setup')).json();if(!s.done)openWizard()}catch{}}
