// Zeichnen: the three helpers the panel (index.html, before base.js) and the Spark-Konsole (konsole.html, before
// modellgenau.js) share; nothing else, no state, no fetch.
// writes HTML only when it differs from what this place shows (polled tables: marking, focus and hover stay)
function setHtml(el,h){if(el&&el._h!==h){el.innerHTML=h;el._h=h}}
// draws a polled page with fields anew and keeps what the user is doing (Dominik 2026-11-16 „anzeige springt immer
// wieder zurück“): a field changed by hand keeps its value, focus and cursor stay, a [data-halten] box keeps its content
// when the new one is empty, the page keeps its scroll position. A field nobody touched takes the new value.
function felderNeu(el,h){if(!el)return;const a=document.activeElement,fokus=a&&a.id&&el.contains(a)?a.id:'',alt={},box={};
  const sel=fokus&&a.selectionStart!=null?[a.selectionStart,a.selectionEnd]:null,y=scrollY;
  const anders=f=>f.type==='checkbox'||f.type==='radio'?f.checked!==f.defaultChecked:f.tagName==='SELECT'?[...f.options].some(o=>o.selected!==o.defaultSelected):f.value!==f.defaultValue;
  el.querySelectorAll('input[id],select[id],textarea[id]').forEach(f=>{if(f.type!=='file'&&anders(f))alt[f.id]=f.type==='checkbox'||f.type==='radio'?f.checked:f.value});
  el.querySelectorAll('[data-halten][id]').forEach(x=>{box[x.id]=x.innerHTML});
  el.innerHTML=h;el._h=h;
  for(const id in alt){const f=document.getElementById(id);if(!f||!el.contains(f))continue;
    if(f.type==='checkbox'||f.type==='radio')f.checked=alt[id];else if(f.tagName!=='SELECT'||[...f.options].some(o=>o.value===alt[id]))f.value=alt[id]}
  for(const id in box){const x=document.getElementById(id);if(x&&el.contains(x)&&!x.innerHTML.trim())x.innerHTML=box[id]}
  const f=fokus&&document.getElementById(fokus);if(f&&el.contains(f)){f.focus({preventScroll:true});if(sel)try{f.setSelectionRange(sel[0],sel[1])}catch{}}
  if(scrollY!==y)scrollTo(0,y)}
// a small curve in an <svg> (a tile's spark line); vals may hold null, max is the top (else the highest value + 10 %)
function spark(svg,vals,max){const w=300,h=60;svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('preserveAspectRatio','none');
  const v=vals.filter(x=>x!=null);if(v.length<2){svg.innerHTML='';return}
  const m=max??(Math.max(...v)*1.1||1);const pts=vals.map((x,i)=>x==null?null:[i*w/(vals.length-1),h-2-(x/m)*(h-4)]).filter(Boolean);
  const d='M'+pts.map(p=>p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' L');
  svg.innerHTML=`<path d="${d} L${w} ${h} L0 ${h}Z" fill="var(--acc)" opacity=".12"/><path d="${d}" fill="none" stroke="var(--acc)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;}
