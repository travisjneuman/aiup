function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function main() {
  const root = document.getElementById("cats");
  const pill = document.getElementById("version-pill");
  let data;
  try {
    const res = await fetch("catalog.json", { cache: "no-store" });
    if (!res.ok) throw new Error("catalog missing");
    data = await res.json();
  } catch {
    if (root) {
      root.innerHTML = "<p class=\"note\">Catalog could not be loaded. Open this page from the deployed site, or run scripts/sync-public-docs.</p>";
    }
    return;
  }

  if (pill) {
    pill.textContent = `${data.version} · ${data.tools.length} tools · click a row to open it`;
  }
  if (!root) return;
  root.innerHTML = "";

  for (const cat of data.categories) {
    if (String(cat.id).startsWith("homebrew/")) continue;
    const tools = cat.tools || [];
    const n = cat.id === "homebrew"
      ? `${(data.recommended || []).length} recommended`
      : String(tools.length);
    const details = document.createElement("details");
    details.className = "cat";
    const chips = tools.length
      ? tools.map((t) => {
          const href = t.docs ? escapeHtml(t.docs) : "";
          const id = escapeHtml(t.id);
          return href
            ? `<a href="${href}">${id}</a>`
            : `<span>${id}</span>`;
        }).join("")
      : "<span>inventory of this Mac</span>";
    details.innerHTML = `
      <summary>
        <span class="id">${escapeHtml(cat.id)}</span>
        <span class="blurb">${escapeHtml(cat.blurb || "")}</span>
        <span class="n">${escapeHtml(n)}</span>
      </summary>
      <div class="chips">${chips}</div>
    `;
    root.appendChild(details);
  }
}

const copyBtn = document.getElementById("copy-install");
const block = document.getElementById("install-block");
if (copyBtn && block) {
  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(block.innerText);
      copyBtn.textContent = "Copied";
      setTimeout(() => { copyBtn.textContent = "Copy"; }, 1400);
    } catch {
      copyBtn.textContent = "Select the text";
    }
  });
}

main().catch(() => {});
