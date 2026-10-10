// The chosen light or dark look before the page is drawn (no flash). Its own file since the strict CSP (V01.0.286).
try{const th=localStorage.getItem("theme");if(th==="light"||th==="dark")document.documentElement.dataset.theme=th}catch{}
