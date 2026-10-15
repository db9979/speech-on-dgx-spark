// Gehäuse (gehaeuse.py, plan Raspberry-Pi split B7): Funktionen → Gehäuse, the case of the panel computer. The settings
// are saved like every switch; "Einrichten", "Entfernen" and "Neu starten" leave a wish for the fixed root unit and ask
// for the code. The line below shows what the Pi reports: set up, restart needed, display and LEDs (words only).
function gehShow(d){const m=$('gehmsg');if(!m)return;
  const w={an:t('an','on'),aus:t('aus','off'),fehlt:t('nicht gefunden','not found'),fehler:t('Fehler','error')};
  m.textContent=!d.pi?t('Kein Raspberry Pi: hier gibt es nichts einzurichten.','Not a Raspberry Pi: nothing to set up here.')
    :[d.eingerichtet?t('Eingerichtet','Set up'):t('Nicht eingerichtet','Not set up'),
      d.neustart?t('Neustart nötig','Restart needed'):'',
      t('Display ','Display ')+(w[d.oled]||d.oled)+(d.addr?' ('+d.addr+')':''),t('LEDs ','LEDs ')+(w[d.led]||d.led)].filter(Boolean).join(' · ');
  $('gehein').disabled=!d.pi;$('gehaus').disabled=!d.pi||!d.eingerichtet;$('gehneu').hidden=!d.neustart}
async function gehLoad(){if(!$('gehbox')||document.body.classList.contains('mgr'))return;
  try{gehShow(await (await api('/api/admin/gehaeuse')).json())}catch{}}
const gehDo=(path,ask)=>async()=>{if(ask&&!confirm(ask))return;$('gehmsg').textContent=t('Einen Moment …','One moment …');
  try{gehShow(await (await api('/api/admin/gehaeuse/'+path,{method:'POST'})).json());setTimeout(gehLoad,4000)}catch(e){$('gehmsg').textContent=e.message}};
if($('gehein'))$('gehein').onclick=gehDo('einrichten');
if($('gehaus'))$('gehaus').onclick=gehDo('entfernen',t('Die Einträge des Gehäuses aus config.txt nehmen? Danach ist ein Neustart nötig.','Take the case entries out of config.txt? A restart is needed then.'));
if($('gehneu'))$('gehneu').onclick=gehDo('neustart',t('Den Panel-Rechner jetzt neu starten? Das Panel ist etwa eine Minute weg.','Restart the panel computer now? The panel is gone for about a minute.'));
window.gehLoad=gehLoad;
