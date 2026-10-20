// Progressive enhancement only: the site works without JavaScript.
document.querySelectorAll("button.copy[data-copy]").forEach((button) => {
  const target = document.querySelector(button.dataset.copy);
  if (!target || !navigator.clipboard) return;
  button.hidden = false;
  button.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(target.textContent.trim());
      button.textContent = "Copied";
      button.classList.add("done");
    } catch {
      button.textContent = "Press Ctrl+C";
    }
    setTimeout(() => {
      button.textContent = "Copy";
      button.classList.remove("done");
    }, 1800);
  });
});
