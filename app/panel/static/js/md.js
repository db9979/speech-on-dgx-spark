// Answers as formatted text: a small Markdown reader for the chat (headings, bold, italic, lists,
// quotes, code, tables, links). Model text is data, never markup: every node is made with
// createElement and filled with textContent, nothing of it goes through innerHTML. Only the elements
// below are made, links only for http(s) to public addresses (like netguard: no localhost, no LAN or
// link-local address, no user:password@), they open in a new tab without referrer and show their
// host when the link text says something else. Pictures are not loaded (no tracking pixel), only
// linked. The spoken text is cleaned on the Spark (textnorm.strip_markdown), md.plain() gives the
// same clean text in the browser.
const md=(()=>{
  const MAX=60000,DEPTH=6;   // longer answers are shown as plain text, deeper nesting as text
  const LIST=/^(\s*)([-*+•]|\d{1,3}[.)])\s+(.*)$/,FENCE=/^\s{0,3}(```|~~~)/,HEAD=/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/,
    RULE=/^\s{0,3}([-*_])(\s*\1){2,}\s*$/,QUOTE=/^\s{0,3}>\s?(.*)$/,SEP=/^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
  const INLINE=new RegExp([
    '`([^`\\n]{1,2000})`',                                             // 1 code
    '\\*\\*(?=\\S)([^\\n]{1,2000}?\\S)\\*\\*',                          // 2 bold
    '(?<!\\w)__(?=\\S)([^\\n]{1,2000}?\\S)__(?!\\w)',                   // 3 bold
    '~~(?=\\S)([^\\n]{1,2000}?\\S)~~',                                  // 4 struck
    '(?<![\\w*])\\*(?=[^\\s*])([^*\\n]{0,2000}?[^\\s*])\\*(?![\\w*])',   // 5 italic, not "3 * 4"
    '(?<![\\w_])_(?=[^\\s_])([^_\\n]{0,2000}?[^\\s_])_(?![\\w_])',       // 6 italic, not snake_case
    '!?\\[([^\\]\\n]{1,300})\\]\\(\\s*<?([^\\s)>]{1,2000})>?(?:\\s+"[^"\\n]{0,200}")?\\s*\\)',   // 7,8 link
    '<(https?:\\/\\/[^>\\s]{1,2000})>',                                 // 9 autolink
    '(https?:\\/\\/[^\\s<>"]{1,2000}[^\\s<>"().,;:!?\'»“”])'].join('|'),'g');   // 10 bare address
  const PRIVATE=[/^127\./,/^10\./,/^192\.168\./,/^172\.(1[6-9]|2\d|3[01])\./,/^169\.254\./,/^0\./,/^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\./,/^22[4-9]\.|^2[3-5]\d\./];
  // a link the browser may open: http(s), a public host, no credentials; else null (shown as text)
  function href(u){let x;try{x=new URL(u)}catch{return null}
    if(!/^https?:$/.test(x.protocol)||x.username||x.password)return null;
    const h=x.hostname.toLowerCase().replace(/\.$/,'');
    if(!h||h==='localhost'||/\.(localhost|local|lan|internal|intranet|home|fritz\.box|home\.arpa|corp)$/.test(h)||!h.includes('.'))return null;
    if(/^[\d.]+$/.test(h)&&PRIVATE.some(r=>r.test(h)))return null;
    if(h.startsWith('['))return null;   // IPv6 literals: loopback, link-local and ULA look alike, so never
    return x}
  function link(par,label,u,depth){const x=href(u);
    if(!x){const s=document.createElement('span');s.className='md-nolink';s.title=t('Kein Link: nur öffentliche http(s)-Adressen werden verlinkt','Not a link: only public http(s) addresses are linked');
      s.textContent=label===u?u:label+' ('+u+')';par.appendChild(s);return}
    const a=document.createElement('a');a.href=x.href;a.target='_blank';a.rel='noopener noreferrer nofollow';
    if(label===u)a.textContent=u;else inline(a,label,depth+1,true);   // no link inside a link
    par.appendChild(a);
    if(label!==u&&label.replace(/^https?:\/\/(www\.)?/i,'').split(/[/?#]/)[0].toLowerCase()!==x.hostname.replace(/^www\./,'')){
      const h=document.createElement('span');h.className='md-host';h.textContent=' ('+x.hostname+')';par.appendChild(h)}}
  function wrap(par,tag,inner,depth,nolink){const e=document.createElement(tag);inline(e,inner,depth+1,nolink);par.appendChild(e)}
  function inline(par,s,depth=0,nolink=false){if(depth>DEPTH){par.appendChild(document.createTextNode(s));return}
    let at=0,m;const re=new RegExp(INLINE.source,'g');
    while((m=re.exec(s))){if(m.index>at)par.appendChild(document.createTextNode(s.slice(at,m.index)));at=re.lastIndex;
      if(m[1]!=null){const c=document.createElement('code');c.textContent=m[1];par.appendChild(c)}
      else if(m[2]!=null||m[3]!=null)wrap(par,'strong',m[2]??m[3],depth,nolink);
      else if(m[4]!=null)wrap(par,'del',m[4],depth,nolink);
      else if(m[5]!=null||m[6]!=null)wrap(par,'em',m[5]??m[6],depth,nolink);
      else if(nolink)par.appendChild(document.createTextNode(m[7]??m[9]??m[10]));
      else if(m[7]!=null)link(par,m[7],m[8],depth);
      else link(par,m[9]??m[10],m[9]??m[10],depth)}
    if(at<s.length)par.appendChild(document.createTextNode(s.slice(at)))}
  const ind=l=>l.match(/^\s*/)[0].replace(/\t/g,'    ').length;
  function cells(l){return l.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(c=>c.trim())}
  function table(par,head,rows){const w=document.createElement('div');w.className='md-tbl';const tb=document.createElement('table');
    const tr=document.createElement('tr');for(const c of head){const th=document.createElement('th');inline(th,c);tr.appendChild(th)}
    const th=document.createElement('thead');th.appendChild(tr);tb.appendChild(th);const body=document.createElement('tbody');
    for(const r of rows){const x=document.createElement('tr');for(let i=0;i<head.length;i++){const td=document.createElement('td');inline(td,r[i]||'');x.appendChild(td)}body.appendChild(x)}
    tb.appendChild(body);w.appendChild(tb);par.appendChild(w)}
  // lines[i..] that form one list at this indent; returns the next line index
  function list(par,lines,i,depth){const first=lines[i].match(LIST),base=ind(lines[i]),ordered=/\d/.test(first[2]);
    const l=document.createElement(ordered?'ol':'ul');if(ordered&&parseInt(first[2],10)!==1)l.start=parseInt(first[2],10);
    let li=null;
    while(i<lines.length){const line=lines[i],m=line.match(LIST);
      if(!line.trim()){if(i+1<lines.length&&LIST.test(lines[i+1])&&ind(lines[i+1])>=base){i++;continue}break}
      if(m&&ind(line)===base&&/\d/.test(m[2])===ordered){li=document.createElement('li');inline(li,m[3]);l.appendChild(li);i++;continue}
      if(m&&ind(line)>base&&li&&depth<DEPTH){i=list(li,lines,i,depth+1);continue}
      if(!m&&li&&ind(line)>base){li.appendChild(document.createElement('br'));inline(li,line.trim());i++;continue}
      break}
    par.appendChild(l);return i}
  function blocks(par,lines,depth){let i=0,p=null;const end=()=>{p=null};
    while(i<lines.length){const line=lines[i];let m;
      if(!line.trim()){end();i++;continue}
      if((m=line.match(FENCE))){end();const close=m[1],code=[];i++;
        while(i<lines.length&&!lines[i].trim().startsWith(close))code.push(lines[i++]);i++;
        const pre=document.createElement('pre'),c=document.createElement('code');c.textContent=code.join('\n');pre.appendChild(c);par.appendChild(pre);continue}
      if((m=line.match(HEAD))){end();const h=document.createElement(m[1].length<=2?'h3':m[1].length===3?'h4':'h5');inline(h,m[2]);par.appendChild(h);i++;continue}
      if(RULE.test(line)){end();par.appendChild(document.createElement('hr'));i++;continue}
      if(QUOTE.test(line)&&depth<DEPTH){end();const q=[];while(i<lines.length&&(m=lines[i].match(QUOTE)))q.push(m[1]),i++;
        const b=document.createElement('blockquote');blocks(b,q,depth+1);par.appendChild(b);continue}
      if(line.includes('|')&&i+1<lines.length&&SEP.test(lines[i+1])&&lines[i+1].includes('-')){end();const head=cells(line).slice(0,20),rows=[];i+=2;
        while(i<lines.length&&lines[i].includes('|')&&lines[i].trim()&&rows.length<200)rows.push(cells(lines[i++]));
        table(par,head,rows);continue}
      if(LIST.test(line)){end();i=list(par,lines,i,depth);continue}
      if(p)p.appendChild(document.createElement('br'));else{p=document.createElement('p');par.appendChild(p)}
      inline(p,line.trim());i++}}
  // shows text as formatted answer in el (keeps nothing of el's old content)
  function render(el,text){text=String(text||'');el.textContent='';
    if(text.length>MAX){el.textContent=text;return}
    const box=document.createElement('div');box.className='md';blocks(box,text.replace(/\r\n?/g,'\n').split('\n'),0);el.appendChild(box)}
  // the same text without Markdown signs (copy, the small answer line, devices without formatting)
  function plain(text){let s=String(text||'');if(s.length>MAX)return s;
    s=s.replace(/\r\n?/g,'\n').replace(/^\s{0,3}(```|~~~).*$/gm,'').replace(/^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/gm,'$1')
      .replace(/^\s{0,3}>\s?/gm,'').replace(/^(\s*)[-*+]\s+/gm,'$1• ').replace(/^\s{0,3}([-*_])(\s*\1){2,}\s*$/gm,'')
      .replace(/^[ \t]*\|?[ \t]*:?-{2,}:?[ \t]*(\|[ \t]*:?-{2,}:?[ \t]*)*\|?[ \t]*$\n?/gm,'').replace(/^[ \t]*\|(.*)\|[ \t]*$/gm,(_,r)=>r.split('|').map(c=>c.trim()).join(' · '));
    return s.replace(new RegExp(INLINE.source,'g'),(all,c,b1,b2,st,i1,i2,lt,lu,au,bu)=>c??b1??b2??st??i1??i2??(lt!=null?(lt===lu?lu:plain(lt)+' ('+lu+')'):(au??bu)))
      .replace(/\n{3,}/g,'\n\n').trim()}
  return {render,plain,href}})();
