// ---------------------------------------------------------------- Android app (android.py, android/ in the repo)
// Ich → Android-App: a download link with a one-time token (QR code for the phone's camera).
// Admin: Funktionen → Android-App shows which APK the Spark keeps and fetches it now.
// Inside the app (user agent "SparkAndroid/x.y.z") the page also takes two jumps from the app: #ask=<text>
// (shared text, only put into the text field, never sent) and #talk (the assistant button: start listening).
const IN_ANDROID=/SparkAndroid\/\d+\.\d+\.\d+/.test(navigator.userAgent);
// "Update in der App" (from app 1.3.0): the button is a fixed link the app catches (sparkapp:update); the page hands
// the app nothing, the app asks the Spark itself, checks the file and lets Android install it
const AND_VER=(navigator.userAgent.match(/SparkAndroid\/(\d+)\.(\d+)\.(\d+)/)||[]).slice(1).map(Number);
const andOlder=(a,b)=>{for(let i=0;i<3;i++){if((a[i]||0)!==(b[i]||0))return (a[i]||0)<(b[i]||0)}return false};
const AND_SELF=IN_ANDROID&&!andOlder(AND_VER,[1,3,0]);
async function showAnd(){const box=$('andbox');if(!box)return;if(!PROFILE||!AND_ON){box.innerHTML='';return}
  let d={on:false,app:null,minutes:30,notes:false};try{d=await (await api('/api/profile/android')).json()}catch{}
  const mb=n=>(n/1048576).toFixed(1).replace('.',L==='en'?'.':',')+' MB';
  box.innerHTML=`<div class="intro">${esc(t('Die App „Spark“ fürs Android-Handy, ohne Play Store: der Spark wie hier am Handy, dazu Mitteilungen bei geschlossener App, Assistenten-Taste und Teilen an Spark. Sie meldet sich wie ein Browser mit Name und PIN an.','The "Spark" app for Android phones, without the Play Store: the Spark like this page on the phone, plus notes while the app is closed, the assistant button and sharing to Spark. It signs in like a browser with name and PIN.'))}</div>
    ${d.on&&d.live_enabled?xsw('android_live',t('Mitteilungen sofort','Notes at once'),t('Die App hält eine Verbindung offen (stille Daueranzeige, etwas mehr Akku); sonst fragt sie alle 15 Minuten. Am Handy in den Android-Einstellungen bei Apps, Spark, Akku „Nicht eingeschränkt“ wählen.','The app keeps a connection open (a quiet lasting notice, a bit more battery); otherwise it asks every 15 minutes. On the phone pick "Unrestricted" in the Android settings under Apps, Spark, Battery.'))
      +(d.live?`<div class="fh">${esc(d.connected?t('Verbunden: Mitteilungen kommen sofort.','Connected: notes come at once.'):t('Noch nicht verbunden: die App einmal öffnen (ab Version 1.2.0).','Not connected yet: open the app once (from version 1.2.0).'))}</div>`:''):''}
    ${d.on?(d.app?`<div class="fh">${esc(t('Version','Version'))} ${esc(d.app.version)} · ${esc(mb(d.app.size))} · SHA-256 <code>${esc(d.app.sha256.slice(0,16))}…</code></div>
      ${AND_SELF&&d.update?(andOlder(AND_VER,d.app.version.split('.').map(Number))
        ?`<div class="fh">${esc(t('Diese App hat ','This app has ')+AND_VER.join('.')+t(': Die App lädt die neue Version von deinem Spark, prüft sie und Android fragt einmal „Aktualisieren“.',': the app loads the new version from your Spark, checks it and Android asks once "Update".'))}</div>
          <div class="row"><a class="b p" href="sparkapp:update">${esc(t('Jetzt aktualisieren','Update now'))}</a></div>`
        :`<div class="fh">${esc(t('Diese App ist aktuell.','This app is up to date.'))}</div>`):''}
      <div class="fh">${esc(IN_ANDROID?t('Neue Version: Link holen und antippen, das Handy lädt und installiert sie.','New version: get the link and tap it, the phone downloads and installs it.')
        :t('Link holen, den QR-Code mit der Kamera des Android-Handys scannen und die APK installieren. Das Handy fragt einmal, ob der Browser Apps installieren darf.','Get the link, scan the QR code with the Android phone camera and install the APK. The phone asks once whether the browser may install apps.'))}</div>
      <div class="row"><button class="b p" type="button" id="andlink">${esc(t('Download-Link holen','Get a download link'))}</button></div><div id="andqr"></div>`
      :`<div class="fh">${esc(t('Der Spark hat die App noch nicht geholt (Admin: Funktionen → Android-App → „App jetzt holen“).','The Spark has not fetched the app yet (admin: Features → Android app → "Fetch the app now").'))}</div>`)+
      `<div class="fh">${esc(d.notes?t('Mitteilungen: Die App hat in den letzten Stunden nachgefragt, Hinweise kommen dort an.','Notes: the app asked lately, notes arrive there.')
        :t('Mitteilungen: Die App hat noch nicht nachgefragt. In der App anmelden und Mitteilungen erlauben.','Notes: the app has not asked yet. Sign in in the app and allow notifications.'))}</div>`:''}
    <div class="fh" id="andmsg"></div>`;
  xbind(box,showAnd);
  if($('andlink'))$('andlink').onclick=async()=>{try{const r=await (await api('/api/profile/android/link',xjson('POST',{base:location.origin}))).json();
    const q=$('andqr');q.textContent='';if(r.qr&&!IN_ANDROID){const w=document.createElement('div');w.className='mfaqr andqr';w.innerHTML=r.qr;q.appendChild(w)}   // the SVG comes from the server's own QR drawer
    const a=document.createElement('a');a.href=r.url;a.textContent=t('APK laden','Download the APK');const p=document.createElement('div');p.className='fh';p.appendChild(a);
    p.appendChild(document.createTextNode(' · '+t('gilt ','valid for ')+r.minutes+t(' Minuten',' minutes')));q.appendChild(p)}
    catch(e){xmsg('andmsg',e.message,true)}}}
async function andAdmin(){if(!$('andadmin'))return;let d={};try{d=await (await api('/api/admin/android')).json()}catch{return}
  const st=$('andstate');st.dataset.need=d.app?'':'1';
  st.textContent=(d.app?t('App ','App ')+d.app.version+t(' auf dem Spark.',' on the Spark.'):t('Noch keine App auf dem Spark.','No app on the Spark yet.'))+(d.error?' '+d.error:'');
  $('andfetch').onclick=async()=>{st.textContent=t('Hole die App von GitHub …','Fetching the app from GitHub …');
    try{await api('/api/admin/android/fetch',xjson('POST'));andAdmin()}catch(e){st.textContent=e.message}}}
// jumps from the app (only inside it): shared text into the text field, the assistant button starts listening,
// shared photos (#pic=<ids>, already on the Spark through the app, pics.js) attached to the next question, and a tab
// of the app view from the shortcuts on the app icon (#tab=today, #tab=chats). Only moving and filling in, never sending.
function andJump(){if(!IN_ANDROID)return;const h=location.hash;let ask=null,pic=null,tab=null;
  if(h.startsWith('#ask=')){try{ask=decodeURIComponent(h.slice(5)).slice(0,4000)}catch{ask=null}}
  else if(h.startsWith('#pic=')){pic=h.slice(5).split(',').filter(x=>/^[A-Za-z0-9_-]{22}$/.test(x)).slice(0,3)}
  else if(/^#tab=(spark|chats|today|docs|me)$/.test(h))tab=h.slice(5);
  else if(h!=='#talk')return;
  try{history.replaceState(history.state,'',location.pathname+location.search)}catch{}
  const go=()=>{if(typeof PROFILE==='undefined'||!$('chattext'))return setTimeout(go,300);
    if(tab){const b=document.querySelector(`#aptabs button[data-tab=${tab}]`);if(b&&!b.hidden)b.click();return}
    const chat=document.querySelector('nav button[data-s=chat]');if(chat)chat.click();
    if(pic){if(typeof picTake==='function')picTake(pic);return}
    if(ask!==null){$('chattext').value=ask;$('chattext').focus()}else if($('talk'))$('talk').click()};
  setTimeout(go,600)}
addEventListener('load',andJump);addEventListener('hashchange',andJump);
