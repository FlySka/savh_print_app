const out = document.getElementById("out");
const dayInput = document.getElementById("day");
const themeBtn = document.getElementById("btnTheme");
const btnGuides = document.getElementById("btnGuides");
const btnShipping = document.getElementById("btnShipping");
const btnUpload = document.getElementById("btnUpload");
const egresoSelect = document.getElementById("egresoSelect");
const btnEgreso = document.getElementById("btnEgreso");
const btnUpdateEgreso = document.getElementById("btnUpdateEgreso");
const techBox = document.getElementById("techBox");
const techSummary = document.getElementById("techSummary");
const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
const PRINT_COOLDOWN_SECONDS = 5;
let notifyFallbackReported = false;

function setDefaultDate() {
  const today = new Date();
  const iso = today.toISOString().slice(0, 10);
  dayInput.value = iso;
}

function applyTheme(theme) {
  const body = document.body;
  if (theme === "dark") {
    body.classList.add("theme-dark");
    themeBtn.textContent = "🌞";
  } else {
    body.classList.remove("theme-dark");
    themeBtn.textContent = "🌙";
  }
  localStorage.setItem("theme", theme);
}

function show(msg, { open = false } = {}) {
  out.style.display = "block";
  out.innerHTML = msg;
  if (techBox && techSummary) {
    techSummary.textContent = "Detalles técnicos (último job)";
    techBox.open = open;
  }
}

function initNotifications() {
  const notifier = window.Notiflix && window.Notiflix.Notify;
  if (!notifier) {
    return false;
  }

  notifier.init({
    width: "340px",
    position: "right-top",
    distance: "18px",
    borderRadius: "12px",
    cssAnimationStyle: "from-right",
    pauseOnHover: true,
    clickToClose: true,
    fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif",
    successBackground: "#2f9e44",
    failureBackground: "#d9485f",
    warningBackground: "#f08c00",
    infoBackground: "#1f6cda",
  });

  return true;
}

function notifyFallback(message, type = "info") {
  if (!notifyFallbackReported) {
    console.warn("Notiflix no se cargó; usando fallback visible en el panel técnico.");
    notifyFallbackReported = true;
  }

  const prefix =
    type === "success" ? "✅" :
    type === "error" ? "❌" :
    type === "warning" ? "⚠️" :
    "ℹ️";

  show(`${prefix} ${message}`, { open: true });
}

function notify(message, type = "info", timeout = 2600) {
  const notifier = window.Notiflix && window.Notiflix.Notify;
  if (!notifier) {
    notifyFallback(message, type);
    return;
  }
  const opts = { timeout };
  if (type === "success") return notifier.success(message, opts);
  if (type === "error") return notifier.failure(message, opts);
  if (type === "warning") return notifier.warning(message, opts);
  return notifier.info(message, opts);
}

function setBusy(el, state) {
  if (!el) return;
  if (state) {
    el.dataset.busy = "1";
    el.disabled = true;
    return;
  }
  el.dataset.busy = "0";
  const until = parseInt(el.dataset.cooldownUntil || "0", 10);
  if (!until || Date.now() >= until) {
    el.disabled = false;
  }
}

function startCooldown(el, label = "Botón") {
  if (!el) return false;
  const now = Date.now();
  const until = parseInt(el.dataset.cooldownUntil || "0", 10);
  if (until && now < until) {
    const remaining = Math.ceil((until - now) / 1000);
    notify(`⏳ ${label} bloqueado por ${remaining}s para evitar duplicados.`, "warning");
    return false;
  }

  const ms = (PRINT_COOLDOWN_SECONDS || 10) * 1000;
  const target = now + ms;
  el.dataset.cooldownUntil = String(target);
  el.disabled = true;

  setTimeout(() => {
    const current = parseInt(el.dataset.cooldownUntil || "0", 10);
    if (current === target) {
      el.disabled = false;
      el.dataset.cooldownUntil = "";
    }
  }, ms);

  return true;
}

async function enqueueDocs(what) {
  const btn =
    what === "guides" ? btnGuides :
    what === "shipping_list" ? btnShipping :
    null;
  if (btn) {
    const label = what === "guides" ? "Guías" : "Lista de despachos";
    if (!startCooldown(btn, label)) return;
    setBusy(btn, true);
  }

  notify("⏳ Creando y enviando solicitud...", "info");
  const payload = { what };
  if (dayInput.value) payload.day = dayInput.value;

  const res = await fetch("/api/jobs/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    show(`❌ Error: ${data.detail || "No se pudo crear el job"}`);
    notify("❌ No se pudo crear el job", "error");
    return;
  }
  show(
    `✅ Job creado: <b>#${data.id}</b> (estado: ${data.status})<br/>` +
      `Puedes revisar: <a href="/api/jobs/${data.id}" target="_blank">/api/jobs/${data.id}</a>`
  );
  notify("🖨️ Solicitud procesada, se imprimirá en breve...", "success");
  if (btn) setBusy(btn, false);
}

if (btnGuides) btnGuides.addEventListener("click", () => enqueueDocs("guides"));
if (btnShipping) btnShipping.addEventListener("click", () => enqueueDocs("shipping_list"));

function populateEgresos(options) {
  if (!egresoSelect) return;
  egresoSelect.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.disabled = true;
  placeholder.selected = true;
  placeholder.textContent = "Seleccionar";
  egresoSelect.appendChild(placeholder);

  options.forEach((opt) => {
    const o = document.createElement("option");
    o.value = opt.venta_id;
    o.textContent = opt.label || `${opt.cliente} | ${opt.total_fmt || ""}`;
    egresoSelect.appendChild(o);
  });
}

async function loadEgresos() {
  if (!egresoSelect) return;
  const params = new URLSearchParams();
  if (dayInput.value) params.set("day", dayInput.value);

  setBusy(btnUpdateEgreso, true);
  try {
    const res = await fetch(`/api/egresos${params.toString() ? `?${params.toString()}` : ""}`);
    if (!res.ok) {
      notify("❌ No se pudieron cargar egresos", "error");
      return;
    }
    const data = await res.json();
    populateEgresos(data || []);
    if (!data || data.length === 0) {
      notify("ℹ️ No hay ventas de tipo EGRESO para la fecha.", "warning");
    }
  } catch (err) {
    notify("❌ Error cargando egresos", "error");
  } finally {
    setBusy(btnUpdateEgreso, false);
  }
}

async function enqueueEgreso() {
  if (!egresoSelect || !egresoSelect.value) {
    notify("⚠️ Selecciona una venta EGRESO.", "error");
    return show("⚠️ Selecciona una venta EGRESO.");
  }

  notify("⏳ Creando guía de egreso...", "info");
  if (btnEgreso) {
    if (!startCooldown(btnEgreso, "Guía de egreso")) return;
    setBusy(btnEgreso, true);
  }
  const payload = { what: "egreso", venta_id: egresoSelect.value };
  if (dayInput.value) payload.day = dayInput.value;

  try {
    const res = await fetch("/api/jobs/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      show(`❌ Error: ${data.detail || "No se pudo crear el job"}`);
      notify("❌ No se pudo crear el job", "error");
      return;
    }
    show(
      `✅ Job creado: <b>#${data.id}</b> (estado: ${data.status})<br/>` +
        `Puedes revisar: <a href="/api/jobs/${data.id}" target="_blank">/api/jobs/${data.id}</a>`
    );
    notify("🖨️ Guía de egreso encolada, se imprimirá en breve.", "success");
  } catch (err) {
    notify("❌ Error al crear el job", "error");
  } finally {
    if (btnEgreso) setBusy(btnEgreso, false);
  }
}

themeBtn.addEventListener("click", () => {
  const current = document.body.classList.contains("theme-dark") ? "dark" : "light";
  applyTheme(current === "dark" ? "light" : "dark");
});

const clearUploadBtn = document.getElementById("btnUploadClear");
if (clearUploadBtn) {
  clearUploadBtn.addEventListener("click", () => {
    const fileInput = document.getElementById("file");
    if (fileInput) fileInput.value = "";
    notify("🧹 Selección limpiada.", "info");
  });
}

if (btnUpload) btnUpload.addEventListener("click", async () => {
  if (!startCooldown(btnUpload, "Subir PDF")) return;
  setBusy(btnUpload, true);

  const f = document.getElementById("file").files[0];
  if (!f) {
    notify("⚠️ Selecciona un PDF primero.", "error");
    setBusy(btnUpload, false);
    return show("⚠️ Selecciona un PDF primero.");
  }

  try {
    notify("⏳ Subiendo PDF y enviando solicitud...", "info");
    const form = new FormData();
    form.append("file", f);

    const res = await fetch("/api/print-upload", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) {
      show(`❌ Error: ${data.detail || "No se pudo crear el job"}`);
      notify("❌ No se pudo crear el job", "error");
      return;
    }

    show(
      `✅ Job creado: <b>#${data.id}</b> (estado: ${data.status})<br/>` +
        `Puedes revisar: <a href="/api/jobs/${data.id}" target="_blank">/api/jobs/${data.id}</a>`
    );
    notify("🖨️ Solicitud procesada, se imprimirá en breve.", "success");
  } finally {
    setBusy(btnUpload, false);
  }
});

setDefaultDate();
const savedTheme = localStorage.getItem("theme");
applyTheme(savedTheme || (prefersDark ? "dark" : "light"));
if (!initNotifications()) {
  show("⚠️ No se pudo cargar Notiflix. Las notificaciones usarán el panel técnico.", { open: true });
}
loadEgresos();
if (dayInput) {
  dayInput.addEventListener("change", loadEgresos);
}
if (btnUpdateEgreso) {
  btnUpdateEgreso.addEventListener("click", loadEgresos);
}
if (btnEgreso) {
  btnEgreso.addEventListener("click", enqueueEgreso);
}
