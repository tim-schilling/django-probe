document.querySelectorAll("[data-token-toggle]").forEach((button) => {
  const code = document.getElementById(button.dataset.tokenToggle);
  if (!code) return;

  const value = code.textContent;
  const mask = "•".repeat(value.length);
  const label = button.querySelector("[data-token-toggle-label]");
  code.textContent = mask;

  button.addEventListener("click", () => {
    const hidden = button.getAttribute("aria-pressed") === "false";
    code.textContent = hidden ? value : mask;
    button.setAttribute("aria-pressed", String(hidden));
    if (label) label.textContent = hidden ? "Hide token" : "Show token";
  });
});
