// Ich → Gedächtnis → Zuordnungen (klaeren.py, plan „Rückfrage, Korrektur und Merken“): the profile's own words for
// its devices (and later contacts, calendars …). One row per mapping with the words, the target and how often it
// was used; "Anderes Ziel", "Wörter ändern" and "Löschen". "Eigene Namen vergeben" lists every target of an area
// and asks "Wie sagst du dazu?". Shown only while "Rückfrage statt Raten" is on for the profile.
let MAPS=null,MAPAREA='all',MAPEDIT=null,MAPNEW=null;
window.meMaps=async function(){const box=$('mapbox');if(!box)return;
  let d=null;try{const r=await fetch('/api/profile/zuordnungen');if(r.ok)d=await r.json()}catch{}
  box.hidden=!d;if(!d)return;MAPS=d;mapDraw()};
function mapDraw(){const E=icEl,box=$('maplist'),tools=$('maptools');if(!box||!MAPS)return;tools.textContent='';box.textContent='';
  const areas=MAPS.areas||{},items=MAPS.items||[],an=k=>(areas[k]||[k,k])[L==='en'?1:0];
  tools.append(icChip(t(`Alle ${items.length}`,`All ${items.length}`),MAPAREA==='all',()=>{MAPAREA='all';mapDraw()}),
    ...Object.keys(areas).filter(k=>(MAPS.pick||[]).includes(k)||items.some(x=>x.area===k)).map(k=>icChip(`${an(k)} ${items.filter(x=>x.area===k).length}`,MAPAREA===k,()=>{MAPAREA=k;mapDraw()})));
  const add=E('button','b p',t('＋ Eigene Namen vergeben','＋ Give own names'));add.type='button';add.id='mapadd';
  const pick=MAPS.pick||[];add.hidden=!pick.length;   // only areas whose targets can be listed
  add.onclick=()=>mapNew(pick.includes(MAPAREA)?MAPAREA:pick[0]);tools.appendChild(add);
  const rows=items.filter(x=>MAPAREA==='all'||x.area===MAPAREA).map(x=>{
    if(MAPEDIT===x.mid){const r=E('div','ic-row');const m=E('div','ic-rmid');const i=document.createElement('input');i.value=x.words;i.maxLength=120;
      i.setAttribute('aria-label',t('Wörter','Words'));const ok=E('button','b p',t('Speichern','Save')),no=E('button','b',t('Abbrechen','Cancel'));ok.type=no.type='button';
      ok.onclick=async()=>{ok.disabled=true;try{await api('/api/profile/zuordnungen/'+encodeURIComponent(x.mid),xjson('PUT',{words:i.value}));MAPEDIT=null;meMaps()}catch(e){ok.disabled=false;$('mapmsg').textContent=e.message}};
      no.onclick=()=>{MAPEDIT=null;mapDraw()};const a=E('div','row');a.append(ok,no);m.append(i,a);r.appendChild(m);return r}
    const meta=`→ ${x.name}${x.room?' · '+x.room:''} · ${an(x.area)} · `+t(`${x.used||0}× genutzt`,`used ${x.used||0}×`)+(x.how==='hand'?t(' · von dir',' · by you'):'');
    return icRow('„'+x.words+'“',meta,[icBtn('pen',t('Wörter ändern','Change words'),()=>{MAPEDIT=x.mid;mapDraw()}),
      ...((MAPS.pick||[]).includes(x.area)?[icBtn('sync',t('Anderes Ziel','Other target'),()=>mapNew(x.area,x))]:[]),
      icBtn('trash',t('Löschen','Delete'),async()=>{if(!confirm(t('Zuordnung löschen?','Delete mapping?')))return;await api('/api/profile/zuordnungen/'+encodeURIComponent(x.mid),{method:'DELETE'});meMaps()})])});
  box.appendChild(icList(rows.length?rows:[icEmpty(t('Noch keine Zuordnungen. Wählt der Assistent nach einer Rückfrage ein Gerät, fragt er, ob er es sich merken soll.','No mappings yet. When the assistant asks back and you pick a device, it asks whether to remember it.'))]));
  if(MAPNEW)box.appendChild(MAPNEW)}
// every target of one area to pick from; for a new mapping first "Wie sagst du dazu?"
async function mapNew(area,row){const E=icEl;if(!area)return;$('mapmsg').textContent=t('Lade …','Loading …');
  let d=null;try{d=await (await api('/api/profile/zuordnungen/ziele?area='+encodeURIComponent(area))).json()}catch(e){$('mapmsg').textContent=e.message;return}
  $('mapmsg').textContent='';const w=E('div','mapnew');const h=E('b','',row?t(`Neues Ziel für „${row.words}“`,`New target for "${row.words}"`):t('Wie sagst du dazu?','What do you call it?'));w.appendChild(h);
  let words=null;if(!row){words=document.createElement('input');words.maxLength=120;words.placeholder=t('z. B. Fernseher im Wohnzimmer','e.g. TV in the living room');words.setAttribute('aria-label',t('Deine Wörter','Your words'));w.appendChild(words)}
  const f=document.createElement('input');f.type='search';f.maxLength=60;f.placeholder=t('Gerät suchen …','Search device …');f.setAttribute('aria-label',t('In der Liste suchen','Search the list'));
  const list=E('div','choice chlist');const rows=E('div','chrows');list.append(f,rows);w.appendChild(list);
  const draw=()=>{rows.textContent='';const q=f.value.trim().toLowerCase();let room=null;
    for(const o of d.items||[]){if(q&&!(o.name+' '+(o.room||'')).toLowerCase().includes(q))continue;
      if(o.room!==room){room=o.room;rows.appendChild(E('div','chgrp',room||t('Ohne Raum','No room')))}
      const b=E('button','chrow');b.type='button';b.appendChild(E('b','',o.name));if(o.info)b.appendChild(E('span','mut',' '+o.info));
      b.onclick=async()=>{try{if(row)await api('/api/profile/zuordnungen/'+encodeURIComponent(row.mid),xjson('PUT',{id:o.id}));
          else await api('/api/profile/zuordnungen',xjson('POST',{area,words:words.value,id:o.id}));MAPNEW=null;meMaps()}catch(e){$('mapmsg').textContent=e.message}};
      rows.appendChild(b)}};
  f.oninput=draw;draw();const no=E('button','b',t('Abbrechen','Cancel'));no.type='button';no.onclick=()=>{MAPNEW=null;mapDraw()};w.appendChild(no);
  MAPNEW=w;mapDraw();(words||f).focus()}
