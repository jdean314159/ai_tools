document.addEventListener("click", (event) => {
  const button = event.target.closest(".select-trash-group");
  if (!button) return;
  const group = button.dataset.trashGroup;
  const selector = `input[name="message_ids"][data-trash-group="${group}"]`;
  const boxes = document.querySelectorAll(selector);
  const select = Array.from(boxes).some((box) => !box.checked);
  boxes.forEach((box) => { box.checked = select; });
  button.textContent = select ? "Clear selection in this group" : "Select all in this group";
});

document.addEventListener("change", (event) => {
  const control = event.target.closest(".select-trash-visible");
  if (!control) return;
  const group = control.dataset.trashGroup;
  const boxes = document.querySelectorAll(
    `input[name="message_ids"][data-trash-group="${group}"]`
  );
  boxes.forEach((box) => { box.checked = control.checked; });
});
