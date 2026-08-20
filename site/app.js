async function main() {
  const res = await fetch("catalog.json", { cache: "no-store" });
  if (!res.ok) return;
  const data = await res.json();

  const pill = document.getElementById("version-pill");
  if (pill) {
    pill.textContent = `${data.version}  ·  ${data.tools.length} tools  ·  ${data.recommended.length} recommended extras`;
  }
  const count = document.getElementById("tool-count");
  if (count) count.textContent = String(data.tools.length);

  const root = document.getElementById("cats");
  if (!root) return;
  root.innerHTML = "";
  for (const cat of data.categories) {
    if (String(cat.id).startsWith("homebrew/")) continue;
    const tools = cat.tools || [];
    const row = document.createElement("article");
    row.className = "cat";
    const n = cat.id === "homebrew" ? `${data.recommended.length} recommended` : `${tools.length}`;
    const chips = tools
      .map((t) => `<span>${escapeHtml(t.id)}</span>`)
      .join("");
    row.innerHTML = `
      <div>
        <h3>${escapeHtml(cat.id)}</h3>
        <p class="blurb">${escapeHtml(cat.blurb || "")}</p>
        <span class="count">${escapeHtml(n)}</span>
      </div>
      <div class="chips">${chips || "<span>inventory of this Mac</span>"}</div>
    `;
    root.appendChild(row);
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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
