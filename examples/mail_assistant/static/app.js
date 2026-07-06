document.addEventListener("click", (event) => {
  const button = event.target.closest(".select-trash-group");
  if (!button) return;
  const group = button.dataset.trashGroup;
  const prefix = button.dataset.trashPrefix;
  const selector = group
    ? `input[name="message_ids"][data-trash-group="${group}"]`
    : `input[name="message_ids"][data-trash-group^="${prefix}"]`;
  const boxes = document.querySelectorAll(selector);
  const select = Array.from(boxes).some((box) => !box.checked);
  boxes.forEach((box) => { box.checked = select; });
  button.textContent = select ? "Clear selection in this group" : "Select all in this group";
});
