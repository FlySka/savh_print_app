const out = document.getElementById("out");
const dayInput = document.getElementById("day");
const themeBtn = document.getElementById("btnTheme");
const techBox = document.getElementById("techBox");
const techSummary = document.getElementById("techSummary");
const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;

function setDefaultDate() {
  const today = new Date();
  const iso = today.toISOString().slice(0, 10);
  dayInput.value = iso;
}

function applyTheme(theme) {
  const body = document.body;
  if (theme === "dark") {
    body.classList.add("theme-dark");
    themeBtn.textContent = "🌞 Modo claro";
  } else {
    body.classList.remove("theme-dark");
    themeBtn.textContent = "🌙 Modo oscuro";
  }
  localStorage.setItem("theme", theme);
}

function show(msg) {
  out.style.display = "block";
  out.innerHTML = msg;
  if (techBox && techSummary) {
    techSummary.textContent = "Detalles técnicos (último job)";
    techBox.open = false;
  }
}

function notify(message, type = "info", timeout = 2600) {
  if (!window.Notiflix) return;
  const opts = { timeout };
  if (type === "success") return Notiflix.Notify.success(message, opts);
  if (type === "error") return Notiflix.Notify.failure(message, opts);
  if (type === "warning") return Notiflix.Notify.warning(message, opts);
  return Notiflix.Notify.info(message, opts);
}

async function enqueueDocs(what) {
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
}

document.getElementById("btnGuides").addEventListener("click", () => enqueueDocs("guides"));
document.getElementById("btnShipping").addEventListener("click", () => enqueueDocs("shipping_list"));

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

document.getElementById("btnUpload").addEventListener("click", async () => {
  const f = document.getElementById("file").files[0];
  if (!f) {
    notify("⚠️ Selecciona un PDF primero.", "error");
    return show("⚠️ Selecciona un PDF primero.");
  }

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
});

setDefaultDate();
const savedTheme = localStorage.getItem("theme");
applyTheme(savedTheme || (prefersDark ? "dark" : "light"));
