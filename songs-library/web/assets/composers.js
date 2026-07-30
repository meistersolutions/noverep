const $ = (id) => document.getElementById(id);

/** @type {Array<{ name: string, count: number }>} */
let composers = [];

async function api(path) {
  const res = await fetch(path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    throw new Error(
      typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : res.statusText,
    );
  }
  return res.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function browseUrl(name) {
  return `/?composer=${encodeURIComponent(name)}`;
}

function filteredComposers() {
  const q = ($("composer-filter").value || "").trim().toLowerCase();
  if (!q) return composers;
  return composers.filter((c) => c.name.toLowerCase().includes(q));
}

function renderComposers() {
  const host = $("composers-list");
  const rows = filteredComposers();
  const totalSongs = composers.reduce((sum, c) => sum + c.count, 0);
  $("composer-summary").textContent =
    `${rows.length} composer${rows.length === 1 ? "" : "s"}` +
    (rows.length !== composers.length ? ` of ${composers.length}` : "") +
    ` · ${totalSongs.toLocaleString()} songs`;

  if (!composers.length) {
    host.innerHTML = `<p class="meta">No composers yet. Discover a seed from the home page.</p>`;
    return;
  }
  if (!rows.length) {
    host.innerHTML = `<p class="meta">No composers match that filter.</p>`;
    return;
  }

  host.innerHTML = `
    <div class="table-wrap">
      <table class="composers-table">
        <thead>
          <tr>
            <th scope="col">Composer</th>
            <th scope="col" class="num">Songs</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (c) => `
            <tr>
              <td>
                <a class="composer-link" href="${browseUrl(c.name)}">${escapeHtml(c.name)}</a>
              </td>
              <td class="num">${c.count.toLocaleString()}</td>
            </tr>`,
            )
            .join("")}
        </tbody>
      </table>
    </div>
  `;
}

async function loadComposers() {
  $("status").textContent = "Loading composers…";
  const stats = await api("/api/stats");
  composers = Object.entries(stats.by_composer || {})
    .map(([name, count]) => ({ name, count: Number(count) || 0 }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  $("status").textContent = "";
  renderComposers();
}

$("composer-filter").addEventListener("input", renderComposers);
loadComposers().catch((err) => {
  $("status").textContent = err.message || String(err);
  $("composer-summary").textContent = "";
  $("composers-list").innerHTML = `<p class="meta">Could not load composers.</p>`;
});
