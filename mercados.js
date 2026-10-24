// ---------- 📰 Mercados: comentarios de mercado diarios / semanales / mensuales / trimestrales / anuales ----------
// Datos (todos en data/mercados/):
//   mercado.json                        series diarias de ~45 activos (mercados_datos.py)
//   fondos/<periodo>_<clave>.json       fondos que más suben/bajan, una clase por fondo (mercados_fondos.py)
//   comentarios/<periodo>/<clave>.json  comentario razonado (lo escribe Claude cada día; ver PROCESO-mercados.md)
//   index.json                          claves disponibles por periodo (mercados_index.py)
(function(){
const PER = {Diario:"diario", Semanal:"semanal", Quincenal:"quincenal", Mensual:"mensual", Trimestral:"trimestral", Semestral:"semestral", Anual:"anual"};
const ORIGEN_COL = {Bankinter:"#1f3864", ABANCA:"#c0392b", IronIA:"#e67e22"};
const MES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];
const st = {per:"diario", clave:null, cache:{}, vistaClase:"general"};
try{const s=JSON.parse(localStorage.getItem("fb_merc_v1")||"null");if(s&&s.vistaClase)st.vistaClase=s.vistaClase;}catch(e){}
const save=()=>{try{localStorage.setItem("fb_merc_v1",JSON.stringify({vistaClase:st.vistaClase}));}catch(e){}};

(function css(){const s=document.createElement("style");s.textContent=`
#mercados{padding:6px 20px 40px;max-width:1280px}
#mercados .mk-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0}
#mercados .mk-bar select,#mercados .mk-bar button{background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:7px 10px;font-size:13px;cursor:pointer}
#mercados .mk-bar button.on{background:var(--navy);color:#fff;border-color:var(--navy)}
#mercados .mk-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0}
#mercados h2{font-size:18px;color:var(--navy);margin:0 0 6px}
#mercados h3{font-size:15px;color:var(--navy);margin:0 0 8px}
#mercados .mk-res{font-size:14.5px;line-height:1.55}
#mercados .mk-res p{margin:0 0 8px}
#mercados ul.mk-claves{margin:6px 0 0 18px;padding:0}
#mercados ul.mk-claves li{margin:3px 0}
#mercados .mk-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:14px}
#mercados .mk-grid>div{min-width:0;overflow-x:auto}
#mercados table.mk{width:100%;border-collapse:collapse;font-size:12.5px}
#mercados table.mk th{text-align:left;color:var(--muted);font-weight:600;border-bottom:1px solid var(--line);padding:5px 6px;white-space:nowrap}
#mercados table.mk td{border-bottom:1px solid var(--line);padding:5px 6px;vertical-align:top}
#mercados table.mk td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
#mercados .up{color:#15803d;font-weight:600}#mercados .dn{color:#b91c1c;font-weight:600}
@media (prefers-color-scheme:dark){#mercados .up{color:#4ade80}#mercados .dn{color:#f87171}}
#mercados .mk-mov{border-left:4px solid var(--line);padding:6px 10px;margin:8px 0;background:var(--zebra);border-radius:0 8px 8px 0}
#mercados .mk-mov.s{border-left-color:#16a34a}#mercados .mk-mov.b{border-left-color:#dc2626}
#mercados .mk-mov b{color:var(--ink)}
#mercados .mk-src{font-size:11.5px;color:var(--muted)}
#mercados .mk-src a{color:var(--accent)}
#mercados .mk-tag{display:inline-block;font-size:9.5px;font-weight:700;color:#fff;border-radius:4px;padding:1px 5px;margin-left:4px;vertical-align:middle}
#mercados .mk-why{font-size:11.5px;color:var(--muted);margin-top:2px}
#mercados .mk-pend{background:#fff7e6;border:1px solid #f5c26b;color:#7a4b00;border-radius:10px;padding:10px 12px;font-size:13px}
@media (prefers-color-scheme:dark){#mercados .mk-pend{background:#2a2110;border-color:#7a5a1a;color:#f5d28a}}
#mercados details summary{cursor:pointer;color:var(--navy);font-weight:600}
#mercados .mk-heat{display:inline-block;min-width:58px;text-align:right;padding:1px 5px;border-radius:4px}
#mercados mark.mk-hl{background:#e6e8ec;color:inherit;padding:0 3px;border-radius:3px;box-decoration-break:clone;-webkit-box-decoration-break:clone}
@media (prefers-color-scheme:dark){#mercados mark.mk-hl{background:#3a4152}}
#mercados .mk-tipos{border-left:4px solid #64748b}
`;document.head.appendChild(s);})();

const esc = s => (window.escHtml?escHtml(s==null?"":s):String(s==null?"":s));
// texto del comentario: se escapa y lo marcado como ==así== se sombrea en gris claro (lo más relevante)
const tx = s => esc(s).replace(/==(.+?)==/g,'<mark class="mk-hl">$1</mark>');
const fmt = (v,d=2) => v==null||isNaN(v)?"—":(v>0?"+":"")+v.toLocaleString("es-ES",{minimumFractionDigits:d,maximumFractionDigits:d});
const cls = v => v==null?"":v>0?"up":v<0?"dn":"";
const pct = (v,d=2) => `<span class="${cls(v)}">${fmt(v,d)} %</span>`;
const heat = (v,u) => { if(v==null||isNaN(v))return '<span class="mk-heat">—</span>';
  const k=u==="pct"?Math.min(1,Math.abs(v)/25):Math.min(1,Math.abs(v)/6);
  const c=v>=0?`rgba(22,163,74,${.12+.45*k})`:`rgba(220,38,38,${.12+.45*k})`;
  return `<span class="mk-heat" style="background:${c}">${fmt(v,u==="pct"?0:2)}${u==="pct"?" pb":" %"}</span>`; };
const getJ = p => st.cache[p]!==undefined?Promise.resolve(st.cache[p]):
  fetch(p,{cache:"no-store"}).then(r=>r.ok?r.json():null).catch(()=>null).then(j=>(st.cache[p]=j));

function etiqueta(per,c){
  if(per==="diario"){const d=new Date(c+"T12:00:00");return d.toLocaleDateString("es-ES",{weekday:"long",day:"numeric",month:"long",year:"numeric"});}
  if(per==="semanal"){const f=new Date(c+"T12:00:00"),i=new Date(f-4*864e5);return `semana del ${i.getDate()} ${MES[i.getMonth()]} al ${f.getDate()} ${MES[f.getMonth()]} ${f.getFullYear()}`;}
  if(per==="quincenal"){const [y,m,q]=c.split("-");return `${q==="1"?"1.ª":"2.ª"} quincena de ${MES[+m-1]} ${y}`;}
  if(per==="semestral")return `${c.slice(-1)}.º semestre ${c.slice(0,4)}`;
  if(per==="mensual"){const [y,m]=c.split("-");return `${MES[+m-1]} ${y}`;}
  if(per==="trimestral")return `${c.slice(-1)}.º trimestre ${c.slice(0,4)}`;
  return `año ${c}`;
}
function rango(per,c){ // [inicio(cierre previo), fin] como YYYY-MM-DD
  const iso=d=>d.toISOString().slice(0,10), D=s=>new Date(s+"T12:00:00Z");
  if(per==="diario"){return [null,c];}
  if(per==="semanal"){return [iso(new Date(D(c)-7*864e5)),c];}
  if(per==="mensual"){const [y,m]=c.split("-").map(Number);return [iso(new Date(Date.UTC(y,m-1,0,12))),iso(new Date(Date.UTC(y,m,0,12)))];}
  if(per==="quincenal"){const [y,m,q]=c.split("-").map(Number);return q===1?[iso(new Date(Date.UTC(y,m-1,0,12))),iso(new Date(Date.UTC(y,m-1,15,12)))]:[iso(new Date(Date.UTC(y,m-1,15,12))),iso(new Date(Date.UTC(y,m,0,12)))];}
  if(per==="semestral"){const y=+c.slice(0,4),h=+c.slice(-1);return h===1?[`${y-1}-12-31`,`${y}-06-30`]:[`${y}-06-30`,`${y}-12-31`];}
  if(per==="trimestral"){const y=+c.slice(0,4),q=+c.slice(-1);return [iso(new Date(Date.UTC(y,3*q-3,0,12))),iso(new Date(Date.UTC(y,3*q,0,12)))];}
  const y=+c;return [`${y-1}-12-31`,`${y}-12-31`];
}
function valorEn(serie,keys,d){ // último valor en o antes de d
  let lo=0,hi=keys.length-1,r=-1;while(lo<=hi){const m=(lo+hi)>>1;if(keys[m]<=d){r=m;lo=m+1;}else hi=m-1;}
  return r<0?[null,null]:[serie[keys[r]],keys[r]];
}
function cambio(a,ini,fin,per){
  const keys=a._k||(a._k=Object.keys(a.serie).sort());
  let [v1,k1]=valorEn(a.serie,keys,fin);
  if(v1==null)return null;
  let v0,k0;
  if(per==="diario"){ if(k1!==fin)return {sinDato:true}; const i=keys.indexOf(k1);if(i<1)return null;k0=keys[i-1];v0=a.serie[k0]; }
  else{ [v0,k0]=valorEn(a.serie,keys,ini); if(v0==null)return null; }
  const d=a.unidad==="pct"?(v1-v0)*100:(v1/v0-1)*100;
  return {v:d,ult:v1,k0,k1};
}

window.__mkMk=()=>getJ("data/mercados/mercado.json").then(j=>(st.mk=j));
window.__mkIx=()=>getJ("data/mercados/index.json");
window.__mkEtq=(p,c)=>etiqueta(p,c); window.__mkRango=(p,c)=>rango(p,c);
window.__mkIr=(p,c)=>{const t=Object.keys(PER).find(k=>PER[k]===p);st.per=p;st.clave=c;window.__group="Mercados";selectTab(t);syncGroup();};
window.showMercados = function(tab){
  ["toolbar","legend","chips","wrap","euribor","intereses","chat","movers","semanal","panel","score","cartera","constructor","cuando","guia","estructura","percentiles","scenarios","weekly","weekhist","carteras","siblings","mapa","antiinfla","ironia"].forEach(id=>{const e=document.getElementById(id);if(e)e.style.display="none";});
  const el=document.getElementById("mercados");el.style.display="block";
  const per=PER[tab]||"diario"; if(per!==st.per){st.per=per;st.clave=null;}
  if(!el.innerHTML)el.innerHTML='<div class="eu-note">Cargando mercados…</div>';
  Promise.all([getJ("data/mercados/index.json"),getJ("data/mercados/mercado.json")]).then(([ix,mk])=>{
    st.ix=ix||{}; st.mk=mk; render();
  });
};

function claves(){ const ix=st.ix||{}; return (ix[st.per]||[]).slice().sort().reverse(); }

function render(){
  const el=document.getElementById("mercados"); const ks=claves();
  if(!st.clave||!ks.includes(st.clave))st.clave=ks[0]||null;
  const tabsHtml=`<b style="color:var(--navy)">${esc(Object.keys(PER).find(t=>PER[t]===st.per))}</b>`;
  if(!st.clave){el.innerHTML=`<div class="mk-bar">${tabsHtml}</div><div class="mk-pend">Aún no hay datos para este periodo.</div>`;return;}
  const i=ks.indexOf(st.clave);
  const sel=`<select onchange="__mkSet(this.value)">${ks.map(k=>`<option value="${k}" ${k===st.clave?"selected":""}>${esc(etiqueta(st.per,k))}</option>`).join("")}</select>`;
  el.innerHTML=`<div class="mk-bar">${tabsHtml}<span style="flex:1"></span>
     <button ${i>=ks.length-1?"disabled":""} onclick="__mkSet('${ks[i+1]||""}')" title="Anterior">◀</button>${sel}
     <button ${i<=0?"disabled":""} onclick="__mkSet('${ks[i-1]||""}')" title="Siguiente">▶</button></div>
     <div id="mkBody"><div class="eu-note">Cargando…</div></div>`;
  const per=st.per,c=st.clave;
  Promise.all([getJ(`data/mercados/comentarios/${per}/${c}.json`),getJ(`data/mercados/fondos/${per}_${c}.json`)])
    .then(([com,fon])=>{ if(st.per===per&&st.clave===c)document.getElementById("mkBody").innerHTML=cuerpo(per,c,com,fon); });
}
window.__mkSet=k=>{if(k){st.clave=k;render();}};
window.__mkVista=v=>{st.vistaClase=v;save();render();};

function cuerpo(per,c,com,fon){
  let h="";
  // 1) comentario
  if(com){
    h+=`<div class="mk-card"><h2>${esc(com.titulo||etiqueta(per,c))}</h2>
      <div class="eu-note">${esc(etiqueta(per,c))}${com.fase==="mercado"?" · <b>avance de la noche</b>: el ranking de fondos se completa por la mañana con los VL del día":""}${com.generado?" · escrito "+esc(com.generado.replace("T"," ").slice(0,16)):""}</div>
      <div class="mk-res">${(com.resumen||"").split(/\n\n+/).map(p=>`<p>${tx(p)}</p>`).join("")}</div>
      ${com.claves&&com.claves.length?`<ul class="mk-claves">${com.claves.map(x=>`<li>${tx(x)}</li>`).join("")}</ul>`:""}</div>`;
    if(com.tipos&&(com.tipos.texto||(com.tipos.puntos||[]).length))h+=`<div class="mk-card mk-tipos"><h3>🏦 Tipos de interés: por qué se movieron</h3>
      <div class="mk-res">${(com.tipos.texto||"").split(/\n\n+/).map(p=>`<p>${tx(p)}</p>`).join("")}</div>
      ${(com.tipos.puntos||[]).map(t=>`<div class="mk-mov"><b>${esc(t.bono)}</b> <span class="${/^[+]/.test(t.cambio||"")?"dn":/^[−-]/.test(t.cambio||"")?"up":""}">${esc(t.cambio||"")}</span><div>${tx(t.por_que||"")}</div>${src(t.fuentes)}</div>`).join("")}
      ${src(com.tipos.fuentes)}</div>`;
  } else {
    h+=`<div class="mk-card"><h2>${esc(etiqueta(per,c))}</h2><div class="mk-pend">Comentario pendiente: se escribe ${per==="diario"?"a las 23:00 (mercados) y se completa a las 09:30 del día siguiente (fondos)":"al cerrar el periodo"}. Abajo, los datos ya disponibles.</div></div>`;
  }
  // 2) qué subió y bajó y por qué
  if(com&&((com.suben||[]).length||(com.bajan||[]).length)){
    const mov=(l,k)=>(l||[]).map(m=>`<div class="mk-mov ${k}"><b>${esc(m.activo)}</b> <span class="${k==="s"?"up":"dn"}">${esc(m.cambio||"")}</span>
        <div>${tx(m.por_que||"")}</div>${src(m.fuentes)}</div>`).join("");
    h+=`<div class="mk-grid"><div class="mk-card"><h3>▲ Lo que más subió y por qué</h3>${mov(com.suben,"s")}</div>
        <div class="mk-card"><h3>▼ Lo que más bajó y por qué</h3>${mov(com.bajan,"b")}</div></div>`;
  }
  if(com&&(com.drivers||[]).length){
    h+=`<div class="mk-card"><h3>Motores del ${per==="diario"?"día":"periodo"}</h3>${com.drivers.map(d=>`<div class="mk-mov"><b>${esc(d.tema)}</b><div>${tx(d.texto)}</div>${src(d.fuentes)}</div>`).join("")}</div>`;
  }
  // 3) termómetro
  h+=termometro(per,c);
  // 4) fondos
  h+=fondos(per,c,com,fon);
  // 5) tus fondos
  h+=tusFondos(fon);
  // 6) agenda y glosario
  if(com&&(com.agenda||[]).length)h+=`<div class="mk-card"><h3>📅 Qué vigilar a continuación</h3><table class="mk"><tr><th>Fecha</th><th>Evento</th><th>Por qué importa</th></tr>${com.agenda.map(a=>`<tr><td class="n">${esc(a.fecha||"")}</td><td>${esc(a.evento||"")}</td><td>${tx(a.por_que_importa||"")}</td></tr>`).join("")}</table></div>`;
  if(com&&(com.glosario||[]).length)h+=`<div class="mk-card"><details><summary>Glosario de siglas y términos</summary><table class="mk">${com.glosario.map(g=>`<tr><td><b>${esc(g.sigla)}</b></td><td>${esc(g.def)}</td></tr>`).join("")}</table></details></div>`;
  h+=`<div class="mk-card"><details><summary>Cómo se calcula</summary><div class="eu-note" style="font-size:12.5px">
    <p><b>Mercados</b>: cierres diarios de Yahoo Finance (bolsas, divisas, materias primas, volatilidad), FRED (bonos de EE. UU. y diferencial high yield) y BCE (curva AAA de la zona euro). Bonos: variación de la TIR en puntos básicos (pb; 100 pb = 1 punto). El resto: variación en %.</p>
    <p><b>Fondos</b>: Bankinter y solo-ABANCA con su VL oficial (en EUR); solo-IronIA con el precio del Financial Times (IronIA no publica VL diario), una clase por fondo de las familias que no están en Bankinter/ABANCA. Una clase por fondo en el ranking (prefiere EUR y la de menor coste). Día: solo fondos con VL exactamente ese día frente a su VL anterior (≤ 5 días). Periodos: VL final ≤ 3 días del cierre y VL inicial ≤ 5 días del cierre previo. «En divisa» = rentabilidad en la moneda de la clase: la diferencia con la de EUR es el efecto divisa. Se apartan como «dudosos» los saltos imposibles para su clase (p. ej. > 3 % en un día en renta fija), casi siempre repartos de dividendo o errores de dato.</p>
    <p>Los comentarios son análisis propios con enlaces a las fuentes; no copian las noticias. No son recomendación de inversión.</p></div></details></div>`;
  return h;
}
function src(f){ if(!f||!f.length)return""; return `<div class="mk-src">Fuentes: ${f.map(x=>x.u?`<a href="${esc(x.u)}" target="_blank" rel="noopener">${esc(x.t||x.u)}</a>`:esc(x.t||"")).join(" · ")}</div>`; }

window.__mkTermo=(ini,fin,label)=>{st.mk=st.mk||null;return termometroR("rango",ini,fin,label);};
function termometro(per,c){ const [ini,fin]=rango(per,c); return termometroR(per,ini,fin,etiqueta(per,c),c); }
function termometroR(per,ini,fin,label,c){
  const mk=st.mk; if(!mk)return"";
  c=c||fin;
  const grupos={};
  mk.activos.forEach(a=>{const ch=cambio(a,ini,fin,per);(grupos[a.grupo]=grupos[a.grupo]||[]).push({a,ch});});
  const extra=per==="diario"; const y=c.slice(0,4);
  let h=`<div class="mk-card"><h3>🌡️ Termómetro de mercado · ${esc(label)}</h3><div class="mk-grid">`;
  Object.entries(grupos).forEach(([g,l])=>{
    l.sort((p,q)=>((q.ch&&q.ch.v)||-1e9)-((p.ch&&p.ch.v)||-1e9));
    h+=`<div><table class="mk"><tr><th>${esc(g)}</th><th class="n">Último</th><th class="n">${per==="diario"?"Día":"Periodo"}</th>${extra?'<th class="n">Semana</th><th class="n">Año</th>':""}</tr>`;
    l.forEach(({a,ch})=>{
      const fin2=ch&&ch.k1?ch.k1:fin;
      const w=extra?cambio(a,new Date(new Date(fin2+"T12:00:00Z")-7*864e5).toISOString().slice(0,10),fin2,"semanal"):null;
      const yy=extra?cambio(a,`${+y-1}-12-31`,fin2,"anual"):null;
      const ult=ch&&ch.ult!=null?ch.ult.toLocaleString("es-ES",{maximumFractionDigits:a.unidad==="pct"?2:(ch.ult>1000?0:2)})+(a.unidad==="pct"?" %":""):"—";
      h+=`<tr><td title="${esc(a.fuente+" · "+a.codigo)}">${esc(a.nombre)}</td><td class="n">${ult}</td><td class="n">${ch&&ch.sinDato?'<span class="mk-src" title="La fuente aún no ha publicado el dato de ese día (FRED y BCE van con 1 día de retraso) o no hubo sesión">pendiente</span>':heat(ch&&ch.v,a.unidad)}</td>${extra?`<td class="n">${heat(w&&w.v,a.unidad)}</td><td class="n">${heat(yy&&yy.v,a.unidad)}</td>`:""}</tr>`;
    });
    h+=`</table></div>`;
  });
  return h+`</div></div>`;
}

function filaFondo(f,why){
  const tag=(f.en||[f.origen]).map(o=>`<span class="mk-tag" style="background:${ORIGEN_COL[o]||"#555"};${o===f.origen?"":"opacity:.45"}" title="${o===f.origen?"Clase mostrada":"También disponible en "+o}">${esc(o)}</span>`).join("");
  const ficha=window.__fichaFondo(f.isin,f.origen);
  return `<tr><td><a href="${ficha}" target="_blank" rel="noopener" style="color:var(--ink);text-decoration:none"><b>${esc(f.nombre)}</b></a>${tag}<div class="mk-src">${esc(f.isin)} · ${esc(f.categoria||f.clase||"")}${f.desde!==f.hasta&&st.per!=="diario"?"":` · VL ${esc((f.hasta||"").slice(5))}`}</div>${why?`<div class="mk-why">${tx(why)}</div>`:""}</td>
    <td class="n">${pct(f.r)}</td><td class="n">${f.ccy==="EUR"?'<span class="mk-src">EUR</span>':pct(f.rn)+`<div class="mk-src">${esc(f.ccy)}</div>`}</td></tr>`;
}
function fondos(per,c,com,fon){
  if(!fon)return `<div class="mk-card"><h3>Fondos</h3><div class="mk-pend">Ranking de fondos pendiente (se calcula ${per==="diario"?"a las 09:30 del día siguiente, con los VL completos":"al cerrar el periodo"}).</div></div>`;
  const why={}; if(com&&com.fondos){(com.fondos.suben||[]).concat(com.fondos.bajan||[]).forEach(x=>why[x.isin]=x.por_que);}
  const tabla=(l,n)=>`<table class="mk"><tr><th>Fondo</th><th class="n">EUR</th><th class="n">En divisa</th></tr>${l.slice(0,n).map(f=>filaFondo(f,why[f.isin])).join("")}</table>`;
  const orig=Object.entries(fon.por_origen||{}).map(([k,v])=>`${k} ${v.toLocaleString("es-ES")}`).join(" · ");
  let h=`<div class="mk-card"><h3>📊 Fondos que más suben y bajan · ${esc(etiqueta(per,c))}</h3>
    <div class="eu-note">${fon.n_fondos.toLocaleString("es-ES")} fondos con dato (una clase por fondo): ${esc(orig)}. ${per==="diario"?"VL de "+esc(fon.fin):"Del "+esc(fon.inicio)+" al "+esc(fon.fin)}.</div>
    ${com&&com.fondos&&com.fondos.texto?`<div class="mk-res" style="margin:8px 0"><p>${tx(com.fondos.texto)}</p></div>`:""}
    <div class="mk-bar"><button class="${st.vistaClase==="general"?"on":""}" onclick="__mkVista('general')">General</button><button class="${st.vistaClase==="clase"?"on":""}" onclick="__mkVista('clase')">Por clase de activo</button></div>`;
  if(st.vistaClase==="general"){
    h+=`<div class="mk-grid"><div><h3>▲ Más suben</h3>${tabla(fon.suben,20)}</div><div><h3>▼ Más bajan</h3>${tabla(fon.bajan,20)}</div></div>`;
  } else {
    const orden=["Renta variable","Renta fija","Mixtos","Alternativos","Materias primas e inmobiliario","Monetarios","Otros"];
    const lect={}; ((com&&com.fondos&&com.fondos.por_clase)||[]).forEach(x=>{if(x&&x.clase)lect[x.clase]=x.texto;});
    Object.entries(fon.por_clase||{}).sort((a,b)=>orden.indexOf(a[0])-orden.indexOf(b[0])).forEach(([k,v])=>{
      h+=`<details ${k==="Renta variable"?"open":""} style="margin:8px 0"><summary>${esc(k)} · ${v.n} fondos · mediana ${fmt(v.mediana)} %</summary>
        ${lect[k]?`<div class="mk-res" style="margin:6px 0"><p>${tx(lect[k])}</p></div>`:""}
        <div class="mk-grid" style="margin-top:6px"><div><h3>▲ Más suben</h3>${tabla(v.suben,10)}</div><div><h3>▼ Más bajan</h3>${tabla(v.bajan,10)}</div></div></details>`;
    });
  }
  const av=(com&&com.fondos&&com.fondos.avisos)||[];
  if(av.length)h+=`<div class="mk-pend" style="margin-top:8px"><b>Datos a vigilar</b><ul style="margin:4px 0 0 18px;padding:0">${av.map(x=>`<li>${tx(typeof x==="string"?x:(x.texto||x.nota||JSON.stringify(x)))}</li>`).join("")}</ul></div>`;
  if((fon.dudosos||[]).length)h+=`<details style="margin-top:8px"><summary>Apartados como dudosos (${fon.dudosos.length})</summary><table class="mk">${fon.dudosos.map(d=>`<tr><td>${esc(d.nombre)} <span class="mk-src">${esc(d.isin)} · ${esc(d.origen)}</span></td><td class="n">${pct(d.r)}</td><td class="mk-src">${esc(d.desde)} → ${esc(d.hasta)}</td></tr>`).join("")}</table></details>`;
  return h+`</div>`;
}
function tusFondos(fon){
  if(!fon||!fon.ret)return"";
  let car=[],pins=[];
  try{car=JSON.parse(localStorage.getItem("mi_cartera")||"[]").map(p=>p.isin);}catch(e){}
  try{const g=JSON.parse(localStorage.getItem("fb_find_v1")||"null");pins=(g&&g.set)||[];}catch(e){}
  const all=[...new Set([...car,...pins])];
  if(!all.length)return `<div class="mk-card"><h3>💼 Tus fondos</h3><div class="eu-note">Añade fondos en Herramientas → Mi Cartera o fíjalos (pines) en Gráficos y aparecerán aquí con su rentabilidad del periodo.</div></div>`;
  const by={};(typeof DATA!=="undefined"?DATA:[]).forEach(d=>by[d.Isin]=d);
  const rows=all.map(i=>({i,r:fon.ret[i],d:by[i]})).sort((a,b)=>((b.r&&b.r[0])??-1e9)-((a.r&&a.r[0])??-1e9));
  return `<div class="mk-card"><h3>💼 Tus fondos (cartera y fijados)</h3><table class="mk"><tr><th>Fondo</th><th></th><th class="n">EUR</th><th class="n">En divisa</th></tr>${rows.map(x=>`<tr><td><b>${esc(x.d?x.d.Name||x.d.LegalName:x.i)}</b> <span class="mk-src">${esc(x.i)}</span></td><td class="mk-src">${car.includes(x.i)?"cartera":"fijado"}</td><td class="n">${x.r?pct(x.r[0]):'<span class="mk-src">sin VL del periodo</span>'}</td><td class="n">${x.r&&x.r[1]!=null?pct(x.r[1]):"—"}</td></tr>`).join("")}</table></div>`;
}
})();

// página del fondo: Bankinter → su ficha oficial; ABANCA → ficha (o quefondos); IronIA → su tienda
window.__fichaFondo=function(isin,origen){
  const d=(typeof DATA!=="undefined"?DATA:[]).find(x=>x.Isin===isin);
  if(origen==="IronIA")return `https://store.ironia.tech/${isin}`;
  return (d&&d.FichaURL)||`https://www.quefondos.com/es/fondos/ficha/index.html?isin=${isin}`;
};
// ---------- 📈 Evolución: ventana creciente (desde la fecha que elijas hasta hoy) ----------
(function(){
const ORIGEN_COL = {Bankinter:"#1f3864", ABANCA:"#c0392b", IronIA:"#e67e22"};
const esc = s => (window.escHtml?escHtml(s==null?"":s):String(s==null?"":s));
const fmt = (v,d=2) => v==null||isNaN(v)?"—":(v>0?"+":"")+v.toLocaleString("es-ES",{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtN = (v,d=2) => v==null||isNaN(v)?"—":v.toLocaleString("es-ES",{minimumFractionDigits:d,maximumFractionDigits:d});
const S = {ini:null, fin:null, origen:"", clase:"", q:"", mios:false, top:15, sort:"r", dir:-1, extra:[], page:0, clu:[]};
try{Object.assign(S, JSON.parse(localStorage.getItem("fb_evo_v1")||"{}"));}catch(e){}
const save=()=>{try{const {ini,fin,origen,clase,mios,top,sort,dir,extra,clu}=S;localStorage.setItem("fb_evo_v1",JSON.stringify({ini,fin,origen,clase,mios,top,sort,dir,extra,clu}));}catch(e){}};
// --- tus clusters (los de Gráficos, con tus ediciones): miembros por la misma regla, sobre Bankinter + ABANCA + IronIA
const CLU = () => (typeof CLUSTERS!=="undefined"?CLUSTERS:[]);
let cluCache={key:"",sets:{}};
function cluSet(id){
  const key=localStorage.getItem("fb_clusters_v1")||"";
  if(cluCache.key!==key)cluCache={key,sets:{}};
  if(cluCache.sets[id])return cluCache.sets[id];
  const c=CLU().find(x=>x.id===id); if(!c||typeof cluMembers!=="function")return new Set();
  const pool=(typeof DATA!=="undefined"?DATA:[]).concat(typeof ironiaAsData==="function"?ironiaAsData():[]);
  const all={};pool.forEach(d=>all[d.Isin]=d);
  const set=new Set(cluMembers(c,pool,all).map(d=>d.Isin));
  Object.keys(c.fixedIronia||{}).forEach(i=>set.add(i));
  return (cluCache.sets[id]=set);
}
function enClusters(f){ // ids de los clusters (activos en el filtro) a los que pertenece el fondo o una clase hermana
  return S.clu.filter(id=>{const st=cluSet(id);return st.has(f.i)||(f.h||[]).some(x=>st.has(x));});
}
let EV=null;

function cargar(){
  if(EV)return Promise.resolve(EV);
  return fetch("data/mercados/evolucion.json",{cache:"no-store"}).then(r=>r.json()).then(j=>{
    j.fondos.forEach(f=>{const v=new Array(j.fechas.length).fill(null);let acc=0;f.d.forEach((x,k)=>{acc+=x;v[f.s+k]=acc;});f.v=v;delete f.d;});
    EV=j;return j;});
}
window.__evCargar=()=>cargar(); window.__evIdx=f=>idxDe(f); window.__evMet=(f,a,b)=>metricas(f,a,b);
function idxDe(fecha){const F=EV.fechas;let lo=0,hi=F.length-1,r=0;while(lo<=hi){const m=(lo+hi)>>1;if(F[m]<=fecha){r=m;lo=m+1;}else hi=m-1;}return r;}
function misIsin(){let a=[];try{a=a.concat(JSON.parse(localStorage.getItem("mi_cartera")||"[]").map(p=>p.isin));}catch(e){}
  try{const g=JSON.parse(localStorage.getItem("fb_find_v1")||"null");a=a.concat((g&&g.set)||[]);}catch(e){}return new Set(a);}

function metricas(f,a,b){
  const v0=f.v[a],v1=f.v[b]; if(v0==null||v1==null)return null;
  const F=EV.fechas; let peak=v0,mdd=0,ss=0,gd=0,prev=v0,pd=F[a];
  for(let k=a+1;k<=b;k++){const x=f.v[k];if(x==null)continue;peak=Math.max(peak,x);mdd=Math.min(mdd,x/peak-1);
    const r=Math.log(x/prev),g=Math.max(1,Math.round((new Date(F[k])-new Date(pd))/864e5*5/7));ss+=r*r;gd+=g;prev=x;pd=F[k];}
  const anos=(new Date(F[b])-new Date(F[a]))/(365.25*864e5);
  const r=(v1/v0-1)*100;
  return {r, ra: anos>=1?(Math.pow(v1/v0,1/anos)-1)*100:null, vol: gd>10?Math.sqrt(ss/gd*252)*100:null, mdd: mdd*100};
}

window.showEvolucion=function(){
  ["toolbar","legend","chips","wrap","euribor","intereses","chat","movers","semanal","panel","score","cartera","constructor","cuando","guia","estructura","percentiles","scenarios","weekly","weekhist","carteras","siblings","mapa","antiinfla","ironia"].forEach(id=>{const e=document.getElementById(id);if(e)e.style.display="none";});
  const el=document.getElementById("mercados");el.style.display="block";
  el.innerHTML='<div class="eu-note">Cargando la evolución de ~3.600 fondos…</div>';
  const extras=[typeof loadIronia==="function"?loadIronia().catch(()=>null):null,
                typeof loadJSONData==="function"?loadJSONData("exposure.json","__expo").catch(()=>null):null];
  Promise.all([cargar(),loadECharts(),...extras]).then(()=>{
    const F=EV.fechas;
    if(!S.ini||S.ini<F[0])S.ini=`${new Date().getFullYear()}-01-01`;
    if(!S.fin||S.fin>F[F.length-1])S.fin=F[F.length-1];
    pintar();
  }).catch(e=>{el.innerHTML='<div class="mk-pend">No se pudo cargar data/mercados/evolucion.json</div>';});
};

function filtrados(a,b){
  const q=S.q.trim().toLowerCase(), mios=S.mios?misIsin():null;
  const out=[];
  EV.fondos.forEach(f=>{
    if(S.origen&&f.o!==S.origen)return; if(S.clase&&f.c!==S.clase)return;
    if(mios&&!mios.has(f.i))return;
    if(S.clu.length&&!enClusters(f).length)return;
    if(q&&!(f.n.toLowerCase().includes(q)||f.i.toLowerCase().includes(q)||(f.cat||"").toLowerCase().includes(q)))return;
    const m=metricas(f,a,b); if(m)out.push({f,...m});
  });
  return out;
}

function pintar(){
  const el=document.getElementById("mercados"),F=EV.fechas;
  const a=idxDe(S.ini),b=idxDe(S.fin);
  const clases=[...new Set(EV.fondos.map(f=>f.c))].sort();
  const sinDato=EV.fondos.filter(f=>f.v[a]==null).length;
  const rapido=[["1M",1],["3M",3],["6M",6],["Año",0],["1A",12],["3A",36],["5A",60]].map(([t,m])=>`<button onclick="__evRapido(${m})">${t}</button>`).join("");
  el.innerHTML=`<div class="mk-bar"><b style="color:var(--navy)">📈 Evolución</b><span class="eu-note">Qué fondos se han revalorizado más desde la fecha que elijas (todos parten de 100).</span></div>
   <div class="mk-bar">Desde <input type="date" value="${F[a]}" min="${F[0]}" max="${F[F.length-1]}" onchange="__evSet('ini',this.value)" style="background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:6px">
     hasta <input type="date" value="${F[b]}" min="${F[0]}" max="${F[F.length-1]}" onchange="__evSet('fin',this.value)" style="background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:6px">
     ${rapido}</div>
   <div class="mk-bar">
     <select onchange="__evSet('origen',this.value)"><option value="">Origen: todos</option>${["Bankinter","ABANCA","IronIA"].map(o=>`<option ${S.origen===o?"selected":""}>${o}</option>`).join("")}</select>
     <select onchange="__evSet('clase',this.value)"><option value="">Clase: todas</option>${clases.map(c=>`<option ${S.clase===c?"selected":""}>${esc(c)}</option>`).join("")}</select>
     <input type="search" placeholder="Buscar fondo, ISIN o categoría…" value="${esc(S.q)}" oninput="__evQ(this.value)" style="background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:7px 10px;min-width:220px">
     <label style="font-size:13px"><input type="checkbox" ${S.mios?"checked":""} onchange="__evSet('mios',this.checked)"> Solo mi cartera y fijados</label>
     <select onchange="__evSet('top',+this.value)">${[5,10,15,20,30].map(n=>`<option value="${n}" ${S.top===n?"selected":""}>Gráfico: top ${n}</option>`).join("")}</select>
   </div>
   <div class="mk-bar" style="gap:6px"><span class="eu-note">🧩 Mis clusters:</span>${CLU().map(c=>`<button class="${S.clu.includes(c.id)?"on":""}" style="${S.clu.includes(c.id)?`background:${c.color};border-color:${c.color};color:#fff`:`border-left:4px solid ${c.color}`}" onclick="__evClu('${c.id}')">${esc(c.name)}</button>`).join("")}${S.clu.length?`<button onclick="__evClu('')">✕ Quitar</button>`:""}</div>
   <div class="mk-card"><div id="evChart" style="height:460px"></div><div class="eu-note" id="evNota"></div></div>
   <div class="mk-card"><div id="evTabla"></div></div>`;
  dibujar();
}
function dibujar(){
  const F=EV.fechas,a=idxDe(S.ini),b=idxDe(S.fin);
  const L=filtrados(a,b);
  const k=S.sort, d=S.dir; L.sort((x,y)=>((y[k]??-1e9)-(x[k]??-1e9))*(d===-1?1:-1));
  const porR=[...L].sort((x,y)=>y.r-x.r);
  const enGraf=porR.slice(0,S.top).map(x=>x.f.i);
  S.extra.forEach(i=>{if(!enGraf.includes(i)&&L.some(x=>x.f.i===i))enGraf.push(i);});
  const ch=echarts.getInstanceByDom(document.getElementById("evChart"))||echarts.init(document.getElementById("evChart"));
  const dark=matchMedia("(prefers-color-scheme: dark)").matches;
  const series=enGraf.map((i,n)=>{const x=L.find(z=>z.f.i===i),f=x.f,v0=f.v[a];
    return {name:f.n,type:"line",showSymbol:false,sampling:"lttb",lineStyle:{width:S.extra.includes(i)?3:1.6,type:S.extra.includes(i)?"dashed":"solid"},
      data:F.slice(a,b+1).map((t,k)=>[t,f.v[a+k]==null?null:+(f.v[a+k]/v0*100).toFixed(2)]),
      labelLayout:{moveOverlap:"shiftY"},triggerLineEvent:true,
      endLabel:{show:n<12,formatter:()=>`{o${f.o}|${f.o==="Bankinter"?"BK":f.o==="ABANCA"?"AB":"IR"}} ${f.n.slice(0,30)} ${fmt(x.r,1)} %`,fontSize:10,color:dark?"#ddd":"#333",
        rich:{oBankinter:{backgroundColor:ORIGEN_COL.Bankinter,color:"#fff",padding:[1,3],borderRadius:3,fontSize:9,fontWeight:"bold"},
              oABANCA:{backgroundColor:ORIGEN_COL.ABANCA,color:"#fff",padding:[1,3],borderRadius:3,fontSize:9,fontWeight:"bold"},
              oIronIA:{backgroundColor:ORIGEN_COL.IronIA,color:"#fff",padding:[1,3],borderRadius:3,fontSize:9,fontWeight:"bold"}}},
      __isin:f.i,__o:f.o,name:`${f.n} · ${f.o}`};});
  ch.off("click");ch.on("click",p=>{const sr=series[p.seriesIndex];if(sr&&sr.__isin)window.open(window.__fichaFondo(sr.__isin,sr.__o),"_blank","noopener");});
  ch.setOption({animation:false,grid:{left:50,right:260,top:20,bottom:50},tooltip:{trigger:"axis",order:"valueDesc",
      formatter:p=>`<b>${p[0].axisValueLabel}</b><br>`+p.filter(z=>z.value[1]!=null).slice(0,15).map(z=>`${z.marker}${esc(z.seriesName.slice(0,40))}: <b>${fmtN(z.value[1],1)}</b>`).join("<br>")},
    xAxis:{type:"time"},yAxis:{type:"value",scale:true,name:"base 100",axisLabel:{formatter:v=>v.toFixed(0)}},
    dataZoom:[{type:"inside"},{type:"slider",height:18,bottom:8}],
    series:series.concat([{type:"line",data:[],markLine:{silent:true,symbol:"none",lineStyle:{color:"#999",type:"dotted"},data:[{yAxis:100}]}}])},true);
  const sinDato=EV.fondos.filter(f=>f.v[a]==null).length;
  document.getElementById("evNota").innerHTML=`${L.length.toLocaleString("es-ES")} fondos con dato del ${esc(F[a])} al ${esc(F[b])} (una clase por fondo, en EUR). ${sinDato?`${sinDato.toLocaleString("es-ES")} fondos no tienen dato en la fecha de inicio (más nuevos o sin histórico) y no entran.`:""} Clic en una línea o en el nombre = abre la página del fondo (Bankinter: su ficha; ABANCA: quefondos; IronIA: su tienda). ＋ añade su línea (discontinua). Etiquetas: <b>BK</b> Bankinter · <b>AB</b> ABANCA · <b>IR</b> IronIA (atenuadas: también disponible ahí).${a<F.length-260?" Antes del último año los puntos son semanales (viernes).":""}`;
  const col=(key,t,tip)=>`<th class="n" style="cursor:pointer" title="${tip||""}" onclick="__evSort('${key}')">${t}${S.sort===key?(S.dir===-1?" ▼":" ▲"):""}</th>`;
  const N=100, pag=Math.min(S.page,Math.max(0,Math.ceil(L.length/N)-1)), filas=L.slice(pag*N,pag*N+N);
  const rank=new Map(porR.map((x,k)=>[x.f.i,k+1]));
  document.getElementById("evTabla").innerHTML=`<table class="mk"><tr><th>#</th><th>Fondo</th><th>Clase</th>${col("r","Revalorización","Acumulada en EUR en el periodo")}${col("ra","Anualizada","Solo si el periodo es de 1 año o más")}${col("vol","Volatilidad","Anualizada, en el periodo")}${col("mdd","Caída máx.","Mayor caída desde un máximo, en el periodo")}</tr>
    ${filas.map(x=>{const f=x.f,on=S.extra.includes(f.i);return `<tr style="${on?"background:var(--zebra)":""}"><td class="n">${rank.get(f.i)}</td>
      <td><button title="${on?"Quitar su línea del gráfico":"Añadir su línea al gráfico"}" onclick="__evPin('${f.i}')" style="border:1px solid var(--line);background:var(--card);border-radius:6px;cursor:pointer;padding:0 4px;margin-right:4px">${on?"📌":"＋"}</button><a href="${window.__fichaFondo(f.i,f.o)}" target="_blank" rel="noopener" style="color:var(--ink)"><b>${esc(f.n)}</b></a>${(f.en||[f.o]).map(o=>`<span class="mk-tag" style="background:${ORIGEN_COL[o]};${o===f.o?"":"opacity:.45"}" title="${o===f.o?"Clase mostrada":"También disponible en "+o}">${o}</span>`).join("")}${S.clu.length?enClusters(f).map(id=>{const c=CLU().find(z=>z.id===id);return `<span class="mk-tag" style="background:${c.color}">${esc(c.name)}</span>`;}).join(""):""}<div class="mk-src">${esc(f.i)} · ${esc(f.cat||"")}${f.x&&EV.fechas[a]<f.x.desde?` · <span title="Antes del ${esc(f.x.desde)} se usa la clase hermana ${esc(f.x.nombre)} (${esc(f.x.clase)}), mismo fondo">⤺ historia de ${esc(f.x.clase)} antes del ${esc(f.x.desde)}</span>`:""}</div></td>
      <td class="mk-src">${esc(f.c)}</td><td class="n"><span class="${x.r>0?"up":x.r<0?"dn":""}">${fmt(x.r)} %</span></td><td class="n">${x.ra==null?"—":fmt(x.ra)+" %"}</td>
      <td class="n">${x.vol==null?"—":fmtN(x.vol,1)+" %"}</td><td class="n dn">${fmtN(x.mdd,1)} %</td></tr>`;}).join("")}</table>
    <div class="mk-bar">${pag>0?`<button onclick="__evPage(${pag-1})">◀ Anteriores</button>`:""}<span class="eu-note">${pag*N+1}–${Math.min(L.length,pag*N+N)} de ${L.length.toLocaleString("es-ES")}</span>${pag*N+N<L.length?`<button onclick="__evPage(${pag+1})">Siguientes ▶</button>`:""}</div>`;
}
window.__evClu=id=>{S.clu=!id?[]:(S.clu.includes(id)?S.clu.filter(x=>x!==id):[...S.clu,id]);S.page=0;save();pintar();};
window.__evSet=(k,v)=>{S[k]=v;S.page=0;save();if(k==="ini"||k==="fin")pintar();else dibujar();};
window.__evQ=v=>{S.q=v;S.page=0;clearTimeout(window.__evT);window.__evT=setTimeout(dibujar,250);};
window.__evSort=k=>{if(S.sort===k)S.dir=-S.dir;else{S.sort=k;S.dir=k==="mdd"||k==="vol"?1:-1;}save();dibujar();};
window.__evPin=i=>{S.extra=S.extra.includes(i)?S.extra.filter(x=>x!==i):[...S.extra,i];save();dibujar();};
window.__evPage=p=>{S.page=p;dibujar();document.getElementById("evTabla").scrollIntoView({behavior:"smooth"});};
window.__evRapido=m=>{const F=EV.fechas,fin=new Date(S.fin+"T12:00:00Z");let d;
  if(m===0)d=new Date(Date.UTC(fin.getUTCFullYear()-1,11,31,12));else{d=new Date(fin);d.setUTCMonth(d.getUTCMonth()-m);}
  S.ini=d.toISOString().slice(0,10);if(S.ini<F[0])S.ini=F[0];save();pintar();};
})();

// ---------- 🎛️ Personalizado: cualquier fecha de inicio y de fin ----------
(function(){
const ORIGEN_COL = {Bankinter:"#1f3864", ABANCA:"#c0392b", IronIA:"#e67e22"};
const esc = s => (window.escHtml?escHtml(s==null?"":s):String(s==null?"":s));
const fmt = (v,d=2) => v==null||isNaN(v)?"—":(v>0?"+":"")+v.toLocaleString("es-ES",{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtN = (v,d=1) => v==null||isNaN(v)?"—":v.toLocaleString("es-ES",{minimumFractionDigits:d,maximumFractionDigits:d});
const pct = v => `<span class="${v>0?"up":v<0?"dn":""}">${fmt(v)} %</span>`;
const P = {ini:null, fin:null, origen:"", clase:"", vista:"general", n:20};
try{Object.assign(P, JSON.parse(localStorage.getItem("fb_pers_v1")||"{}"));}catch(e){}
const save=()=>{try{localStorage.setItem("fb_pers_v1",JSON.stringify(P));}catch(e){}};
const PERS = ["diario","semanal","quincenal","mensual","trimestral","semestral","anual"];

window.showPersonalizado=function(){
  ["toolbar","legend","chips","wrap","euribor","intereses","chat","movers","semanal","panel","score","cartera","constructor","cuando","guia","estructura","percentiles","scenarios","weekly","weekhist","carteras","siblings","mapa","antiinfla","ironia"].forEach(id=>{const e=document.getElementById(id);if(e)e.style.display="none";});
  const el=document.getElementById("mercados");el.style.display="block";
  el.innerHTML='<div class="eu-note">Cargando…</div>';
  Promise.all([window.__evCargar(),window.__mkMk(),window.__mkIx()]).then(([EV,mk,ix])=>{
    const F=EV.fechas, hoy=F[F.length-1];
    if(!P.fin||P.fin>hoy)P.fin=hoy;
    if(!P.ini||P.ini<F[0]||P.ini>=P.fin){const d=new Date(P.fin+"T12:00:00Z");d.setUTCMonth(d.getUTCMonth()-1);P.ini=d.toISOString().slice(0,10);}
    pintar(EV,ix);
  });
};
function pintar(EV,ix){
  const el=document.getElementById("mercados"),F=EV.fechas;
  const a=window.__evIdx(P.ini), b=window.__evIdx(P.fin);
  const rap=[["1S",0,7],["2S",0,14],["1M",1],["3M",3],["6M",6],["Año",-1],["1A",12],["3A",36],["5A",60]].map(([t,m,d])=>`<button onclick="__peRap(${m},${d||0})">${t}</button>`).join("");
  const clases=[...new Set(EV.fondos.map(f=>f.c))].sort();
  const inp=(k,v)=>`<input type="date" value="${v}" min="${F[0]}" max="${F[F.length-1]}" onchange="__peSet('${k}',this.value)" style="background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:6px">`;
  // fondos del rango
  const L=[]; EV.fondos.forEach(f=>{
    if(P.origen&&f.o!==P.origen)return; if(P.clase&&f.c!==P.clase)return;
    const m=window.__evMet(f,a,b); if(m)L.push({f,...m});});
  L.sort((x,y)=>y.r-x.r);
  const fila=x=>{const f=x.f;return `<tr><td><a href="${window.__fichaFondo(f.i,f.o)}" target="_blank" rel="noopener" style="color:var(--ink)"><b>${esc(f.n)}</b></a>${(f.en||[f.o]).map(o=>`<span class="mk-tag" style="background:${ORIGEN_COL[o]};${o===f.o?"":"opacity:.45"}">${o}</span>`).join("")}<div class="mk-src">${esc(f.i)} · ${esc(f.cat||f.c)}</div></td>
    <td class="n">${pct(x.r)}</td><td class="n">${x.vol==null?"—":fmtN(x.vol)+" %"}</td><td class="n dn">${fmtN(x.mdd)} %</td></tr>`;};
  const tabla=(l)=>`<table class="mk"><tr><th>Fondo</th><th class="n">Rentab. (EUR)</th><th class="n">Volat.</th><th class="n">Caída máx.</th></tr>${l.map(fila).join("")}</table>`;
  let fondosH;
  if(P.vista==="general"){
    fondosH=`<div class="mk-grid"><div><h3>▲ Más suben</h3>${tabla(L.slice(0,P.n))}</div><div><h3>▼ Más bajan</h3>${tabla(L.slice(-P.n).reverse())}</div></div>`;
  } else {
    const orden=["Renta variable","Renta fija","Mixtos","Alternativos","Materias primas e inmobiliario","Monetarios","Otros"], g={};
    L.forEach(x=>(g[x.f.c]=g[x.f.c]||[]).push(x));
    fondosH=Object.entries(g).sort((p,q)=>orden.indexOf(p[0])-orden.indexOf(q[0])).map(([k,l])=>`<details ${k==="Renta variable"?"open":""} style="margin:8px 0"><summary>${esc(k)} · ${l.length} fondos · mediana ${fmt(l[l.length>>1].r)} %</summary><div class="mk-grid" style="margin-top:6px"><div><h3>▲ Más suben</h3>${tabla(l.slice(0,10))}</div><div><h3>▼ Más bajan</h3>${tabla(l.slice(-10).reverse())}</div></div></details>`).join("");
  }
  // tus fondos
  let mios=[];try{mios=mios.concat(JSON.parse(localStorage.getItem("mi_cartera")||"[]").map(p=>p.isin));}catch(e){}
  try{const g=JSON.parse(localStorage.getItem("fb_find_v1")||"null");mios=mios.concat((g&&g.set)||[]);}catch(e){}
  const ms=new Set(mios), tus=L.filter(x=>ms.has(x.f.i)||(x.f.h||[]).some(i=>ms.has(i)));
  // comentarios escritos dentro del rango
  const coms=[]; PERS.forEach(p=>(ix[p]||[]).forEach(c=>{const [i0,f0]=window.__mkRango(p,c);const ini0=i0||f0;if(f0<=P.fin&&ini0>=P.ini.slice(0,10)&&f0>=P.ini)coms.push([p,c]);}));
  const etq=`del ${esc(F[a])} al ${esc(F[b])}`;
  el.innerHTML=`<div class="mk-bar"><b style="color:var(--navy)">🎛️ Periodo a medida</b><span class="eu-note">Elige cualquier inicio y fin: termómetro de mercado, fondos que más suben y bajan y tus fondos, calculados al momento.</span></div>
    <div class="mk-bar">Desde ${inp("ini",F[a])} hasta ${inp("fin",F[b])} ${rap}</div>
    <div class="mk-bar"><select onchange="__peSet('origen',this.value)"><option value="">Origen: todos</option>${["Bankinter","ABANCA","IronIA"].map(o=>`<option ${P.origen===o?"selected":""}>${o}</option>`).join("")}</select>
      <select onchange="__peSet('clase',this.value)"><option value="">Clase: todas</option>${clases.map(c=>`<option ${P.clase===c?"selected":""}>${esc(c)}</option>`).join("")}</select>
      <button class="${P.vista==="general"?"on":""}" onclick="__peSet('vista','general')">General</button><button class="${P.vista==="clase"?"on":""}" onclick="__peSet('vista','clase')">Por clase de activo</button>
      <select onchange="__peSet('n',+this.value)">${[10,20,30,50].map(n=>`<option value="${n}" ${P.n===n?"selected":""}>Top ${n}</option>`).join("")}</select></div>
    ${coms.length?(()=>{const bt=([p,c])=>`<button onclick="__mkIr('${p}','${c}')">${esc(p[0].toUpperCase()+p.slice(1))} · ${esc(window.__mkEtq(p,c))}</button>`;
      const lar=coms.filter(x=>x[0]!=="diario"),dia=coms.filter(x=>x[0]==="diario");
      return `<div class="mk-card"><h3>📰 Comentarios escritos dentro de este periodo</h3><div class="mk-bar" style="gap:6px">${lar.slice().reverse().map(bt).join("")}</div>${dia.length?`<details><summary>${dia.length} comentarios diarios</summary><div class="mk-bar" style="gap:6px">${dia.slice().reverse().map(bt).join("")}</div></details>`:""}</div>`;})():""}
    ${window.__mkTermo(F[a],F[b],etq)}
    <div class="mk-card"><h3>📊 Fondos que más suben y bajan · ${etq}</h3><div class="eu-note">${L.length.toLocaleString("es-ES")} fondos con dato (una clase por fondo, en EUR). Volatilidad anualizada y caída máxima dentro del periodo.${a<F.length-260?" Antes del último año los precios son semanales (viernes): las fechas se ajustan al viernes anterior.":""}</div>${fondosH}</div>
    <div class="mk-card"><h3>💼 Tus fondos (cartera y fijados)</h3>${tus.length?tabla(tus):'<div class="eu-note">Añade fondos en Mi Cartera o fíjalos en Gráficos.</div>'}</div>`;
}
window.__peSet=(k,v)=>{P[k]=v;save();showPersonalizado();};
window.__peRap=(m,d)=>{const fin=new Date(P.fin+"T12:00:00Z");let x=new Date(fin);
  if(d)x=new Date(fin-d*864e5);else if(m===-1)x=new Date(Date.UTC(fin.getUTCFullYear()-1,11,31,12));else x.setUTCMonth(x.getUTCMonth()-m);
  P.ini=x.toISOString().slice(0,10);save();showPersonalizado();};
})();
