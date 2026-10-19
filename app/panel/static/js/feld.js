// Eingabefelder wachsen mit dem Text (Dominik 2026-10-19: „die ganzen Eingabefenster sind starr“, Plan eingabefelder/plan.md).
// Eine Stelle für jedes <textarea>, auch für künftige: das Feld ist so hoch wie sein Text, mindestens so hoch wie seine
// rows, höchstens data-zeilen Zeilen (Eingaben zum Abschicken) oder eine halbe Fensterhöhe; darüber scrollt es innen.
// Ab 4 Zeilen öffnet ⤢ die Großansicht (Fertig übernimmt, Senden schickt ab), ab 80 % von maxlength steht der Zähler
// am Feld. data-senden="<Knopf-id>" oder "form": Enter schickt ab, Umschalt+Enter macht eine neue Zeile (am Handy macht
// die Taste immer eine neue Zeile, der Pfeil sendet). data-fest: das Feld behält seine Höhe. Kein Feld rechnet seine Höhe
// selbst; ein Wert aus dem Code (ta.value = …) wächst über den Setter unten mit, ein verstecktes Feld beim Sichtbarwerden.
const FELD={big:4,warn:.8,cur:null,raf:0,box:null};
const feldTouch=()=>matchMedia('(pointer:coarse)').matches;
// Enter schickt ab (nicht am Handy, nicht mitten in einer Eingabe mit Vorschlägen, nie mit Umschalt)
function feldEnterSendet(e){return e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&!feldTouch()}
function feldSend(ta){const s=ta.dataset.senden;if(s==='form'){if(ta.form)ta.form.requestSubmit()}else if(s&&$(s))$(s).click()}
const feldSichtbar=ta=>ta.getClientRects().length>0;   // auch in festen Kästen (offsetParent wäre dort null)
const feldOn=ta=>ta&&ta.tagName==='TEXTAREA'&&!('fest' in ta.dataset)&&ta.id!=='feldtext';
// Maße einmal je Feld (keine Stil-Abfrage je Tastendruck)
function feldMass(ta){if(ta._fm)return ta._fm;const cs=getComputedStyle(ta),fs=parseFloat(cs.fontSize)||14;
  const lh=parseFloat(cs.lineHeight)||fs*1.5,rand=ta.offsetHeight-ta.clientHeight,pad=parseFloat(cs.paddingTop)+parseFloat(cs.paddingBottom);
  return ta._fm={lh,rand,pad,min:ta.offsetHeight}}
function feldMax(ta,m){const z=+ta.dataset.zeilen;return z?Math.ceil(z*m.lh+m.pad+m.rand):Math.max(m.min,Math.round(innerHeight*.5))}
// Höhe nachziehen; schreibt nur, wenn sich etwas ändert (Tippen geht vor, Richtlinie Teil 6)
function feldGrow(ta){if(!feldOn(ta)||!ta.isConnected)return;
  if(!feldSichtbar(ta)){ta._fdirty=true;return}ta._fdirty=false;
  if(!ta._fm&&ta.style.height)ta.style.height='';const m=feldMass(ta),max=feldMax(ta,m),len=ta.value.length;
  const shrink=len<(ta._flen||0);ta._flen=len;
  if(!shrink&&ta.scrollHeight<=ta.clientHeight+1&&ta.style.height)return feldUi();
  const sc=document.scrollingElement,y=sc?sc.scrollTop:0;
  ta.style.height=m.min+'px';const h=ta.scrollHeight+m.rand;
  ta.style.height=Math.min(Math.max(h,m.min),max)+'px';ta.style.overflowY=h>max?'auto':'hidden';
  if(sc&&sc.scrollTop!==y)sc.scrollTop=y;feldUi()}
// ta.value = … aus dem Code (Antwort einsetzen, Feld leeren) wächst mit, ohne dass jede Stelle daran denken muss
{const d=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value');
 Object.defineProperty(HTMLTextAreaElement.prototype,'value',{configurable:true,enumerable:d.enumerable,get(){return d.get.call(this)},
   set(v){d.set.call(this,v);if(feldOn(this)){this._flen=1e9;requestAnimationFrame(()=>feldGrow(this))}}})}
// versteckt gefüllt (Einstellungen, Unterseiten): wachsen, sobald es zu sehen ist
const feldSicht='IntersectionObserver' in window?new IntersectionObserver(es=>es.forEach(x=>{if(x.isIntersecting&&x.target._fdirty)feldGrow(x.target)})):null;
function feldNeu(ta){if(ta._fneu||!feldOn(ta))return;ta._fneu=true;if(feldSicht)feldSicht.observe(ta);if(ta.value)feldGrow(ta)}
function feldSuch(n){if(n.nodeType!==1)return;if(n.tagName==='TEXTAREA')feldNeu(n);else if(n.firstElementChild)n.querySelectorAll('textarea').forEach(feldNeu)}
new MutationObserver(ms=>ms.forEach(m=>m.addedNodes.forEach(feldSuch))).observe(document.documentElement,{childList:true,subtree:true});
document.querySelectorAll('textarea').forEach(feldNeu);
document.addEventListener('input',e=>{if(feldOn(e.target))feldGrow(e.target)},true);
document.addEventListener('keydown',e=>{const ta=e.target;if(feldOn(ta)&&ta.dataset.senden&&feldEnterSendet(e)){e.preventDefault();feldSend(ta)}});
// ⤢ und Zähler: je ein Element für die ganze Seite, am Feld mit dem Cursor
function feldEl(){if($('feldgross'))return;const b=document.createElement('button');b.type='button';b.id='feldgross';b.className='ib';b.hidden=true;
  b.title=t('Groß bearbeiten','Edit in a large view');b.setAttribute('aria-label',b.title);
  b.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>';
  b.addEventListener('pointerdown',e=>e.preventDefault());b.addEventListener('click',()=>{if(FELD.cur)feldGross(FELD.cur)});
  const z=document.createElement('span');z.id='feldzahl';z.hidden=true;z.setAttribute('aria-live','polite');document.body.append(b,z)}
function feldZahl(ta){const max=ta.maxLength,n=ta.value.length;return max>0&&n>=max*FELD.warn?n.toLocaleString()+' / '+max.toLocaleString():''}
function feldUi(){if(FELD.raf)return;FELD.raf=requestAnimationFrame(()=>{FELD.raf=0;feldEl();const ta=FELD.cur,b=$('feldgross'),z=$('feldzahl');
  if(!ta||!ta.isConnected||!feldSichtbar(ta)||FELD.box){b.hidden=z.hidden=true;return}
  const r=ta.getBoundingClientRect(),m=feldMass(ta),gross=!ta.readOnly&&!ta.disabled&&ta.scrollHeight>=FELD.big*m.lh+m.pad,zahl=feldZahl(ta);
  if(gross!==ta.classList.contains('feldplatz')){ta.classList.toggle('feldplatz',gross);ta._flen=1e9;FELD.raf=0;return feldGrow(ta)}   // Platz für ⤢, damit es keinen Text verdeckt
  b.hidden=!gross;if(gross){b.style.top=(r.top+5)+'px';b.style.left=(r.right-35-(ta.offsetWidth-ta.clientWidth-m.rand>0?ta.offsetWidth-ta.clientWidth-m.rand:0))+'px'}
  z.hidden=!zahl;if(zahl){z.textContent=zahl;z.classList.toggle('voll',ta.value.length>=ta.maxLength);z.style.top=(r.bottom+2)+'px';z.style.left='';z.style.right=Math.max(0,innerWidth-r.right)+'px'}})}
document.addEventListener('focusin',e=>{if(feldOn(e.target)){FELD.cur=e.target;if(e.target._fdirty)feldGrow(e.target);feldUi()}});
document.addEventListener('focusout',e=>{if(e.target===FELD.cur){FELD.cur=null;feldUi()}});
addEventListener('scroll',()=>{if(FELD.cur)feldUi()},{capture:true,passive:true});
addEventListener('resize',()=>{document.querySelectorAll('textarea').forEach(ta=>{if(ta._fm&&feldSichtbar(ta)){ta._fm=null;ta.style.height='';ta._flen=1e9;feldGrow(ta)}})});
// Großansicht: ganzer Bildschirm am Handy, großes Fenster am Rechner. Fertig (auch Esc oder daneben tippen) übernimmt
// den Text ins Feld, Senden schickt ab, wo das Feld etwas abschickt. Nichts geht verloren.
function feldGross(ta){let m=$('feldmodal');
  if(!m){m=document.createElement('div');m.id='feldmodal';m.className='modal';m.style.display='none';
    m.innerHTML='<div class="card modalcard feldcard" role="dialog" aria-modal="true" aria-labelledby="feldtitel"><div class="feldkopf"><button type="button" class="b" id="feldfertig"></button><b id="feldtitel"></b><button type="button" class="b p" id="feldsenden"></button></div>'+
      '<textarea id="feldtext" data-fest></textarea><div class="feldfuss"><span id="feldtipp"></span><span id="feldzahl2"></span></div></div>';
    document.body.appendChild(m);
    $('feldfertig').onclick=()=>feldZu(false);$('feldsenden').onclick=()=>feldZu(true);
    m.addEventListener('click',e=>{if(e.target===m)feldZu(false)});
    m.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();feldZu(false)}});
    $('feldtext').addEventListener('input',()=>{const z=feldZahl($('feldtext'));$('feldzahl2').textContent=z})}
  FELD.box=ta;feldUi();const big=$('feldtext');
  $('feldfertig').textContent=t('Fertig','Done');$('feldsenden').textContent=t('Senden','Send');$('feldsenden').hidden=!ta.dataset.senden;
  const lab=ta.labels&&ta.labels[0]?ta.labels[0].textContent:'';$('feldtitel').textContent=(lab||ta.getAttribute('aria-label')||t('Text bearbeiten','Edit text')).trim().slice(0,60);
  $('feldtipp').textContent=t('Neue Zeile mit Enter','Enter makes a new line');
  if(ta.maxLength>0)big.maxLength=ta.maxLength;else big.removeAttribute('maxlength');
  big.placeholder=ta.placeholder||'';big.value=ta.value;$('feldzahl2').textContent=feldZahl(big);
  m.style.display='grid';big.focus();big.setSelectionRange(ta.selectionStart,ta.selectionEnd)}
function feldZu(senden){const ta=FELD.box,big=$('feldtext');$('feldmodal').style.display='none';FELD.box=null;if(!ta)return;
  if(ta.value!==big.value){ta.value=big.value;ta.dispatchEvent(new Event('input',{bubbles:true}))}
  if(senden)feldSend(ta);else{ta.focus();const n=ta.value.length;ta.setSelectionRange(n,n)}}
window.feldGrow=feldGrow;window.feldEnterSendet=feldEnterSendet;
