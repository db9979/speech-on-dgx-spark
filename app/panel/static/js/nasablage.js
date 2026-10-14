// "Ich → Speicher → Wofür → Ablage-Ordner" (nasablage.py, plan synology-bauplan.md S4): the folder spark_ablage at one
// place in the home network, the only folder the Spark writes to. Erstellt/ gets made documents (unless unticked) and
// own things after a "Ja"; files in Eingang/ come into Dokumente and move to Eingang/erledigt. One per profile.
// When the admin blocks the profile the setting stays visible and can be removed (own data). Server text is text (esc).
let NAB=null;
const naWhy=k=>t(...((NAB&&NAB.why_words||{})[k]||NAS_WHY[k]||NAS_WHY.other));
async function naLoad(){NAB=null;try{const d=await (await api('/api/profile/nasablage')).json();if(d.on||d.drop)NAB=d}catch{NAB=null}return NAB}
function naState(x){if(x.running)return ['warn',t('holt gerade','taking in now')];if(x.fail)return [x.fail.kind==='offline'?'warn':'bad',naWhy(x.fail.kind)];
  return x.last?['ok',t('bereit','ready')]:['ok',t('eingerichtet','set up')]}
function naOne(x){const [cls,word]=naState(x),on=NAB.on;
  return `<div class="use"><div class="use-h"><span><b>${esc(t('Ablage-Ordner','Filing folder'))}</b> <em class="pill ${cls}">${esc(word)}</em>
      <small>${esc(NAB.folder)} · ${esc(t(`${x.made+x.dropped} abgelegt`,`${x.made+x.dropped} filed`))} · ${esc(t(`${x.fetched} aus dem Eingang`,`${x.fetched} from the inbox`))}${x.refused?' · '+esc(t(`${x.refused} abgelehnt`,`${x.refused} refused`)):''}${x.last?' · '+esc(t('zuletzt','last'))+' '+esc(spWhen(x.last.t)):''}</small></span></div>
    ${on?'':`<div class="fh">${esc(t('Vom Admin ausgeschaltet oder für dich gesperrt: der Spark schreibt dort nichts mehr. „Nicht mehr nutzen“ geht weiter.','Switched off or blocked for you by the admin: the Spark writes nothing there any more. "Stop using" still works.'))}</div>`}
    ${on?`<label class="chk"><input type="checkbox" data-naauto${x.auto?' checked':''}${NAB.made_ok?'':' disabled'}> ${esc(t('Erstellte Dokumente automatisch ablegen (in Erstellt)','File made documents automatically (in Erstellt)'))}</label>
    <label class="chk"><input type="checkbox" data-nainbox${x.inbox?' checked':''}${NAB.docs?'':' disabled'}> ${esc(t(`Eingang abholen (alle ${NAB.every} Minuten, dann nach Eingang/erledigt)`,`Take in the inbox (every ${NAB.every} minutes, then to Eingang/erledigt)`))}</label>
    ${NAB.docs?'':`<div class="fh">${esc(t('Den Eingang abholen braucht „Eigene Dokumente“.','Taking in the inbox needs "Own documents".'))}</div>`}
    <div class="row" style="margin-top:6px"><button class="b" type="button" data-nanow${NAB.docs&&x.inbox?'':' disabled'}>${esc(t('Eingang jetzt abholen','Take in the inbox now'))}</button></div>`:''}
    <div class="row"><button class="b" type="button" data-nadel>${esc(t('Nicht mehr nutzen','Stop using'))}</button></div></div>`}
// the Ablage-Ordner part of one place under "Wofür" (nas.js)
function naUse(place){if(!NAB)return '';const d=NAB.drop;
  if(d)return d.nas===place.id?naOne(d):'';
  if(!NAB.on)return '';
  if(place.zone!=='lan')return `<div class="use"><small class="mut">${esc(t('Ablage-Ordner: nur an einem Ort im Heimnetz.','Filing folder: only at a place in the home network.'))}</small></div>`;
  return `<div class="use"><div class="use-h"><span><b>${esc(t('Ablage-Ordner','Filing folder'))}</b><small>${esc(t('Der Spark legt Erstelltes in „spark_ablage/Erstellt“ und holt, was du in „Eingang“ legst. Nur dort schreibt er, nie über eine Datei, er löscht nie.','The Spark puts what it made into "spark_ablage/Erstellt" and takes in what you put into "Eingang". It writes only there, never over a file, and never deletes.'))}</small></span></div>
    <div class="row"><button class="b" type="button" data-naset="${esc(place.id)}">${esc(t('Hier ablegen','File here'))}</button></div></div>`}
function naBind(box,after,say){if(!NAB)return;
  const go=async(url,opts,ok)=>{try{const r=await (await api(url,opts)).json();await after();if(ok)say(ok(r))}catch(e){await after();say(e.message,true)}};
  box.querySelectorAll('[data-naset]').forEach(b=>b.onclick=async()=>{b.disabled=true;say(t('Prüfe „spark_ablage“ und lege die Ordner an …','Checking "spark_ablage" and making the folders …'));
    try{await api('/api/profile/nasablage',xjson('POST',{nas:b.dataset.naset}));await after();say(t('Eingerichtet: Erstelltes landet in „spark_ablage/Erstellt“, der Eingang wird abgeholt.','Set up: what the Spark makes lands in "spark_ablage/Erstellt", the inbox is taken in.'))}
    catch(e){b.disabled=false;say(e.message,true)}});
  const put=body=>go('/api/profile/nasablage',xjson('PUT',body),()=>t('Gespeichert.','Saved.'));
  box.querySelectorAll('[data-naauto]').forEach(c=>c.onchange=()=>put({auto:c.checked}));
  box.querySelectorAll('[data-nainbox]').forEach(c=>c.onchange=()=>put({inbox:c.checked}));
  box.querySelectorAll('[data-nanow]').forEach(b=>b.onclick=()=>{b.disabled=true;say(t('Hole den Eingang …','Taking in the inbox …'));
    go('/api/profile/nasablage/now',{method:'POST'},r=>t(`${r.fetched} geholt, ${r.refused} abgelehnt, ${r.left} warten.`,`${r.fetched} taken in, ${r.refused} refused, ${r.left} waiting.`))});
  box.querySelectorAll('[data-nadel]').forEach(b=>b.onclick=()=>{if(!confirm(t('Den Ablage-Ordner nicht mehr nutzen? Der Spark schreibt dort nichts mehr; was dort liegt, bleibt.','Stop using the filing folder? The Spark writes nothing there any more; what lies there stays.')))return;
    go('/api/profile/nasablage',{method:'DELETE'},()=>t('Der Spark nutzt den Ablage-Ordner nicht mehr.','The Spark no longer uses the filing folder.'))})}
