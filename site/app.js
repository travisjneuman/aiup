async function main() {
  const res = await fetch("catalog.json", { cache: "no-store" });
  if (!res.ok) return;
  const data = await res.json();
  const pill = document.getElementById("version-pill");
  if (pill) {
    pill.textContent = `${data.version} · ${data.tools.length} tools · ${data.recommended.length} recommended extras`;
  }
  const root = document.getElementById("cats");
  if (!root) return;
  root.innerHTML = "";
  for (const cat of data.categories) {
    if (String(cat.id).startsWith("homebrew/")) continue;
    const tools = cat.tools || [];
    const card = document.createElement("article");
    card.className = "cat-card";
    const count = cat.id === "homebrew" ? `${data.recommended.length} recommended` : `${tools.length} tools`;
    const names = tools.slice(0, 8).map((t) => t.id).join(" · ");
    card.innerHTML = `
      <h3><span>${cat.emoji || ""}</span> ${cat.id}</h3>
      <p>${cat.blurb || ""}</p>
      <p class="count">${count}</p>
      ${names ? `<p class="names">${names}${tools.length > 8 ? " · …" : ""}</p>` : ""}
    `;
    root.appendChild(card);
  }
}
main().catch(() => {});
