/* ── Estado de la aplicación ───────────────────────────────────── */
let modelos             = [];   // [{nombre, r2, etapa}, ...]
let map                 = null; // instancia Leaflet
let marker              = null; // marcador draggable
let ciudadesDisponibles = [];   // valores exactos de BigQuery
let capasciudades       = {};   // {nombre: L.geoJSON layer}

const COLOMBIA_CENTER = [4.5709, -74.2973];
const COLOMBIA_ZOOM   = 6;

/* ── Arranque ──────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
  cargarModelos();
  cargarOpciones();
  initMap();
  document.getElementById("predict-form").addEventListener("submit", onSubmit);
  document.getElementById("modelo").addEventListener("change", actualizarBadgeR2);
  document.getElementById("lat").addEventListener("change", sincronizarDesdeInputs);
  document.getElementById("lon").addEventListener("change", sincronizarDesdeInputs);

  // Steppers de alcobas y baños
  document.querySelectorAll(".step-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const input = document.getElementById(btn.dataset.target);
      const delta = parseInt(btn.dataset.delta, 10);
      const min   = parseInt(input.min, 10);
      const max   = parseInt(input.max, 10);
      const cur   = parseInt(input.value, 10);
      const next  = Math.max(min, Math.min(max, (isNaN(cur) ? 0 : cur) + delta));
      input.value = next;
      input.classList.remove("invalid");
      document.getElementById("err-" + input.id).textContent = "";
    });
  });
});

/* ── Carga de modelos desde la API ─────────────────────────────── */
async function cargarModelos() {
  const sel = document.getElementById("modelo");
  try {
    const resp = await fetch("/api/modelos");
    if (!resp.ok) throw new Error(await resp.text());
    modelos = await resp.json();

    sel.innerHTML = "";
    modelos.forEach((m, i) => {
      const opt = document.createElement("option");
      opt.value = m.nombre;
      opt.textContent = formatNombreModelo(m.nombre);
      if (i === 0) opt.selected = true;
      sel.appendChild(opt);
    });
    actualizarBadgeR2();
  } catch (err) {
    sel.innerHTML = '<option value="">Error al cargar modelos</option>';
    console.error("Error cargando modelos:", err);
  }
}

function formatNombreModelo(nombre) {
  return nombre
    .replace(/_/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase());
}

function actualizarBadgeR2() {
  const sel   = document.getElementById("modelo");
  const badge = document.getElementById("badge-r2");
  const info  = modelos.find(m => m.nombre === sel.value);
  if (info) {
    badge.textContent = `R² = ${info.r2.toFixed(4)}`;
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }
}

/* ── Carga de opciones (selects dinámicos) ─────────────────────── */
async function cargarOpciones() {
  try {
    const resp = await fetch("/api/opciones");
    if (!resp.ok) throw new Error(await resp.text());
    const { ciudad, tipo } = await resp.json();

    ciudadesDisponibles = ciudad;   // guardar para validar contra el mapa
    poblarSelect("ciudad", ciudad);
    cargarLimitesCiudades(ciudad);
    poblarSelect("tipo",   tipo);
  } catch (err) {
    ["ciudad", "tipo"].forEach(id => {
      document.getElementById(id).innerHTML =
        '<option value="">Error al cargar</option>';
    });
    console.error("Error cargando opciones:", err);
  }
}

function poblarSelect(id, valores) {
  const sel = document.getElementById(id);
  sel.innerHTML = '<option value="">Seleccione…</option>';
  valores.forEach(v => {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    sel.appendChild(opt);
  });
}

/* ── Validación del formulario ─────────────────────────────────── */
const CAMPOS = [
  { id: "modelo",  label: "modelo" },
  { id: "ciudad",  label: "ciudad" },
  { id: "tipo",    label: "tipo" },
  { id: "area_m2", label: "área", tipo: "decimal", min: 1,     max: 10000 },
  { id: "alcobas", label: "alcobas", tipo: "entero", min: 0,   max: 20 },
  { id: "banos",   label: "baños",   tipo: "entero", min: 0,   max: 20 },
  { id: "lat",     label: "latitud", tipo: "decimal", min: -4.3, max: 13.0 },
  { id: "lon",     label: "longitud",tipo: "decimal", min: -81.8, max: -66.8 },
];

function limpiarErrores() {
  CAMPOS.forEach(c => {
    const el  = document.getElementById(c.id);
    const err = document.getElementById("err-" + c.id);
    if (el)  el.classList.remove("invalid");
    if (err) err.textContent = "";
  });
}

function mostrarError(id, msg) {
  const el  = document.getElementById(id);
  const err = document.getElementById("err-" + id);
  if (el)  el.classList.add("invalid");
  if (err) err.textContent = msg;
}

function validar() {
  let ok = true;
  limpiarErrores();

  CAMPOS.forEach(c => {
    const el = document.getElementById(c.id);
    if (!el) return;
    const val = el.value.trim();

    if (!val) {
      mostrarError(c.id, `El campo ${c.label} es obligatorio.`);
      ok = false;
      return;
    }

    if (c.tipo === "entero") {
      if (!/^-?\d+$/.test(val)) {
        mostrarError(c.id, `${c.label} debe ser un número entero.`);
        ok = false;
        return;
      }
      const n = parseInt(val, 10);
      if (n < c.min || n > c.max) {
        mostrarError(c.id, `${c.label} debe estar entre ${c.min} y ${c.max}.`);
        ok = false;
      }
    }

    if (c.tipo === "decimal") {
      const n = parseFloat(val);
      if (isNaN(n)) {
        mostrarError(c.id, `${c.label} debe ser un número.`);
        ok = false;
        return;
      }
      if (n < c.min || n > c.max) {
        mostrarError(c.id, `${c.label} debe estar entre ${c.min} y ${c.max}.`);
        ok = false;
      }
    }
  });

  return ok;
}

/* ── Submit ─────────────────────────────────────────────────────── */
async function onSubmit(e) {
  e.preventDefault();
  if (!validar()) return;

  setLoading(true);
  ocultarResultados();

  const payload = {
    modelo:  document.getElementById("modelo").value,
    ciudad:  document.getElementById("ciudad").value,
    tipo:    document.getElementById("tipo").value,
    area_m2: parseFloat(document.getElementById("area_m2").value),
    alcobas: parseInt(document.getElementById("alcobas").value, 10),
    banos:   parseInt(document.getElementById("banos").value, 10),
    lat:     parseFloat(document.getElementById("lat").value),
    lon:     parseFloat(document.getElementById("lon").value),
  };

  try {
    const resp = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await resp.json();

    if (!resp.ok) {
      throw new Error(data.detail || "Error al calcular la predicción.");
    }

    mostrarResultado(data);
  } catch (err) {
    mostrarErrorPanel(err.message);
  } finally {
    setLoading(false);
  }
}

/* ── Helpers de UI ─────────────────────────────────────────────── */
function setLoading(on) {
  const btn     = document.getElementById("btn-predict");
  const texto   = document.getElementById("btn-text");
  const spinner = document.getElementById("spinner");
  btn.disabled  = on;
  texto.textContent = on ? "Calculando…" : "Estimar Precio";
  spinner.classList.toggle("hidden", !on);
}

function ocultarResultados() {
  document.getElementById("result-placeholder").classList.add("hidden");
  document.getElementById("result-content").classList.add("hidden");
  document.getElementById("result-error").classList.add("hidden");
}

function mostrarResultado(data) {
  ocultarResultados();
  document.getElementById("result-price").textContent =
    formatCOP(data.precio_estimado);

  const area = parseFloat(document.getElementById("area_m2").value) || 1;
  document.getElementById("result-m2").textContent =
    formatCOP(data.precio_estimado / area) + " / m²";

  document.getElementById("result-model").textContent =
    formatNombreModelo(data.modelo_usado);
  document.getElementById("result-content").classList.remove("hidden");
}

function mostrarErrorPanel(msg) {
  ocultarResultados();
  document.getElementById("error-msg").textContent = msg;
  document.getElementById("result-error").classList.remove("hidden");
}

function formatCOP(valor) {
  return new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency: "COP",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.round(valor));
}

/* ── Mapa Leaflet ───────────────────────────────────────────────── */
function initMap() {
  map = L.map("mapa", {
    center: COLOMBIA_CENTER,
    zoom: COLOMBIA_ZOOM,
    zoomControl: true,
  });

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
  }).addTo(map);

  // Clic en el mapa → colocar / mover marcador y geocodificar ciudad
  map.on("click", (e) => {
    colocarMarcador(e.latlng.lat, e.latlng.lng, true);
  });
}

function colocarMarcador(lat, lon, geocodificar = false) {
  const latlng = L.latLng(lat, lon);

  if (marker) {
    marker.setLatLng(latlng);
  } else {
    marker = L.marker(latlng, { draggable: true }).addTo(map);
    marker.on("dragend", (e) => {
      const pos = e.target.getLatLng();
      actualizarInputs(pos.lat, pos.lng);
      geocodificarCiudad(pos.lat, pos.lng);
    });
  }

  actualizarInputs(lat, lon);
  map.panTo(latlng);

  if (geocodificar) geocodificarCiudad(lat, lon);
}

function actualizarInputs(lat, lon) {
  document.getElementById("lat").value = lat.toFixed(6);
  document.getElementById("lon").value = lon.toFixed(6);
  // Limpiar errores de validación al seleccionar en el mapa
  ["lat", "lon"].forEach(id => {
    document.getElementById(id).classList.remove("invalid");
    document.getElementById("err-" + id).textContent = "";
  });
}

function sincronizarDesdeInputs() {
  const lat = parseFloat(document.getElementById("lat").value);
  const lon = parseFloat(document.getElementById("lon").value);
  if (isNaN(lat) || isNaN(lon)) return;
  if (lat >= -4.3 && lat <= 13.0 && lon >= -81.8 && lon <= -66.8) {
    colocarMarcador(lat, lon);
  }
}

/* ── Geocodificación inversa (Nominatim / OSM) ─────────────────── */
function normalizarStr(str) {
  return str
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")  // quitar tildes
    .trim();
}

function matchCiudad(candidatos) {
  // candidatos: strings devueltos por Nominatim (ciudad, municipio, etc.)
  for (const candidato of candidatos) {
    const norm = normalizarStr(candidato);
    for (const ciudad of ciudadesDisponibles) {
      const ciudadNorm = normalizarStr(ciudad);
      // Coincidencia exacta o contenida (cubre "Santiago de Cali" → "cali")
      if (norm === ciudadNorm || norm.includes(ciudadNorm) || ciudadNorm.includes(norm)) {
        return ciudad;  // devuelve el nombre exacto de BigQuery
      }
    }
  }
  return null;
}

async function geocodificarCiudad(lat, lon) {
  const selCiudad = document.getElementById("ciudad");
  const errCiudad = document.getElementById("err-ciudad");

  // Indicar búsqueda en curso
  errCiudad.textContent = "Buscando ciudad…";
  errCiudad.style.color = "var(--slate-500)";

  try {
    const url =
      `https://nominatim.openstreetmap.org/reverse` +
      `?lat=${lat}&lon=${lon}&format=json&accept-language=es`;

    const resp = await fetch(url, {
      headers: { "User-Agent": "PrediCasa/1.0 (demo)" },
    });
    if (!resp.ok) throw new Error("Nominatim error " + resp.status);

    const data = await resp.json();
    const addr = data.address || {};

    // Probar distintos campos en orden de especificidad
    const candidatos = [
      addr.city,
      addr.town,
      addr.municipality,
      addr.county,
      addr.state_district,
    ].filter(Boolean);

    const match = matchCiudad(candidatos);

    if (match) {
      selCiudad.value = match;
      selCiudad.classList.remove("invalid");
      errCiudad.textContent = "";
      errCiudad.style.color = "";
    } else {
      // Ciudad fuera de la base de datos
      selCiudad.value = "";
      selCiudad.classList.add("invalid");
      const lista = ciudadesDisponibles.join(", ");
      errCiudad.textContent =
        `Ciudad no disponible. Ciudades con datos: ${lista}.`;
      errCiudad.style.color = "var(--red-600)";
    }
  } catch (err) {
    // Error de red o cuota — limpiar indicador sin romper la UI
    errCiudad.textContent = "";
    errCiudad.style.color = "";
    console.warn("Geocodificación fallida:", err);
  }
}

/* ── Acciones del panel resultado ──────────────────────────────── */
function resetForm() {
  document.getElementById("predict-form").reset();
  limpiarErrores();
  ocultarResultados();
  document.getElementById("result-placeholder").classList.remove("hidden");
  // Remover marcador y volver al centro de Colombia
  if (marker) {
    marker.remove();
    marker = null;
  }
  if (map) map.setView(COLOMBIA_CENTER, COLOMBIA_ZOOM);
}

function clearError() {
  ocultarResultados();
  document.getElementById("result-placeholder").classList.remove("hidden");
}

/* ── Límites de ciudades disponibles (Nominatim GeoJSON) ─────────── */
function cargarLimitesCiudades(ciudades) {
  ciudades.forEach((ciudad, i) => {
    setTimeout(() => fetchLimiteCiudad(ciudad), i * 350);
  });
}

async function fetchLimiteCiudad(ciudad) {
  try {
    const url =
      `https://nominatim.openstreetmap.org/search` +
      `?q=${encodeURIComponent(ciudad + " Colombia")}` +
      `&format=geojson&polygon_geojson=1&limit=1`;

    const resp = await fetch(url, {
      headers: { "User-Agent": "PrediCasa/1.0 (demo)" },
    });
    if (!resp.ok) return;

    const geojson = await resp.json();
    if (!geojson.features || geojson.features.length === 0) return;

    const feature = geojson.features[0];
    const tipo = feature.geometry?.type;
    if (tipo !== "Polygon" && tipo !== "MultiPolygon") return;

    const capa = L.geoJSON(feature, {
      style: {
        color: "#1d4ed8",
        weight: 1.5,
        fillColor: "#3b82f6",
        fillOpacity: 0.12,
      },
    });

    capa.on("mouseover", () => capa.setStyle({ fillOpacity: 0.28 }));
    capa.on("mouseout",  () => capa.setStyle({ fillOpacity: 0.12 }));

    capa.bindTooltip(ciudad, { sticky: true, className: "ciudad-tooltip" });

    capa.on("click", (e) => {
      L.DomEvent.stopPropagation(e);
      colocarMarcador(e.latlng.lat, e.latlng.lng, false);
      const selCiudad = document.getElementById("ciudad");
      const errCiudad = document.getElementById("err-ciudad");
      selCiudad.value = ciudad;
      selCiudad.classList.remove("invalid");
      errCiudad.textContent = "";
      errCiudad.style.color = "";
    });

    capa.addTo(map);
    capasciudades[ciudad] = capa;
  } catch (err) {
    console.warn(`No se pudo cargar límite de ${ciudad}:`, err);
  }
}
