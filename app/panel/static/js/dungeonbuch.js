// KI-Dungeon-Master: Heldenbuch aufs reMarkable (dungeon_buch.py, Dominik 2026-10-27). Below the own heroes (tab
// „Helden“) a part per hero: its last edition, whether it waits for the evening's end, „Jetzt schicken“ and the preview
// as a PDF made on the Spark. The panel decides everything; this file only shows the state and sends the button.
// It joins the heroes' page without touching dungeon.js: dmHeroes(D) gets this part appended.
const DMBUCH={d:null,geladen:false,busy:false,msg:'',err:false};
async function dmBuchLaden(){if(DMBUCH.busy)return;DMBUCH.busy=true;const {r,d}=await apiTry('/api/profile/dungeon/buch');DMBUCH.busy=false;
  DMBUCH.geladen=true;DMBUCH.d=r.ok?d:null;dmDraw()}
const dmBuchZeit=x=>x?new Date(x*1000).toLocaleString([],{dateStyle:'short',timeStyle:'short'}):'';
const DMBUCH_MODELL={rm2:'reMarkable 2',pro:'Paper Pro',move:'Paper Pro Move'};
function dmBuchTeil(){if(!DMBUCH.geladen){dmBuchLaden();return ''}const B=DMBUCH.d;if(!B||!B.admin)return '';
  const head=`<h3 class="sec">📖 ${esc(t('Heldenbuch aufs reMarkable','Hero book to the reMarkable'))}</h3>`;
  if(!B.on)return head+`<div class="ic-empty">${esc(B.fehlt)}</div>`;
  if(!B.verbunden)return head+`<div class="ic-empty">${esc(t('Verbinde zuerst dein reMarkable unter Ich → reMarkable.','Connect your reMarkable first under Me → reMarkable.'))}</div>`;
  const fmt=`<small class="mut">${esc(t('Format: ','Format: ')+(DMBUCH_MODELL[B.modell]||B.modell)+' · '+(B.farbe?t('Farbe','colour'):t('Graustufen','grey'))+t(' (ändern unter Ich → reMarkable)',' (change under Me → reMarkable)'))}</small>`;
  const rows=B.helden.map(h=>`<div class="ic-row"><div class="ic-rmid"><span class="ic-t">${esc(h.name)}</span><small class="ic-meta">${esc(h.ausgabe?t(`Ausgabe ${h.ausgabe} vom ${dmBuchZeit(h.t)}, ${h.seiten} Seiten`,`Edition ${h.ausgabe} of ${dmBuchZeit(h.t)}, ${h.seiten} pages`):t('Noch keine Ausgabe','No edition yet'))}${h.wartet?esc(t(' · kommt nach dem Abend von selbst',' · comes by itself after the evening')):''}${h.notizen?esc(t(' · Notizen liegen dort',' · notes are there')):''}</small></div>
    <a class="b" href="/api/profile/dungeon/buch/${esc(h.hid)}.pdf?lang=${dmLang()}" download>${esc(t('Vorschau (PDF)','Preview (PDF)'))}</a><button type="button" class="b p" data-dmbuch="${esc(h.hid)}"${DMBUCH.busy?' disabled':''}>${esc(t('Jetzt schicken','Send now'))}</button></div>`).join('');
  return head+fmt+(rows?`<div class="ic-list">${rows}</div>`:`<div class="ic-empty">${esc(t('Noch keine Helden.','No heroes yet.'))}</div>`)+`<div class="dmmsg ${DMBUCH.err?'err':'mut'}" role="status">${esc(DMBUCH.msg)}</div>`}
{const kern=dmHeroes;dmHeroes=D=>kern(D)+dmBuchTeil()}
document.body.addEventListener('click',async e=>{const b=e.target.closest('#dmview [data-dmbuch]');if(!b||DMBUCH.busy)return;
  DMBUCH.busy=true;b.disabled=true;DMBUCH.msg=t('Wird geschickt …','Sending …');DMBUCH.err=false;dmDraw();
  const {r,d}=await apiTry(`/api/profile/dungeon/buch/${b.dataset.dmbuch}/senden`,xjson('POST',{}));DMBUCH.busy=false;
  const why={kein_geraet:t('Kein reMarkable verbunden.','No reMarkable connected.'),limit:t('Heute schon zu oft aufs reMarkable geschickt.','Sent to the reMarkable too often today.')};
  if(r.ok){DMBUCH.d=d;DMBUCH.msg=t('Liegt jetzt auf deinem reMarkable.','It is on your reMarkable now.')}else{DMBUCH.msg=why[d.detail]||t('Nicht geschickt.','Not sent.');DMBUCH.err=true}dmDraw()});
