// "Ich" → Lautsprecher (esp32.py): own ESP32-S3 speakers. Set up over USB from Chrome/Edge (Web Serial,
// esptool.js) or by the 6-digit code a board shows. The Wi-Fi password only goes into the board's
// settings block (NVS), which is put together here in the browser; the Spark never sees it.
let ESP_ON=false;
// ---------------------------------------------------------------- NVS image (ESP-IDF format version 2)
// Same bytes as Espressif's nvs_partition_gen for the same entries (checked when this was written).
const NVS_CRC=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0}return t})();
// zlib.crc32(data, 0xFFFFFFFF), as ESP-IDF computes it for NVS
function crc32le(b){let c=0;for(const x of b)c=NVS_CRC[(c^x)&255]^(c>>>8);return (~c)>>>0}
function nvsImage(size,spaces){
  const PAGE=4096,img=new Uint8Array(size).fill(0xFF),enc=new TextEncoder(),ents=[];let ns=0;
  const entry=(nsi,type,key,data,span=1)=>{const e=new Uint8Array(32).fill(0xFF);e[0]=nsi;e[1]=type;e[2]=span;
    const k=enc.encode(key);if(k.length>15)throw new Error('NVS key too long: '+key);e.fill(0,8,24);e.set(k,8);e.set(data,24);
    new DataView(e.buffer).setUint32(4,crc32le(new Uint8Array([...e.slice(0,4),...e.slice(8,32)])),true);return e};
  for(const [name,items] of Object.entries(spaces)){ns++;
    const d=new Uint8Array(8).fill(0xFF);d[0]=ns;ents.push([entry(0,0x01,name,d)]);
    for(const [key,val] of Object.entries(items)){
      if(typeof val==='number'){const d=new Uint8Array(8).fill(0xFF);new DataView(d.buffer).setInt32(0,val,true);ents.push([entry(ns,0x14,key,d)]);continue}
      const s=enc.encode(String(val)+'\0');if(s.length>4000)throw new Error('NVS value too long: '+key);
      const n=Math.ceil(s.length/32),body=new Uint8Array(n*32).fill(0xFF);body.set(s);
      const d=new Uint8Array(8).fill(0xFF),v=new DataView(d.buffer);v.setUint16(0,s.length,true);v.setUint32(4,crc32le(s),true);
      const list=[entry(ns,0x21,key,d,n+1)];for(let i=0;i<n;i++)list.push(body.slice(i*32,i*32+32));ents.push(list)}}
  let page=0,slot=0;const pages=[0];
  for(const list of ents){if(slot+list.length>126){page++;slot=0;if((page+2)*PAGE>size)throw new Error('NVS full');pages.push(page)}
    for(const e of list){img.set(e,page*PAGE+64+slot*32);img[page*PAGE+32+(slot>>2)]&=~(1<<((slot&3)*2))&0xFF;slot++}}
  for(const p of pages){const h=new Uint8Array(32).fill(0xFF),v=new DataView(h.buffer);
    v.setUint32(0,p<page?0xFFFFFFFC:0xFFFFFFFE,true);v.setUint32(4,p,true);h[8]=0xFE;v.setUint32(28,crc32le(h.slice(4,28)),true);img.set(h,p*PAGE)}
  return img}
// the NVS partition of the firmware's own partition table (type data, subtype nvs)
function nvsPartition(table){const v=new DataView(table.buffer,table.byteOffset,table.byteLength);
  for(let o=0;o+32<=table.length;o+=32){if(v.getUint16(o,true)!==0x50AA)break;if(table[o+2]===1&&table[o+3]===2)return {offset:v.getUint32(o+4,true),size:v.getUint32(o+8,true)}}
  throw new Error(t('Keine NVS-Partition in der Firmware.','No NVS partition in the firmware.'))}
async function sha256hex(u8){const h=new Uint8Array(await crypto.subtle.digest('SHA-256',u8));return [...h].map(x=>x.toString(16).padStart(2,'0')).join('')}
// ---------------------------------------------------------------- USB
function espLog(x,err){ESP_MSG=[x,!!err];const m=$('espflog');if(!m)return;m.textContent=x;m.className='fh'+(err?' err':'')}
function espBar(p){const b=$('espbar');if(b){b.style.display=p==null?'none':'block';b.firstElementChild.style.width=Math.round((p||0)*100)+'%'}}
async function espConnect(){
  if(!('serial' in navigator))throw new Error(t('Dieser Browser kann nicht per USB flashen. Bitte Chrome oder Edge am PC oder Mac nehmen.','This browser cannot flash over USB. Please use Chrome or Edge on a PC or Mac.'));
  if(!window.isSecureContext)throw new Error(t('Nur über https (oder localhost) erlaubt der Browser USB.','The browser only allows USB over https (or localhost).'));
  const port=await navigator.serial.requestPort({});
  const {ESPLoader,Transport}=await import('/static/js/esptool.js?v='+encodeURIComponent(SPARK_VER));
  const transport=new Transport(port,true);
  const term={clean(){},writeLine(){},write(){}};
  const loader=new ESPLoader({transport,baudrate:460800,romBaudrate:115200,terminal:term});
  espLog(t('Verbinde mit dem Board … (klappt es nicht: BOOT gedrückt halten, kurz RESET drücken, BOOT loslassen)','Connecting to the board … (if it fails: hold BOOT, press RESET briefly, release BOOT)'));
  const chip=await loader.main();
  const mac=await loader.chip.readMac(loader).catch(()=>'');
  const flashKB=await loader.getFlashSize().catch(()=>0);
  return {port,transport,loader,chip,mac,flashMB:flashKB?flashKB/1024:0}}
async function espParts(parts){const out=[];let i=0;
  for(const p of parts){espLog(t('Lade Firmware vom Spark … ','Loading firmware from the Spark … ')+(++i)+'/'+parts.length);
    const r=await fetch(p.url);if(!r.ok)throw new Error(p.file+': '+r.status);const u8=new Uint8Array(await r.arrayBuffer());
    if(await sha256hex(u8)!==p.sha256)throw new Error(p.file+t(': Prüfsumme passt nicht.',': checksum does not match.'));out.push({address:p.address,u8,file:p.file})}
  return out}
async function espWrite(c,files){espBar(0);
  await c.loader.writeFlash({fileArray:files.map(f=>({address:f.address,data:c.loader.ui8ToBstr(f.u8)})),flashSize:'keep',flashMode:'keep',flashFreq:'keep',
    eraseAll:false,compress:true,reportProgress:(i,w,tot)=>{espBar((i+w/tot)/files.length);espLog(t('Schreibe ','Writing ')+(i+1)+'/'+files.length+' … '+Math.round(w/tot*100)+' %')}});
  await c.loader.after('hard_reset');await c.transport.disconnect().catch(()=>{});espBar(null)}
function espChip(c,need){if(!/ESP32-S3/i.test(c.chip))throw new Error(t('Das ist ein ','This is an ')+c.chip+t(', gebraucht wird ein ESP32-S3.',', an ESP32-S3 is needed.'));
  const mb=parseInt(need)||16;if(c.flashMB&&c.flashMB<mb)throw new Error(t('Das Board hat ','The board has ')+c.flashMB+t(' MB Flash, die Firmware braucht ',' MB flash, the firmware needs ')+mb+' MB.')}
// a self-signed certificate (port 31443) is refused by the board
function espBaseHint(b){if(/^https:\/\/[^/]*:31443$/.test(b)||/^https:\/\/\d+\.\d+\.\d+\.\d+/.test(b))
  return t('Achtung: Diese Adresse hat ein selbst signiertes Zertifikat, das nimmt das Board nicht an. Nimm die Adresse deines Reverse Proxys oder http://<Spark-IP>:31080 im Heimnetz.','Careful: this address has a self-signed certificate, the board refuses it. Use your reverse proxy address or http://<Spark IP>:31080 at home.');
  if(/^http:\/\//.test(b))return t('Ohne https: Der Geräteschlüssel geht im Heimnetz unverschlüsselt. Unterwegs geht es so nicht.','Without https: the device key travels unencrypted in your home network. It does not work away from home.');
  return ''}
// ---------------------------------------------------------------- the page
// Ich → Lautsprecher: the switch, a list of the speakers and the two ways to add one. A speaker opens its
// own page: Klang, Raum-Modus, Stimme, Firmware, Prüfen, Entfernen. One row per setting, one sentence each.
let ESP_VIEW=null,ESP_MSG=null;   // view: null = list, 'usb' / 'code' = add a speaker, else the device id
const espRow=(l,h,ctl='')=>`<div class="setrow"><div class="lbl"><b>${l}</b>${h?`<span>${h}</span>`:''}</div>${ctl}</div>`;
const espTgl=(id,on)=>`<label class="tgl"><input type="checkbox" id="${id}"${on?' checked':''}><i></i></label>`;
const espSel=(id,opts,val)=>`<select id="${id}">${opts.map(([v,l])=>`<option value="${esc(v)}"${v===val?' selected':''}>${esc(l)}</option>`).join('')}</select>`;
const espGrp=l=>`<div class="mgrp espgrp">${esc(l)}</div>`;
const espDate=s=>s?new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'–';
const espHM=ms=>new Date(ms).toLocaleTimeString(L==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'});
const espFoot=()=>`<div id="espbar" class="ulbar" style="display:none;margin-top:10px"><i style="width:0"></i></div><div class="fh${ESP_MSG&&ESP_MSG[1]?' err':''}" id="espflog">${esc(ESP_MSG?ESP_MSG[0]:'')}</div>`;
function espGo(v){ESP_VIEW=v;ESP_MSG=null;clearInterval(ESP_LIVE);showEsp().then(()=>{const b=$('espbox');b&&b.scrollIntoView&&b.scrollIntoView({block:'start'})})}
function espState(x){const s=[];
  if(x.room_until)s.push(t('Raum-Modus bis ','Room mode until ')+espHM(x.room_until));else if(x.room_waits)s.push(t('Raum-Modus beim nächsten Weckwort','room mode at the next wake word'));
  if(x.newer)s.push(x.update?t('Update beim nächsten Start','update at next start'):t('Update da','update available'));
  if(!x.seen)s.push(t('hat sich noch nie gemeldet','never checked in'));else if(!x.online)s.push(t('zuletzt ','last ')+espDate(x.seen));
  return s.join(' · ')}
async function showEsp(){const box=$('espbox');if(!box)return;if(!PROFILE||!ESP_ON){box.innerHTML='';return}
  let d={on:false,devices:[],firmware:null,base:location.origin};try{d=await (await api('/api/profile/esp32')).json()}catch{}
  const x=d.devices.find(v=>v.id===ESP_VIEW);
  if(!d.on||(ESP_VIEW&&ESP_VIEW!=='usb'&&ESP_VIEW!=='code'&&!x))ESP_VIEW=null;
  const back=`<div class="row espback"><button class="b" type="button" id="espback">← ${t('Alle Lautsprecher','All speakers')}</button></div>`;
  if(!ESP_VIEW){box.innerHTML=espList(d);if(typeof guidesMe==='function')guidesMe('espbox')}
  else if(ESP_VIEW==='usb')box.innerHTML=back+espUsb(d);
  else if(ESP_VIEW==='code')box.innerHTML=back+espCode();
  else box.innerHTML=back+espOne(d,x);
  if($('espback'))$('espback').onclick=()=>espGo(null);
  xbind(box,showEsp);
  box.querySelectorAll('[data-ego]').forEach(b=>b.onclick=()=>espGo(b.dataset.ego));
  if(ESP_VIEW==='usb')espUsbBind(d);else if(ESP_VIEW==='code')espCodeBind();else if(x)espOneBind(d,x)}
// the list: the switch, my speakers, the ways to add one
function espList(d){
  let h=xsw('esp_on',t('Eigene Lautsprecher für mich','Own speakers for me'),t('Ohne diesen Schalter nimmt der Spark keine Verbindung deiner Lautsprecher an.','Without this switch the Spark accepts no connection from your speakers.'));
  if(!d.on)return h+espFoot();
  h+=espGrp(t('Meine Lautsprecher','My speakers'))+`<div class="overlist esplist">`+(d.devices.map(x=>`<button type="button" class="overrow" data-ego="${esc(x.id)}"><b>${esc(x.name)}${x.online?` <span class="pill ok">● ${t('verbunden','connected')}</span>`:''}</b><span>${esc(espState(x))}</span></button>`).join('')
    ||`<div class="fh">${t('Noch kein Lautsprecher eingerichtet.','No speaker set up yet.')}</div>`)+`</div>`;
  h+=espGrp(t('Lautsprecher hinzufügen','Add a speaker'))+`<div class="overlist esplist">
    <button type="button" class="overrow" data-ego="usb"><b>${t('Neues Board per USB einrichten','Set up a new board over USB')}</b><span>${t('Chrome oder Edge am PC','Chrome or Edge on a PC')}</span></button>
    <button type="button" class="overrow" data-ego="code"><b>${t('Board zeigt einen Code','Board shows a code')}</b><span>${t('hat schon die Spark-Firmware','already has the Spark firmware')}</span></button></div>`;
  if(!d.firmware)h+=`<div class="fh err">${t('Auf dem Spark liegt noch keine Firmware. Der Admin holt sie unter Einstellungen → Funktionen → Eigene Lautsprecher.','There is no firmware on the Spark yet. The admin fetches it under Settings → Features → Own speakers.')}</div>`;
  return h+espFoot()}
const espVars=d=>d.firmware?Object.entries(d.firmware.variants).map(([k,v])=>[k,v.label]):[];
const espUsbOk=()=>'serial' in navigator&&window.isSecureContext;
function espUsb(d){const fw=d.firmware;
  return `<h3 class="esph">${t('Neues Board per USB einrichten','Set up a new board over USB')}</h3>
    <div class="fh">${t('Board mit einem Datenkabel (nicht nur Ladekabel) an diesen PC stecken. Alles darauf wird überschrieben.','Plug the board into this PC with a data cable (not a charge-only cable). Everything on it is overwritten.')}</div>
    ${espUsbOk()?'':`<div class="fh err">${t('Dieser Browser kann nicht per USB schreiben. Bitte Chrome oder Edge am PC oder Mac nehmen, die Seite über https.','This browser cannot write over USB. Please use Chrome or Edge on a PC or Mac, the page over https.')}</div>`}
    ${fw?'':`<div class="fh err">${t('Auf dem Spark liegt noch keine Firmware (Admin: Funktionen → Eigene Lautsprecher).','There is no firmware on the Spark yet (admin: Features → Own speakers).')}</div>`}
    <label>${t('Name','Name')}</label><input id="espname" placeholder="${t('z. B. Küche','e.g. Kitchen')}" autocomplete="off">
    <label>${t('Board','Board')}</label>${espSel('espvar',espVars(d))}
    <div class="two2"><div><label>${t('WLAN-Name','Wi-Fi name')}</label><input id="espssid" autocomplete="off" autocapitalize="off"></div><div><label>${t('WLAN-Passwort','Wi-Fi password')}</label><input id="esppw" type="password" autocomplete="new-password"></div></div>
    <div class="fh">${t('Nur 2,4-GHz-WLAN. Das Passwort geht nur aufs Board, nicht an den Spark.','2.4 GHz Wi-Fi only. The password only goes onto the board, not to the Spark.')}</div>
    <label>${t('Adresse des Spark für das Gerät','Spark address for the device')}</label><input id="espbase" value="${esc(d.base)}"${d.fixed_base?' readonly':''} autocapitalize="off" autocomplete="off">
    <div class="fh">${d.fixed_base?t('Vom Admin festgelegt.','Set by the admin.'):''} <span id="espbasehint"></span></div>
    <div class="row" style="margin-top:8px"><button class="b p" type="button" id="espflash"${fw&&espUsbOk()?'':' disabled'}>${t('Board verbinden und einrichten','Connect board and set up')}</button></div>${espFoot()}`}
function espUsbBind(d){const hint=()=>{$('espbasehint').textContent=espBaseHint($('espbase').value.trim().replace(/\/$/,''))};$('espbase').oninput=hint;hint();
  $('espflash').onclick=()=>espSetup(d.firmware).catch(e=>{espBar(null);espLog(t('Nicht eingerichtet: ','Not set up: ')+e.message,true)})}
function espCode(){
  return `<h3 class="esph">${t('Board mit Code koppeln','Pair a board with a code')}</h3>
    <div class="fh">${t('Für ein Board, das schon die Spark-Firmware hat: Beim Start zeigt oder sagt es einen 6-stelligen Code.','For a board that already has the Spark firmware: at start it shows or says a 6-digit code.')}</div>
    <div class="two2"><div><label>${t('Code','Code')}</label><input id="espcode" inputmode="numeric" maxlength="7" autocomplete="off"></div><div><label>${t('Name','Name')}</label><input id="espcname" autocomplete="off"></div></div>
    <div class="row" style="margin-top:8px"><button class="b p" type="button" id="esppair">${t('Koppeln','Pair')}</button></div>${espFoot()}`}
function espCodeBind(){$('esppair').onclick=async()=>{try{await api('/api/profile/esp32/pair',xjson('POST',{code:$('espcode').value,name:$('espcname').value}));
  ESP_VIEW=null;ESP_MSG=[t('Gekoppelt. Der Lautsprecher verbindet sich gleich.','Paired. The speaker connects in a moment.'),false];await showEsp()}catch(e){espLog(e.message,true)}}}
// one speaker
function espOne(d,x){
  const lvl=[['questions',t('nur Fragen','questions only')],['hints',t('auch Hinweise','also hints')],['all',t('auch Kommentare','also comments')]];
  const kinds=[['q',t('Offene Fragen beantworten','Answer open questions')],['cal',t('Termine vorschlagen','Offer appointments')],['ha',t('Raumklima und Licht','Room climate and light')],['shop',t('Einkaufsliste','Shopping list')],
    ['timer',t('Timer','Timers')],['remind',t('Erinnerungen','Reminders')],['conv',t('Umrechnen','Unit conversion')]];
  const k=x.room_kinds||{},kon=kinds.filter(([v])=>k[v]!==false).length;
  let h=`<div class="esptop"><div><b class="espname">${esc(x.name)}</b>${x.online?` <span class="pill ok">● ${t('verbunden','connected')}</span>`:''}
      <div class="fh">${esc(x.board||'')}${x.board?' · ':''}${x.seen?t('zuletzt ','last ')+espDate(x.seen):t('hat sich noch nie gemeldet','never checked in')}</div></div>
      <button class="b" type="button" id="espren">${t('Umbenennen','Rename')}</button></div>`;
  h+=espGrp(t('Klang','Sound'))
    +espRow(t('Lautstärke','Volume'),t('Gilt sofort, sonst beim nächsten Verbinden.','Applies at once, else at the next connection.'),`<input type="range" min="0" max="100" step="5" value="${x.volume??70}" id="espvol"><output id="espvolv">${x.volume??'–'}</output>`)
    +espRow(t('Mikrofon','Microphone'),t('Empfindlicher, wenn er dich aus der Ferne nicht hört.','More sensitive when it does not hear you from afar.'),espSel('espmic',[['low',t('weniger empfindlich','less sensitive')],['normal',t('normal','normal')],['high',t('empfindlicher','more sensitive')]],x.mic));
  if(d.room){
    const now=x.room_until?[t('Hört zu bis ','Listening until ')+espHM(x.room_until)+'.',t('Beenden','Stop'),'0']:x.room_waits?[t('Startet beim nächsten „Jarvis“ oder Knopfdruck.','Starts at the next "Jarvis" or button press.'),t('Nicht starten','Do not start'),'0']
      :[t('Hört dem Gespräch im Raum zu und hilft in Pausen; schläft er, startet es beim nächsten „Jarvis“.','Listens to the conversation in the room and helps in pauses; when it sleeps, it starts at the next "Jarvis".'),t('Starten','Start'),'1'];
    h+=espGrp(t('Raum-Modus','Room mode'))
      +espRow(t('Jetzt zuhören','Listen now'),now[0],`<button class="b" type="button" id="esproom" data-on="${now[2]}">${now[1]}</button>`)
      +espRow(t('Dauer','Duration'),t('Danach geht er von selbst aus.','Then it switches off by itself.'),espSel('espmins',[15,30,60,120,240].map(n=>[String(n),n+' '+t('Minuten','minutes')]),String(x.room_mins)))
      +espRow(t('Wie viel er sagen darf','How much it may say'),t('„Auch Kommentare“ ist am wenigsten zuverlässig.','"Also comments" is the least reliable.'),espSel('esplevel',lvl,x.room_level))
      +`<details class="espkinds"><summary>${t('Was er anbieten darf','What it may offer')} <small class="mut">(${kon} ${t('von','of')} ${kinds.length})</small></summary>`
      +kinds.map(([v,l])=>espRow(esc(l),'',`<label class="tgl"><input type="checkbox" data-ekind="${v}"${k[v]!==false?' checked':''}><i></i></label>`)).join('')+`</details>`
      +espRow(t('Raum in Home Assistant','Room in Home Assistant'),t('Für Raumklima, Licht und den Fernseher.','For room climate, light and the TV.'),`<input id="esparea" value="${esc(x.room_area||'')}" placeholder="${t('z. B. Wohnzimmer','e.g. Living room')}" autocomplete="off">`)
      +espRow(t('Genauer erkennen','Detect more'),t('Das Sprachmodell sucht alle zwei Minuten nach Übersehenem; kostet Rechenzeit.','The language model looks for missed things every two minutes; costs GPU time.'),espTgl('espdetect',x.room_detect))
      +espRow(t('Erinnerungston','Reminder tone'),t('Alle 15 Minuten ein leiser Ton, damit niemand vergisst, dass er zuhört. Nie in Ruhezeiten.','A soft tone every 15 minutes, so nobody forgets it listens. Never in quiet hours.'),espTgl('espping',x.room_ping));
    if(RV_ON)h+=espRow(t('Wem er zuhört','Who it listens to'),t('Nur bekannte Stimmen gilt erst, wenn deine Stimme über diesen Lautsprecher angelernt ist.','Known voices only applies once your voice was taught through this speaker.'),
        espSel('espvoices',[['all',t('allen','everybody')],['tv',t('bekannten bei TV','known ones at TV')],['known',t('nur bekannten','known ones only')]],x.room_voices))
      +espRow(t('Probelauf','Trial'),t('Überhört noch nichts, zählt nur; Ergebnis im Protokoll und unter Prüfen.','Ignores nothing yet, only counts; result in the log and under Check.'),espTgl('espprobe',x.room_probe!==false))}
  if(d.speaker_id)h+=espGrp(t('Stimme','Voice'))
    +espRow(t('Meine Stimme über diesen Lautsprecher','My voice through this speaker'),x.voice_waits?t('Vorgemerkt: sag „Jarvis“ oder drück den Knopf, dann drei Sätze.','Queued: say "Jarvis" or press the button, then three sentences.')
      :x.voice_here?t('Angelernt (','Taught (')+x.voice_here+t(' Aufnahmen). Danach erkennt er dich auch über sein Mikrofon.',' recordings). It then knows you through its microphone too.'):t('Noch nicht angelernt. Drei Sätze, damit er dich über sein Mikrofon erkennt.','Not taught yet. Three sentences so it knows you through its microphone.'),
      `<button class="b" type="button" id="espvoice">${x.voice_here?t('Neu anlernen','Teach again'):t('Anlernen','Teach')}</button>`);
  h+=espGrp(t('Firmware','Firmware'))
    +espRow(esc(x.fw||'?')+(x.newer?' · '+t('neue ist da','a new one is there'):''),x.newer?(x.update?t('Kommt beim nächsten Start des Boards.','Comes at the board\'s next start.'):t('Holt er beim nächsten Start, wenn „Updates von selbst“ an ist.','It fetches it at its next start when "Updates by themselves" is on.')):t('Aktuell.','Up to date.'),
      x.newer&&!x.update?`<button class="b" type="button" id="espup">${t('Jetzt aktualisieren','Update now')}</button>`:'')
    +espRow(t('Updates von selbst','Updates by themselves'),t('Holt neue Firmware bei jedem Start.','Fetches new firmware at every start.'),espTgl('espauto',x.auto))
    +espRow(t('Firmware per USB neu schreiben','Rewrite the firmware over USB'),t('Wenn das Board nicht mehr startet. WLAN und Kopplung bleiben.','When the board no longer starts. Wi-Fi and pairing stay.'))
    +`<div class="row esprepair">${espSel('espvar2',espVars(d),x.variant)}<button class="b" type="button" id="esprepair"${d.firmware&&espUsbOk()?'':' disabled'}>${t('Board verbinden und schreiben','Connect board and write')}</button></div>`;
  h+=espGrp(t('Prüfen','Check'))+`<div id="espdiag"></div>
    <div id="espserbox">${espRow(t('Board-Protokoll (USB)','Board log (USB)'),t('Board per USB an diesen PC: Es startet neu, die Seite liest 45 Sekunden mit (WLAN, Adresse, Zertifikat, Abstürze). Der Text bleibt in diesem Browser.','Board to this PC over USB: it restarts and the page reads along for 45 seconds (Wi-Fi, address, certificate, crashes). The text stays in this browser.'),
      `<button class="b" type="button" id="espser"${espUsbOk()?'':' disabled'}>${t('Mitlesen','Read')}</button>`)}
      <div class="row"><button class="b" type="button" id="espserstop" style="display:none">${t('Aufhören','Stop')}</button><button class="b" type="button" id="espsercopy" style="display:none">${t('Kopieren','Copy')}</button></div>
      <ul class="facts small" id="espserres"></ul><pre id="espserlog" style="display:none;max-height:40vh"></pre></div>`;
  return h+`<div class="row espdel"><button class="b bad" type="button" id="espdel">${t('Lautsprecher entfernen','Remove speaker')}</button></div>`+espFoot()}
function espOneBind(d,x){const id=x.id,put=(o,again=true)=>api('/api/profile/esp32/'+id,xjson('PUT',o)).then(()=>again&&showEsp()).catch(e=>espLog(e.message,true));
  $('espren').onclick=()=>{const n=prompt(t('Neuer Name','New name'),x.name);if(n)put({name:n})};
  $('espvol').oninput=()=>{$('espvolv').textContent=$('espvol').value};$('espvol').onchange=()=>put({volume:Number($('espvol').value)},false);
  $('espmic').onchange=()=>put({mic:$('espmic').value},false);
  if($('esproom')){$('esproom').onclick=()=>put({room:$('esproom').dataset.on==='1'});
    $('espmins').onchange=()=>put({room_mins:Number($('espmins').value)},false);$('esplevel').onchange=()=>put({room_level:$('esplevel').value},false);
    $('esparea').onchange=()=>put({room_area:$('esparea').value.trim().slice(0,60)},false);$('espdetect').onchange=()=>put({room_detect:$('espdetect').checked},false);
    $('espping').onchange=()=>put({room_ping:$('espping').checked},false);
    document.querySelectorAll('#espbox [data-ekind]').forEach(b=>b.onchange=()=>put({room_kinds:{[b.dataset.ekind]:b.checked}},false));
    if($('espvoices')){$('espvoices').onchange=()=>put({room_voices:$('espvoices').value},false);$('espprobe').onchange=()=>put({room_probe:$('espprobe').checked},false)}}
  if($('espvoice'))$('espvoice').onclick=async()=>{try{const r=await (await api('/api/profile/esp32/'+id+'/voice',xjson('POST'))).json();
    ESP_MSG=[r.now?t('Der Lautsprecher bittet jetzt um drei Sätze.','The speaker now asks for three sentences.'):t('Vorgemerkt: sag „Jarvis“ oder drück den Knopf, dann sprich drei Sätze.','Queued: say "Jarvis" or press the button, then speak three sentences.'),false];showEsp()}catch(e){espLog(e.message,true)}};
  if($('espup'))$('espup').onclick=async()=>{try{const r=await (await api('/api/profile/esp32/'+id+'/update',xjson('POST'))).json();
    ESP_MSG=[r.restarted?t('Der Lautsprecher startet neu und holt das Update.','The speaker restarts and fetches the update.'):t('Das Update kommt beim nächsten Start (Stecker kurz ziehen genügt).','The update comes at the next start (unplugging briefly is enough).'),false];showEsp()}catch(e){espLog(e.message,true)}};
  $('espauto').onchange=()=>put({auto:$('espauto').checked},false);
  $('esprepair').onclick=()=>espRepair(d.firmware).catch(e=>{espBar(null);espLog(t('Nicht geschrieben: ','Not written: ')+e.message,true)});
  $('espser').onclick=()=>espSerial().catch(e=>espSerShow(null,[[false,e.message]]));
  $('espdel').onclick=async()=>{if(!confirm(t('Lautsprecher entfernen? Sein Schlüssel gilt dann nicht mehr.','Remove the speaker? Its key stops working.')))return;
    await api('/api/profile/esp32/'+id,{method:'DELETE'});espGo(null)};
  espDiag(id)}
async function espSetup(fw){
  const name=$('espname').value.trim(),variant=$('espvar').value,ssid=$('espssid').value,pw=$('esppw').value,base=$('espbase').value.trim().replace(/\/$/,'');
  if(!name)throw new Error(t('Bitte einen Namen eingeben.','Please enter a name.'));
  if(!ssid)throw new Error(t('Bitte den WLAN-Namen eingeben.','Please enter the Wi-Fi name.'));
  const v=fw.variants[variant];
  const c=await espConnect();espChip(c,v.flash);
  espLog(c.chip+(c.mac?' · '+c.mac:'')+(c.flashMB?' · '+c.flashMB+' MB':''));
  const files=await espParts(v.parts.map(p=>Object.assign({},p,{url:`/api/esp32/fw/${fw.version}/${p.file}`})));
  const table=files.find(f=>f.address===0x8000);if(!table)throw new Error(t('Partitionstabelle fehlt.','Partition table missing.'));
  const nvs=nvsPartition(table.u8);
  const r=await (await api('/api/profile/esp32/setup',xjson('POST',{name,variant,base}))).json();
  const img=nvsImage(nvs.size,{wifi:{ssid,password:pw,ota_url:r.ota_url},websocket:{url:r.ws_url,token:r.token,version:1},board:{uuid:r.uuid}});
  try{await espWrite(c,files.concat([{address:nvs.offset,u8:img,file:'nvs'}]))}
  catch(e){await api('/api/profile/esp32/'+r.device,{method:'DELETE'}).catch(()=>{});throw e}
  $('esppw').value='';
  // on to the new speaker's page: its check shows when the board checks in
  ESP_VIEW=r.device;ESP_MSG=[t('Fertig. Das Board startet neu, verbindet sich mit dem WLAN und meldet sich beim Spark. Sag dann „Jarvis“ oder drück den Knopf.','Done. The board restarts, joins the Wi-Fi and checks in with the Spark. Then say "Jarvis" or press the button.'),false];
  await showEsp()}
async function espRepair(fw){const v=fw.variants[$('espvar2').value];
  const c=await espConnect();espChip(c,v.flash);
  const files=await espParts(v.parts.map(p=>Object.assign({},p,{url:`/api/esp32/fw/${fw.version}/${p.file}`})));
  await espWrite(c,files);espLog(t('Firmware geschrieben. Das Board startet neu.','Firmware written. The board restarts.'))}
// ---------------------------------------------------------------- diagnosis ("Prüfen", on the speaker's page)
const espWhen=s=>new Date(s*1000).toLocaleString(L==='en'?'en-GB':'de-DE',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});
const espMark=ok=>ok===true?'<b style="color:var(--ok)">✓</b>':ok===false?'<b style="color:var(--bad)">✗</b>':'<b class="mut">·</b>';
const espEvents=d=>d.events.map(e=>`<li><small class="mut" style="white-space:nowrap">${espWhen(e.t)}</small><span>${esc(e.text)}</span></li>`).join('')||`<li class="mut">${t('Seit dem letzten Neustart des Spark nichts. Das Board hat sich nicht gemeldet.','Nothing since the Spark last restarted. The board has not checked in.')}</li>`;
function espDiagShow(id,d,results){const box=$('espdiag');if(!box)return;
  const li=x=>`<li>${espMark(x.ok)}<span>${esc(x.text)}</span></li>`;
  box.innerHTML=`<ul class="facts small">${d.checks.map(li).join('')}${(results||[]).map(li).join('')}</ul>
    <div class="fh">${t('Adresse im Board','Address in the board')}: <b>${esc(d.base)}</b>${d.base_known?'':' '+t('(nicht gespeichert, eingerichtet vor dieser Version; geprüft wird die Adresse dieser Seite)','(not stored, set up before this version; the address of this page is checked)')}</div>
    <div class="row" style="margin-top:8px"><button class="b" type="button" id="espdnet">${t('Netz prüfen','Check network')}</button><button class="b" type="button" id="espdtest">${t('Ton- und Mikrofontest','Sound and microphone test')}</button></div>
    <div class="fh">${d.test?t('Test ist vorgemerkt: Sag „Jarvis“ oder drück den Knopf. Er spielt einen Ton und einen Satz, dann sagst du etwas und er sagt, was er verstanden hat.','Test is queued: say "Jarvis" or press the button. It plays a tone and a sentence, then you say something and it tells you what it understood.'):t('„Netz prüfen“ fragt die Adresse vom Spark aus ab, wie es das Board tut. Der Test spielt Ton und Satz und prüft danach das Mikrofon.','"Check network" asks the address from the Spark, as the board does. The test plays a tone and a sentence and then checks the microphone.')}</div>
    <div style="margin-top:8px"><b>${t('Zuletzt','Lately')}</b> <small class="mut">(live)</small></div>
    <ul class="facts small" id="espev">${espEvents(d)}</ul>`;
  $('espdnet').onclick=async()=>{$('espdnet').disabled=true;$('espdnet').textContent=t('Prüfe …','Checking …');
    try{const r=await (await api('/api/profile/esp32/'+id+'/check',xjson('POST'))).json();espDiagShow(id,r,r.results)}catch(e){espDiagShow(id,d,[{ok:false,text:e.message}])}};
  $('espdtest').onclick=async()=>{try{const r=await (await api('/api/profile/esp32/'+id+'/test',xjson('POST'))).json();espDiagShow(id,r,[{ok:null,text:r.now?t('Der Lautsprecher spielt jetzt den Test.','The speaker plays the test now.'):t('Vorgemerkt: beim nächsten „Jarvis“ oder Knopfdruck.','Queued: at the next "Jarvis" or button press.')}])}catch(e){espDiagShow(id,d,[{ok:false,text:e.message}])}}}
async function espDiag(id){try{espDiagShow(id,await (await api('/api/profile/esp32/'+id+'/diag')).json());espLive(id)}catch(e){espLog(e.message,true)}}
// "live": while the speaker's page is open and visible, "Zuletzt" follows what it does (every 2 s)
let ESP_LIVE=null;
function espLive(id){clearInterval(ESP_LIVE);ESP_LIVE=setInterval(async()=>{const ul=$('espev');
  if(!ul||ESP_VIEW!==id||!ul.offsetParent){clearInterval(ESP_LIVE);return}
  if(document.hidden)return;
  try{ul.innerHTML=espEvents(await (await api('/api/profile/esp32/'+id+'/diag')).json())}catch{}},2000)}
// ---------------------------------------------------------------- the board's own log over USB
// What XiaoZhi prints at start (see its main/application.cc, ota.cc, esp-wifi-connect), in plain words.
const ESP_SIGNS=[
  [/Brownout detector was triggered/i,false,()=>t('Die Spannung bricht ein. Anderes Netzteil oder kürzeres Kabel nehmen.','The voltage drops. Use another power supply or a shorter cable.')],
  [/Guru Meditation Error|abort\(\) was called|assert failed|Backtrace:/,false,()=>t('Das Board stürzt ab. Meist passt die Board-Variante oder die Pinbelegung nicht. Schick mir den Text.','The board crashes. Usually the board variant or the pins do not match. Send me the text.')],
  [/NVS namespace wifi doesn't exist/,false,()=>t('Auf dem Board stehen keine WLAN-Daten. Per USB neu einrichten.','There is no Wi-Fi data on the board. Set it up again over USB.')],
  [/Connecting to WiFi (\S+)/,null,m=>t('Verbinde mit dem WLAN „','Connecting to the Wi-Fi "')+m[1]+t('“','"')],
  [/Got IP:\s*([\d.]+)/,true,m=>t('Im WLAN, Adresse ','On the Wi-Fi, address ')+m[1]],
  [/WiFi connection timeout|WiFi config mode entered|Access Point started with SSID/,false,()=>t('Das WLAN klappt nicht: Name oder Passwort falsch, oder nur 5 GHz. Das Board macht jetzt ein eigenes WLAN auf. Per USB mit richtigen Daten neu einrichten.','The Wi-Fi does not work: wrong name or password, or 5 GHz only. The board now opens its own Wi-Fi. Set it up again over USB with the right data.')],
  [/Current version: ([\d.]+)/,null,m=>'Firmware '+m[1]],
  [/Check version URL is not properly set/,false,()=>t('Im Board steht keine Spark-Adresse.','There is no Spark address in the board.')],
  [/Failed to open HTTP connection: (.*)/,false,m=>(/cert|x509|ssl|tls/i.test(m[1])?t('Das Board lehnt das Zertifikat des Spark ab. Adresse des Reverse Proxys oder http://<Spark-IP>:31080 nehmen. ','The board refuses the Spark\'s certificate. Use the reverse proxy address or http://<Spark IP>:31080. '):/dns|resolve|host/i.test(m[1])?t('Das Board findet den Namen der Spark-Adresse nicht. ','The board cannot resolve the Spark address. '):t('Das Board erreicht den Spark nicht. ','The board cannot reach the Spark. '))+'('+m[1].slice(0,120)+')'],
  [/Failed to check version, status code: (\d+)/,false,m=>t('Der Spark antwortet mit ','The Spark answers with ')+m[1]+(m[1]==='403'?t(': Lautsprecher sind in Funktionen ausgeschaltet.',': speakers are switched off in Features.'):'')],
  [/Check new version failed/,false,()=>t('Die Start-Prüfung beim Spark ist fehlgeschlagen, das Board versucht es weiter.','The start check at the Spark failed, the board keeps trying.')],
  [/Alert \[link\]/,null,()=>t('Das Board zeigt einen Kopplungscode: Es kennt den Spark noch nicht. Code unter „Lautsprecher mit Code koppeln“ eingeben.','The board shows a pairing code: it does not know the Spark yet. Enter it under "Pair a speaker with a code".')],
  [/No websocket section found/,false,()=>t('Der Spark hat keine Gesprächsadresse geschickt.','The Spark sent no conversation address.')],
  [/Connecting to websocket server: (\S+)/,null,m=>t('Verbinde zum Gespräch: ','Connecting for the conversation: ')+m[1]],
  [/Failed to connect to websocket server/,false,()=>t('Die Gesprächsverbindung klappt nicht: Reverse Proxy ohne WebSockets oder Schlüssel abgelehnt. „Prüfen“ beim Lautsprecher zeigt den Grund.','The conversation connection fails: reverse proxy without WebSockets or key refused. "Check" at the speaker shows why.')],
  [/Session ID:/,true,()=>t('Gespräch mit dem Spark steht.','Conversation with the Spark is up.')],
  [/Wake word detected/,true,()=>t('Weckwort erkannt.','Wake word detected.')],
  [/Failed to create audio (?:de|en)coder|Read Failed!/,false,()=>t('Ton-Fehler auf dem Board (Mikrofon oder Verstärker). Board-Variante und Pins prüfen.','Sound error on the board (microphone or amplifier). Check board variant and pins.')],
  [/rst:0x[0-9a-f]+ \((\w+)\)/i,null,m=>t('Board startet (','Board starts (')+m[1]+')']];
function espAnalyse(text){const out=[],seen=new Set();
  for(const line of text.split('\n'))for(const [re,ok,msg] of ESP_SIGNS){const m=line.match(re);if(!m)continue;const s=msg(m);if(seen.has(s))continue;seen.add(s);out.push([ok,s])}
  if(text.length>200&&!/Current version|Connecting to WiFi|ESP-ROM|rst:0x/i.test(text))out.push([false,t('Das Board schreibt etwas, aber nichts Bekanntes. Schick mir den Text.','The board writes something, but nothing known. Send me the text.')]);
  return out}
// never show what looks like a key or a password, even if a firmware should print one
const espMask=s=>s.replace(/((?:token|password|passwd|authorization|bearer)[^:=\s]*\s*[:=]?\s*)\S+/gi,'$1•••');
function espSerShow(text,res){const r=$('espserres'),l=$('espserlog');if(!r)return;
  r.innerHTML=(res||[]).map(([ok,s])=>`<li>${espMark(ok)}<span>${esc(s)}</span></li>`).join('');
  if(text!=null){l.style.display='block';l.textContent=text.split('\n').slice(-300).join('\n');l.scrollTop=l.scrollHeight;$('espsercopy').style.display=''}}
let ESP_SER=null;
async function espSerial(){
  if(!('serial' in navigator))throw new Error(t('Dieser Browser kann nicht per USB lesen. Bitte Chrome oder Edge am PC oder Mac nehmen.','This browser cannot read over USB. Please use Chrome or Edge on a PC or Mac.'));
  if(!window.isSecureContext)throw new Error(t('Nur über https (oder localhost) erlaubt der Browser USB.','The browser only allows USB over https (or localhost).'));
  if(ESP_SER)return;
  let port=await navigator.serial.requestPort({});const info=port.getInfo();
  const st=ESP_SER={stop:false,text:''};const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  $('espser').disabled=true;$('espserstop').style.display='';$('espserstop').onclick=()=>{st.stop=true;st.reader&&st.reader.cancel().catch(()=>{})};
  $('espsercopy').onclick=()=>navigator.clipboard.writeText(espMask(st.text)).catch(()=>{});
  espSerShow('',[[null,t('Verbunden, starte das Board neu …','Connected, restarting the board …')]]);
  const end=Date.now()+45000,dec=new TextDecoder();let reset=false;
  try{while(!st.stop&&Date.now()<end){
      try{await port.open({baudRate:115200})}catch(e){if(!/already open/i.test(e.message))throw e}
      if(!reset){reset=true;   // restart into the firmware: boot pin high (DTR off), reset pulse on RTS
        await port.setSignals({dataTerminalReady:false,requestToSend:true}).catch(()=>{});await sleep(150);await port.setSignals({requestToSend:false}).catch(()=>{})}
      st.reader=port.readable.getReader();
      const timer=setInterval(()=>{if(Date.now()>end)st.reader.cancel().catch(()=>{})},500);
      try{while(true){const {value,done}=await st.reader.read();if(done)break;
          st.text=(st.text+dec.decode(value,{stream:true})).slice(-200000);espSerShow(espMask(st.text),espAnalyse(st.text))}}
      catch(e){}   // a board with its own USB vanishes for a moment when it restarts
      finally{clearInterval(timer);try{st.reader.releaseLock()}catch{}await port.close().catch(()=>{})}
      if(st.stop||Date.now()>end)break;
      await sleep(1200);   // find the same board again after it came back
      const again=(await navigator.serial.getPorts()).find(p=>{const i=p.getInfo();return i.usbVendorId===info.usbVendorId&&i.usbProductId===info.usbProductId});
      if(again)port=again}}
  finally{ESP_SER=null;if($('espser'))$('espser').disabled=false;if($('espserstop'))$('espserstop').style.display='none'}
  const res=espAnalyse(st.text);
  if(!st.text.trim())res.push([false,t('Vom Board kam nichts. Anderes Kabel (Datenkabel) oder die andere USB-Buchse des Boards versuchen.','Nothing came from the board. Try another (data) cable or the board\'s other USB socket.')]);
  espSerShow(espMask(st.text),res)}
// ---------------------------------------------------------------- admin (Funktionen)
async function espAdmin(){if(!$('espadmin'))return;let d={};try{d=await (await api('/api/admin/esp32')).json()}catch{return}
  const fw=d.firmware;
  $('espstate').dataset.need=fw?'':'1';setTimeout(()=>typeof guidesCount==='function'&&guidesCount());$('espstate').textContent=(fw?t('Firmware ','Firmware ')+fw.version+' ('+Object.keys(fw.variants).length+t(' Boards)',' boards)'):t('Noch keine Firmware auf dem Spark.','No firmware on the Spark yet.'))
    +' · '+d.speakers+t(' Lautsprecher, ',' speakers, ')+d.online+t(' verbunden',' connected')+(d.checked?' · '+t('zuletzt geprüft ','last checked ')+espDate(d.checked):'')+(d.error?' · ⚠ '+d.error:'');
  $('espfetch').onclick=async()=>{$('espstate').textContent=t('Hole die Firmware von GitHub …','Fetching the firmware from GitHub …');
    try{await api('/api/admin/esp32/fetch',xjson('POST'));espAdmin()}catch(e){$('espstate').textContent=e.message}};
  // "Adresse prüfen": the address in the field (saved or not) tried from the Spark, like the board would
  $('espcheck').onclick=async()=>{const b=$('espcheck'),ul=$('espcheckres');b.disabled=true;ul.innerHTML=`<li class="mut">${t('Prüfe …','Checking …')}</li>`;
    try{const r=await (await api('/api/admin/esp32/check',xjson('POST',{base:$('chat.esp32_url').value.trim()}))).json();
      ul.innerHTML=r.results.map(x=>`<li>${espMark(x.ok)}<span>${esc(x.text)}</span></li>`).join('')}
    catch(e){ul.innerHTML=`<li>${espMark(false)}<span>${esc(e.message)}</span></li>`}finally{b.disabled=false}}}
