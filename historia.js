// ---------- 📜 Historia 2019–2025: qué productos ganaron, con qué drivers y cuánto pesó cada uno ----------
// Datos en data/historia/ (historia_analisis.py, historia_temas.py, historia_eventos.py) y textos en
// data/historia/textos/<tipo>/<id>.json (mismo esquema que los comentarios de Mercados + bloque «analistas»).
// Se pinta en el contenedor #mercados (mismos estilos).
(function(){
const ORIGEN_COL={Bankinter:"#1f3864",ABANCA:"#c0392b",IronIA:"#e67e22",IB:"#0f766e"};
const TIPO_EV={pandemia:"🦠 Pandemia",politica_monetaria:"🏦 Política monetaria",inflacion_macro:"📈 Inflación y macro",elecciones_politica:"🗳️ Elecciones y política",fiscal_deuda:"💶 Fiscal y deuda",divisas:"💱 Divisas",geopolitica:"🌍 Geopolítica",materias_primas:"🛢️ Materias primas",meteorologia_clima:"🌦️ Meteorología y clima",catastrofe_natural:"🌪️ Catástrofes",logistica:"🚢 Logística",regulacion:"📜 Regulación",tecnologia:"💻 Tecnología",crisis_financiera:"🏚️ Crisis financiera",flujos_posicionamiento:"🔁 Flujos",resultados:"📊 Resultados",estacionalidad:"📅 Estacionalidad"};
const esc=s=>(window.escHtml?escHtml(s==null?"":s):String(s==null?"":s));
const tx=s=>esc(s).replace(/==(.+?)==/g,'<mark class="mk-hl">$1</mark>');
const fmt=(v,d=1)=>v==null||isNaN(v)?"—":(v>0?"+":"")+(+v).toLocaleString("es-ES",{minimumFractionDigits:d,maximumFractionDigits:d});
const pc=(v,d=1)=>`<span class="${v>0?"up":v<0?"dn":""}">${fmt(v,d)} %</span>`;
const heat=(v,esc_=12)=>{if(v==null||isNaN(v))return '<td class="n">—</td>';const k=Math.min(1,Math.abs(v)/esc_);
  return `<td class="n" style="background:${v>=0?`rgba(22,163,74,${.1+.5*k})`:`rgba(220,38,38,${.1+.5*k})`}">${fmt(v)}</td>`;};
const cache={};
const J=p=>cache[p]!==undefined?Promise.resolve(cache[p]):fetch(`data/historia/${p}`,{cache:"no-store"}).then(r=>r.ok?r.json():null).catch(()=>null).then(j=>(cache[p]=j));
const S={tema:null,pais:null,anio:"2022",ev:null,evTipo:"",evAnio:"",q:"",fondo:null,ltTema:"ene",ltIni:"2019-01-01",ltImp:2};
try{Object.assign(S,JSON.parse(localStorage.getItem("fb_hist_v1")||"{}"));}catch(e){}
const save=()=>{try{localStorage.setItem("fb_hist_v1",JSON.stringify(S));}catch(e){}};
const TABS=["Línea temporal","Temáticas","Países","Años","Eventos","Por qué se movió","Persistencia","Regímenes","Caídas"];
const AVISO=`<div class="eu-note" style="margin:6px 0 10px">Universo: fondos de Bankinter, ABANCA e IronIA (una clase por fondo, en EUR)${""} + futuros de materias primas y ETF/ETC comprables en Interactive Brokers. <b>Sesgo de supervivencia</b>: solo productos que existen hoy. Las carteras son las actuales: el «por qué» histórico se mide con sensibilidades (betas) a los drivers, no con posiciones de entonces.</div>`;

function tag(m){return `<span class="mk-tag" style="background:${ORIGEN_COL[m.o]||"#555"}">${m.tipo==="Fondo"?m.o:m.tipo}</span>`;}
function ficha(id,m){return id.startsWith("FUT:")?"#":(window.__fichaFondo?window.__fichaFondo(id,m.o):"#");}
function nomF(id,P){const m=P[id]||{n:id,o:""};return `<a href="${ficha(id,m)}" target="_blank" rel="noopener" style="color:var(--ink)"><b>${esc(m.n)}</b></a>${tag(m)}<div class="mk-src">${esc(id.replace("FUT:",""))} · ${esc(m.cat||m.c||"")}</div>`;}
function texto(t){ if(!t)return "";
  let h=`<div class="mk-card"><h2>${esc(t.titulo||"")}</h2><div class="mk-res">${(t.resumen||"").split(/\n\n+/).map(p=>`<p>${tx(p)}</p>`).join("")}</div>${(t.claves||[]).length?`<ul class="mk-claves">${t.claves.map(x=>`<li>${tx(x)}</li>`).join("")}</ul>`:""}</div>`;
  if((t.drivers||[]).length)h+=`<div class="mk-card"><h3>Drivers y su impacto</h3>${t.drivers.map(d=>`<div class="mk-mov"><b>${esc(d.tema)}</b><div>${tx(d.texto)}</div></div>`).join("")}</div>`;
  if(t.tipos&&t.tipos.texto)h+=`<div class="mk-card mk-tipos"><h3>🏦 Tipos de interés</h3><div class="mk-res">${t.tipos.texto.split(/\n\n+/).map(p=>`<p>${tx(p)}</p>`).join("")}</div></div>`;
  if((t.analistas||[]).length)h+=`<div class="mk-card"><h3>🗣️ Lo que decían tus analistas</h3>${t.analistas.map(a=>`<div class="mk-mov"><b>${esc(a.fuente)}</b> <span class="mk-src">${esc(a.fecha||"")}</span><div>${tx(a.texto)}</div>${a.acierto?`<div class="mk-src">Balance: ${esc(a.acierto)}</div>`:""}</div>`).join("")}</div>`;
  return h;}

window.showHistoria=function(tab){
  ["toolbar","legend","chips","wrap","euribor","intereses","chat","movers","semanal","panel","score","cartera","constructor","cuando","guia","estructura","percentiles","scenarios","weekly","weekhist","carteras","siblings","mapa","antiinfla","ironia"].forEach(id=>{const e=document.getElementById(id);if(e)e.style.display="none";});
  const el=document.getElementById("mercados");el.style.display="block";el.innerHTML='<div class="eu-note">Cargando la historia…</div>';
  Promise.all([J("productos.json"),J("temas.json"),J("eventos.json"),J("anual.json")]).then(([P,T,E,A])=>{
    if(!P){el.innerHTML='<div class="mk-pend">Aún no hay datos de la Historia (historia_analisis.py).</div>';return;}
    const ctx={P,T:(T||{}).temas||[],E:E||[],A};
    const h=`<div class="mk-bar"><b style="color:var(--navy)">📜 Historia 2019–hoy · ${esc(tab)}</b></div>${AVISO}<div id="hiBody"></div>`;
    el.innerHTML=h; const b=document.getElementById("hiBody");
    ({"Línea temporal":linea,"Temáticas":(c,b)=>temasImpl(c,b,"tema"),"Países":(c,b)=>temasImpl(c,b,"pais"),"Años":anios,"Eventos":eventos,"Por qué se movió":porque,"Persistencia":persist,"Regímenes":regimen,"Caídas":caidas}[tab]||linea)(ctx,b);
  });
};
const set=(k,v,tab)=>{S[k]=v;save();showHistoria(tab);};
window.__hiSet=set;

// ---- Línea temporal: mediana base 100 de una temática con los eventos marcados
function linea(c,b){
  Promise.all([fetch("data/mercados/evolucion.json",{cache:"no-store"}).then(r=>r.json()),J("eventos_impacto.json"),loadECharts()]).then(([EV,EI])=>{
    const F=EV.fechas, opts=c.T.map(t=>`<option value="${t.id}" ${S.ltTema===t.id?"selected":""}>${esc(t.nombre)}${t.tipo==="pais"?" (país)":""}</option>`).join("");
    b.innerHTML=`<div class="mk-bar">Temática <select onchange="__hiSet('ltTema',this.value,'Línea temporal')">${opts}</select>
      Desde <input type="date" value="${S.ltIni}" min="${F[0]}" onchange="__hiSet('ltIni',this.value,'Línea temporal')" style="background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:6px">
      Eventos <select onchange="__hiSet('ltImp',+this.value,'Línea temporal')">${[[3,"solo los grandes"],[2,"importantes"],[1,"todos"]].map(([v,l])=>`<option value="${v}" ${S.ltImp===v?"selected":""}>${l}</option>`).join("")}</select></div>
      <div class="mk-card"><div id="hiChart" style="height:480px"></div><div class="eu-note">Línea: mediana de la temática (base 100) y, en gris, la de todos los fondos. Pulsa un evento (▼) para ver su impacto.</div></div><div id="hiEv"></div>`;
    const tema=c.T.find(t=>t.id===S.ltTema)||c.T[0], ids=new Set(Object.keys(c.P).filter(i=>(c.P[i].temas||[]).includes(tema.id)));
    const a=F.findIndex(d=>d>=S.ltIni), fl=EV.fondos;
    fl.forEach(f=>{if(!f.v){const v=new Array(F.length).fill(null);let acc=0;f.d.forEach((x,k)=>{acc+=x;v[f.s+k]=acc;});f.v=v;}});
    const med=sel=>F.slice(a).map((d,k)=>{const xs=[];sel.forEach(f=>{const v0=f.v[a],v=f.v[a+k];if(v0&&v)xs.push(v/v0*100);});xs.sort((p,q)=>p-q);return [d,xs.length?+xs[xs.length>>1].toFixed(2):null];});
    const selT=fl.filter(f=>ids.has(f.i)||(f.h||[]).some(x=>ids.has(x)));
    const evs=c.E.filter(e=>e.fecha>=F[a]&&(e.importancia||1)>=S.ltImp);
    const ch=echarts.init(document.getElementById("hiChart"));
    ch.setOption({animation:false,tooltip:{trigger:"axis"},legend:{top:0},grid:{left:50,right:20,top:30,bottom:50},xAxis:{type:"time"},yAxis:{type:"value",scale:true},
      dataZoom:[{type:"inside"},{type:"slider",height:18,bottom:6}],
      series:[{name:`${tema.nombre} (${selT.length} fondos)`,type:"line",showSymbol:false,data:med(selT),lineStyle:{width:2.5,color:tema.color},
        markPoint:{symbol:"pin",symbolSize:22,label:{show:false},data:evs.map(e=>({name:e.titulo,coord:[e.fecha,null],value:"",__id:e.id,itemStyle:{color:"#64748b"}})).map(p=>{const d=med(selT).find(x=>x[0]>=p.coord[0]);return d?{...p,coord:[d[0],d[1]]}:null;}).filter(Boolean)}},
        {name:"Todos los fondos",type:"line",showSymbol:false,data:med(fl.filter(f=>c.P[f.i]&&c.P[f.i].tipo==="Fondo")),lineStyle:{width:1,color:"#9ca3af"}}]});
    ch.on("click",p=>{if(p.componentType==="markPoint"){const e=c.E.find(x=>x.titulo===p.name);if(e)verEvento(c,e,EI,"hiEv");}});
  });
}
function verEvento(c,e,EI,dest){
  const imp=(EI||[]).find(x=>x.id===e.id), el=document.getElementById(dest);
  let h=`<div class="mk-card"><h2>${esc(e.titulo)}</h2><div class="eu-note">${esc(e.fecha)}${e.fin?" → "+esc(e.fin):""} · ${esc(TIPO_EV[e.tipo]||e.tipo)} · ${esc((e.pais||[]).join(", "))}</div>
    <div class="mk-res"><p>${tx(e.mecanismo||"")}</p></div>${(e.activos_afectados||[]).length?`<div class="mk-src">${e.activos_afectados.map(a=>`${esc(a.activo)} ${esc(a.sentido||"")} ${esc(a.magnitud||"")}`).join(" · ")}</div>`:""}
    ${(e.fuentes||[]).length?`<div class="mk-src">Fuentes: ${e.fuentes.map(f=>`<a href="${esc(f.u)}" target="_blank" rel="noopener">${esc(f.t)}</a>`).join(" · ")}</div>`:""}</div>`;
  if(imp){
    const tm=Object.entries(imp.temas||{}).map(([k,v])=>[c.T.find(t=>t.id===k),v]).filter(x=>x[0]).sort((p,q)=>(q[1]["+20"]??-99)-(p[1]["+20"]??-99));
    h+=`<div class="mk-card"><h3>Impacto por temática (mediana)</h3><div style="overflow-x:auto"><table class="mk"><tr><th>Temática</th><th class="n">Día</th><th class="n">+5 sesiones</th><th class="n">+20</th><th class="n">+60</th></tr>${tm.map(([t,v])=>`<tr><td>${esc(t.nombre)}</td>${heat(v.dia,4)}${heat(v["+5"],8)}${heat(v["+20"],12)}${heat(v["+60"],20)}</tr>`).join("")}</table></div></div>`;
    const W=imp.ventanas["+20"]||imp.ventanas["+5"], fila=([i,r])=>`<tr><td>${nomF(i,c.P)}</td><td class="n">${pc(r)}</td></tr>`;
    if(W)h+=`<div class="mk-grid"><div class="mk-card"><h3>▲ Más ganaron (+20 sesiones)</h3><table class="mk">${W.suben.map(fila).join("")}</table></div><div class="mk-card"><h3>▼ Más perdieron</h3><table class="mk">${W.bajan.map(fila).join("")}</table></div></div>`;
  }
  J(`textos/evento/${e.id}.json`).then(t=>{el.innerHTML=texto(t)+h;el.scrollIntoView({behavior:"smooth"});});
}

// ---- Temáticas / Países
function temasImpl(c,b,tipo){
  const L=c.T.filter(t=>t.tipo===tipo), anios=Object.keys(c.A.anios).sort(), key=tipo==="tema"?"tema":"pais", tab=tipo==="tema"?"Temáticas":"Países";
  const sel=S[key]&&L.find(t=>t.id===S[key])?S[key]:null;
  let h=`<div class="mk-card"><h3>${tipo==="tema"?"Temáticas":"Países y regiones"}: mediana de rentabilidad anual (EUR)</h3><div style="overflow-x:auto"><table class="mk"><tr><th>${tipo==="tema"?"Temática":"País"}</th><th class="n">Fondos</th>${anios.map(a=>`<th class="n">${a}</th>`).join("")}</tr>
    ${L.map(t=>{const d=c.A.por_tema[t.id]||{};return `<tr style="cursor:pointer" onclick="__hiSet('${key}','${t.id}','${tab}')"><td><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${t.color}"></span> <b>${esc(t.nombre)}</b></td><td class="n">${t.n_fondos}</td>${anios.map(a=>heat(d[a]&&d[a].mediana,25)).join("")}</tr>`;}).join("")}</table></div><div class="eu-note">Pulsa una fila para ver sus fondos, drivers, caídas y regímenes.</div></div>`;
  b.innerHTML=h+`<div id="hiDet"></div>`;
  if(!sel)return;
  const t=L.find(x=>x.id===sel), ids=Object.keys(c.P).filter(i=>(c.P[i].temas||[]).includes(t.id));
  Promise.all([J(`textos/${key}/${t.id}.json`),J("caidas.json"),J("regimenes.json"),J("coste.json")]).then(([TX,CA,RE,CO])=>{
    const rows=ids.map(i=>({i,r:anios.map(a=>(c.A.anios[a][i]||[])[0]),tot:(()=>{let x=1,ok=0;anios.forEach(a=>{const v=(c.A.anios[a][i]||[])[0];if(v!=null){x*=1+v/100;ok++;}});return ok?(x-1)*100:null;})()})).sort((p,q)=>(q.tot??-1e9)-(p.tot??-1e9));
    let d=texto(TX);
    d+=`<div class="mk-card"><h3>${esc(t.nombre)}: todos sus productos, año a año</h3><div style="overflow-x:auto"><table class="mk"><tr><th>Producto</th>${anios.map(a=>`<th class="n">${a}</th>`).join("")}<th class="n">Acumulado</th></tr>${rows.map(x=>`<tr><td>${nomF(x.i,c.P)}</td>${x.r.map(v=>heat(v,30)).join("")}<td class="n"><b>${fmt(x.tot)}</b></td></tr>`).join("")}</table></div></div>`;
    if(CA)d+=`<div class="mk-card"><h3>Caídas y recuperación (mediana)</h3><table class="mk"><tr><th>Episodio</th><th class="n">Caída</th><th class="n">Días hasta recuperar</th></tr>${CA.map(e=>{const v=(e.temas||{})[t.id];return v?`<tr><td>${esc(e.nombre)} <span class="mk-src">${esc(e.desde)}→${esc(e.hasta)}</span></td><td class="n">${pc(v.caida)}</td><td class="n">${v.dias_recuperar??"sin recuperar"}</td></tr>`:"";}).join("")}</table></div>`;
    if(RE&&RE.temas[t.id])d+=`<div class="mk-card"><h3>Regímenes: rentabilidad mensual media</h3><table class="mk"><tr><th>Situación</th><th class="n">Media mensual</th><th class="n">% meses positivos</th><th class="n">Meses</th></tr>${Object.entries(RE.temas[t.id]).map(([k,v])=>`<tr><td>${esc(k.replace(":",": "))}</td>${heat(v.media,5)}<td class="n">${fmt(v.positivos,0)} %</td><td class="n">${v.meses}</td></tr>`).join("")}</table></div>`;
    if(CO&&CO[t.id])d+=`<div class="mk-card"><h3>Coste</h3><div class="eu-note">${esc(CO[t.id].nota)} (${CO[t.id].n} fondos con TER).</div></div>`;
    document.getElementById("hiDet").innerHTML=d;
  });
}

// ---- Años
function anios(c,b){
  const L=Object.keys(c.A.anios).sort(), an=L.includes(S.anio)?S.anio:L[L.length-1], v=c.A.anios[an];
  const temasM=c.T.map(t=>[t,(c.A.por_tema[t.id]||{})[an]]).filter(x=>x[1]).sort((p,q)=>q[1].mediana-p[1].mediana);
  const prods=Object.entries(v).filter(([i,x])=>x[0]!=null).sort((p,q)=>q[1][0]-p[1][0]);
  const fila=([i,x])=>`<tr><td>${nomF(i,c.P)}</td><td class="n">${pc(x[0])}</td><td class="n">${fmt(x[1])} %</td><td class="n dn">${fmt(x[2])} %</td></tr>`;
  const evs=c.E.filter(e=>e.fecha.startsWith(an)).sort((p,q)=>p.fecha<q.fecha?-1:1);
  b.innerHTML=`<div class="mk-bar">${L.map(a=>`<button class="${a===an?"on":""}" onclick="__hiSet('anio','${a}','Años')">${a}</button>`).join("")}</div><div id="hiTx"></div>
    <div class="mk-card"><h3>Temáticas y países en ${an} (mediana)</h3><div style="overflow-x:auto"><table class="mk"><tr><th>Temática / país</th><th class="n">Mediana</th><th class="n">Productos</th></tr>${temasM.map(([t,d])=>`<tr><td>${esc(t.nombre)}</td>${heat(d.mediana,30)}<td class="n">${d.n}</td></tr>`).join("")}</table></div></div>
    <div class="mk-grid"><div class="mk-card"><h3>▲ Los 25 mejores de ${an}</h3><table class="mk"><tr><th>Producto</th><th class="n">Rent.</th><th class="n">Volat.</th><th class="n">Caída máx.</th></tr>${prods.slice(0,25).map(fila).join("")}</table></div>
    <div class="mk-card"><h3>▼ Los 25 peores</h3><table class="mk"><tr><th>Producto</th><th class="n">Rent.</th><th class="n">Volat.</th><th class="n">Caída máx.</th></tr>${prods.slice(-25).reverse().map(fila).join("")}</table></div></div>
    <div class="mk-card"><h3>Eventos de ${an} (${evs.length})</h3>${evs.map(e=>`<div class="mk-mov" style="cursor:pointer" onclick="__hiSet('ev','${e.id}','Eventos')"><b>${esc(e.fecha)} · ${esc(e.titulo)}</b> <span class="mk-src">${esc(TIPO_EV[e.tipo]||e.tipo)}</span></div>`).join("")}</div>`;
  J(`textos/anual/${an}.json`).then(t=>{const x=document.getElementById("hiTx");if(x)x.innerHTML=texto(t);});
}

// ---- Eventos
function eventos(c,b){
  J("eventos_impacto.json").then(EI=>{
    const anios=[...new Set(c.E.map(e=>e.fecha.slice(0,4)))].sort();
    const L=c.E.filter(e=>(!S.evTipo||e.tipo===S.evTipo||(e.tipos_secundarios||[]).includes(S.evTipo))&&(!S.evAnio||e.fecha.startsWith(S.evAnio))&&(!S.q||(e.titulo+" "+(e.pais||[]).join(" ")).toLowerCase().includes(S.q.toLowerCase())));
    b.innerHTML=`<div class="mk-bar"><select onchange="__hiSet('evTipo',this.value,'Eventos')"><option value="">Todos los tipos</option>${Object.entries(TIPO_EV).map(([k,l])=>`<option value="${k}" ${S.evTipo===k?"selected":""}>${l}</option>`).join("")}</select>
      <select onchange="__hiSet('evAnio',this.value,'Eventos')"><option value="">Todos los años</option>${anios.map(a=>`<option ${S.evAnio===a?"selected":""}>${a}</option>`).join("")}</select>
      <input type="search" placeholder="Buscar (país, tema…)" value="${esc(S.q)}" onchange="__hiSet('q',this.value,'Eventos')" style="background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:7px 10px"><span class="eu-note">${L.length} eventos</span></div>
      <div class="mk-grid"><div class="mk-card" style="max-height:640px;overflow:auto">${L.map(e=>`<div class="mk-mov" style="cursor:pointer;${S.ev===e.id?"border-left-color:var(--accent)":""}" onclick="__hiSet('ev','${e.id}','Eventos')"><b>${esc(e.fecha)}</b> ${esc(e.titulo)}<div class="mk-src">${esc(TIPO_EV[e.tipo]||e.tipo)} · ${esc((e.pais||[]).join(", "))}${"★".repeat(e.importancia||1)}</div></div>`).join("")}</div><div id="hiEv2"></div></div>`;
    const e=c.E.find(x=>x.id===S.ev); if(e)verEvento(c,e,EI,"hiEv2");
  });
}

// ---- Por qué se movió (atribución por drivers)
function porque(c,b){
  J("atribucion.json").then(AT=>{
    const L=Object.keys(AT.fondos), q=(S.q||"").toLowerCase();
    const cand=q?L.filter(i=>(c.P[i]&&c.P[i].n.toLowerCase().includes(q))||i.toLowerCase().includes(q)).slice(0,30):[];
    const id=S.fondo&&AT.fondos[S.fondo]?S.fondo:null;
    let h=`<div class="mk-bar"><input type="search" placeholder="Busca un fondo, ETF o ISIN…" value="${esc(S.q)}" oninput="clearTimeout(window.__hiT);window.__hiT=setTimeout(()=>__hiSet('q',this.value,'Por qué se movió'),400)" style="background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:8px;padding:7px 10px;min-width:320px"></div>
      ${cand.length?`<div class="mk-card">${cand.map(i=>`<div class="mk-mov" style="cursor:pointer" onclick="__hiSet('fondo','${i}','Por qué se movió')">${esc(c.P[i]?c.P[i].n:i)} ${c.P[i]?tag(c.P[i]):""}</div>`).join("")}</div>`:""}`;
    if(id){
      const R=AT.fondos[id], an=Object.keys(R).sort(), dr=AT.drivers;
      h+=`<div class="mk-card"><h2>${nomF(id,c.P)}</h2><div class="eu-note">${esc(AT.nota)}. R² = parte de los movimientos semanales que explican los drivers.</div><div id="hiAt" style="height:420px"></div>
        <div style="overflow-x:auto"><table class="mk"><tr><th>Año</th><th class="n">Rentab.</th>${dr.map(d=>`<th class="n">${esc(d)}</th>`).join("")}<th class="n">Propio</th><th class="n">R²</th></tr>
        ${an.map(a=>`<tr><td>${a}</td><td class="n"><b>${fmt(R[a].r)}</b></td>${R[a].c.map(v=>heat(v,15)).join("")}${heat(R[a].propio,15)}<td class="n">${fmt(R[a].R2*100,0)} %</td></tr>`).join("")}</table></div></div>`;
      b.innerHTML=h;
      loadECharts().then(()=>{const ch=echarts.init(document.getElementById("hiAt"));
        ch.setOption({tooltip:{trigger:"axis",axisPointer:{type:"shadow"}},legend:{type:"scroll",top:0},grid:{left:50,right:20,top:40,bottom:30},xAxis:{type:"category",data:an},yAxis:{type:"value",name:"puntos de rentabilidad"},
          series:dr.map((d,k)=>({name:d,type:"bar",stack:"x",data:an.map(a=>R[a].c[k])})).concat([{name:"Propio (gestión)",type:"bar",stack:"x",data:an.map(a=>R[a].propio),itemStyle:{color:"#94a3b8"}},{name:"Rentabilidad del año",type:"line",data:an.map(a=>R[a].r),symbolSize:8,lineStyle:{width:0},itemStyle:{color:"#111827"}}])});});
    } else b.innerHTML=h+`<div class="eu-note">Busca un producto para ver, año a año, cuántos puntos de su rentabilidad vienen de cada driver (bolsa, dólar, tipos, petróleo, oro, cobre, estilo, emergentes) y cuánto es mérito propio.</div>`;
  });
}

// ---- Persistencia, Regímenes, Caídas
function persist(c,b){J("persistencia.json").then(PE=>{if(!PE)return;
  const M=PE.global, tot=M.map(r=>r.reduce((a,x)=>a+x,0)), q=["Peor 20 %","2.º","3.º","4.º","Mejor 20 %"];
  const tem=Object.entries(PE.por_tema).map(([k,v])=>[c.T.find(t=>t.id===k),v]).filter(x=>x[0]&&x[1].top>=5).sort((p,q)=>q[1].top_repite/q[1].top-p[1].top_repite/p[1].top);
  b.innerHTML=`<div class="mk-card"><h3>¿Los ganadores repiten? (quintiles dentro de su categoría, año a año)</h3><div class="eu-note">Fila = quintil un año; columna = quintil al año siguiente. Si fuera azar, cada casilla rondaría el 20 %.</div>
    <table class="mk"><tr><th>Año N \\ N+1</th>${q.map(x=>`<th class="n">${x}</th>`).join("")}</tr>${M.map((r,i)=>`<tr><td><b>${q[i]}</b></td>${r.map(x=>heat(tot[i]?x/tot[i]*100-20:null,15).replace(/>[^<]*<\/td>$/,`>${tot[i]?fmt(x/tot[i]*100,0).replace("+",""):"—"} %</td>`)).join("")}</tr>`).join("")}</table></div>
    <div class="mk-card"><h3>Por temática: % de los del mejor quintil que al año siguiente siguen en la mitad alta</h3><table class="mk"><tr><th>Temática</th><th class="n">Casos</th><th class="n">Repiten</th></tr>${tem.map(([t,v])=>`<tr><td>${esc(t.nombre)}</td><td class="n">${v.top}</td>${heat(v.top_repite/v.top*100-40,40).replace(/>[^<]*<\/td>$/,`>${fmt(v.top_repite/v.top*100,0).replace("+","")} %</td>`)}</tr>`).join("")}</table></div>`;});}
function regimen(c,b){J("regimenes.json").then(RE=>{if(!RE)return;
  const cols=["tipos:suben","tipos:bajan","dolar:sube","dolar:baja","petroleo:sube","petroleo:baja","crisis:sí"];
  const L=c.T.filter(t=>RE.temas[t.id]);
  b.innerHTML=`<div class="mk-card"><h3>Qué temáticas ganan en cada situación (rentabilidad mensual media, %)</h3><div class="eu-note">Meses con: tipos de EE. UU. a 10 años ±0,15 pp; dólar ±1 % frente al euro; Brent ±5 %; crisis = VIX por encima de 30.</div>
    <div style="overflow-x:auto"><table class="mk"><tr><th>Temática / país</th>${cols.map(k=>`<th class="n">${esc(k.replace(":"," "))}</th>`).join("")}</tr>${L.map(t=>`<tr><td>${esc(t.nombre)}</td>${cols.map(k=>heat((RE.temas[t.id][k]||{}).media,5)).join("")}</tr>`).join("")}</table></div></div>`;});}
function caidas(c,b){J("caidas.json").then(CA=>{if(!CA)return;
  const L=c.T.filter(t=>CA.some(e=>(e.temas||{})[t.id]));
  b.innerHTML=`<div class="mk-card"><h3>Caídas (mediana) y días hasta recuperar</h3><div style="overflow-x:auto"><table class="mk"><tr><th>Temática / país</th>${CA.map(e=>`<th class="n">${esc(e.nombre)}</th>`).join("")}</tr>${L.map(t=>`<tr><td>${esc(t.nombre)}</td>${CA.map(e=>{const v=(e.temas||{})[t.id];return v?heat(v.caida,40).replace(/<\/td>$/,`<div class="mk-src">${v.dias_recuperar!=null?v.dias_recuperar+" d":"sin recuperar"}</div></td>`):'<td class="n">—</td>';}).join("")}</tr>`).join("")}</table></div></div>`;});}

window.__HIST_TABS=TABS;
})();
