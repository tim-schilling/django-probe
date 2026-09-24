document.querySelectorAll("[data-dialog-open]").forEach((button) => {
  button.addEventListener("click", () => {
    document.getElementById(button.dataset.dialogOpen).showModal();
  });
});
