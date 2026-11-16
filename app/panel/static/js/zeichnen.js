// Zeichnen: the two helpers the panel (index.html, before base.js) and the Spark-Konsole (konsole.html, before
// modellgenau.js) share; nothing else, no state, no fetch.
// writes HTML only when it differs from what this place shows (polled tables: marking, focus and hover stay)
function setHtml(el,h){if(el&&el._h!==h){el.innerHTML=h;el._h=h}}
// a small curve in an <svg> (a tile's spark line); vals may hold null, max is the top (else the highest value + 10 %)
function spark(svg,vals,max){const w=300,h=60;svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('preserveAspectRatio','none');
  const v=vals.filter(x=>x!=null);if(v.length<2){svg.innerHTML='';return}
  const m=max??(Math.max(...v)*1.1||1);const pts=vals.map((x,i)=>x==null?null:[i*w/(vals.length-1),h-2-(x/m)*(h-4)]).filter(Boolean);
  const d='M'+pts.map(p=>p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' L');
  svg.innerHTML=`<path d="${d} L${w} ${h} L0 ${h}Z" fill="var(--acc)" opacity=".12"/><path d="${d}" fill="none" stroke="var(--acc)" stroke-width="1.5" vector-effect="non-scaling-stroke"/>`;}
