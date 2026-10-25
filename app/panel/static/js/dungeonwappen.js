// KI-Dungeon-Master: Wappen für Gruppe und Fraktionen (D&D-Idee 10 of 2026-10-25, Dominik „1-12 reihenfolge bestimmst du
// wie du alles umsetzten kannst.“). The panel builds every coat of arms as a checked SVG of its own parts
// (dungeon_wappen.py); the view carries v.wappen {gruppe: code, fr: {faction in small letters: code}, svg: {code: svg},
// wahl (host only)}. This file only shows them as pictures (an img or an SVG image never runs anything inside) and sends
// the host's choice of colour and charge. No v.wappen: the switch is off, nothing to show.
// For the other parts of the game: dmWappen(v,code,cls,label), dmWappenFr(v,name,cls), dmWappenGruppe(v,cls),
// dmWappenHref(v,code) (an SVG map's image href), dmWappenCode(v,name), dmWappenKopf(v) (the group's arms with the choice).
const DMWAPPEN={auf:false};
const dmWappenHref=(v,code)=>{const s=v&&v.wappen&&code&&v.wappen.svg[code];return s?'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(s):''};
const dmWappenCode=(v,name)=>(v&&v.wappen&&v.wappen.fr[String(name||'').toLowerCase()])||'';
function dmWappen(v,code,cls,label){const u=dmWappenHref(v,code);
  return u?`<img class="dm-wappen${cls?' '+cls:''}" src="${u}" ${label?`alt="${esc(label)}" title="${esc(label)}"`:'alt="" aria-hidden="true"'}>`:''}
const dmWappenFr=(v,name,cls)=>dmWappen(v,dmWappenCode(v,name),cls,t('Wappen von ','Arms of ')+name);
const dmWappenGruppe=(v,cls)=>dmWappen(v,v&&v.wappen&&v.wappen.gruppe,cls,t('Wappen eurer Gruppe','Your group’s arms'));
function dmWappenKopf(v){if(!v||!v.wappen)return '';const W=v.wappen.wahl;
  return `<div class="dm-wappenkopf">${dmWappenGruppe(v,'gross')}<div><b>${esc(t('Euer Wappen','Your arms'))}</b><small class="mut">${esc(t('Es steht auf den Heldenkarten, in den Spiel-Mails und auf dem Kapiteldeckel. Jede Gruppe der Geschichte trägt ihr eigenes.','It is on the hero cards, in the game mails and on the chapter cover. Every group of the story carries its own.'))}</small>${W?`<div class="dm-hostb"><button type="button" class="b" data-dmwappen="auf" aria-expanded="${DMWAPPEN.auf}">${esc(DMWAPPEN.auf?t('Fertig','Done'):t('Farbe und Zeichen wählen','Choose colour and charge'))}</button></div>`:''}</div></div>${W&&DMWAPPEN.auf?dmWappenWahl(W):''}`}
function dmWappenWahl(W){const knopf=(k,cur,inner,label,attr)=>`<button type="button" class="dm-wappenk${k===cur?' on':''}" ${attr}="${esc(k)}" aria-pressed="${k===cur}" title="${esc(label)}" aria-label="${esc(label)}">${inner}</button>`;
  return `<div class="dm-wappenwahl"><h5>${esc(t('Farbe','Colour'))}</h5><div class="dm-wappenreihe">${knopf('',W.farbe,'?',t('vom Zufall','by chance'),'data-dmwappenf')}${W.farben.map(f=>knopf(f[0],W.farbe,`<i style="background:${f[2]}"></i>`,f[1],'data-dmwappenf')).join('')}</div>
    <h5>${esc(t('Zeichen','Charge'))}</h5><div class="dm-wappenreihe">${knopf('',W.zeichen,'?',t('vom Zufall','by chance'),'data-dmwappenz')}${W.zeichen_alle.map(z=>knopf(z[0],W.zeichen,`<img src="data:image/svg+xml;charset=utf-8,${encodeURIComponent(z[2])}" alt="">`,z[1],'data-dmwappenz')).join('')}</div></div>`}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmwappen],#dmview [data-dmwappenf],#dmview [data-dmwappenz]');if(!b||!DM.rid)return;
  if(b.dataset.dmwappen){DMWAPPEN.auf=!DMWAPPEN.auf;dmDraw();return}
  const W=(DM.v&&DM.v.wappen&&DM.v.wappen.wahl)||{farbe:'',zeichen:''};
  const body={farbe:b.dataset.dmwappenf!==undefined?b.dataset.dmwappenf:W.farbe,zeichen:b.dataset.dmwappenz!==undefined?b.dataset.dmwappenz:W.zeichen};
  const d=await dmSend(`/api/profile/dungeon/${DM.rid}/wappen`,body,DM);if(d){DM.v=d;DM.at=Date.now()}dmDraw()});
