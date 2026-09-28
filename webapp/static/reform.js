document.addEventListener('click', event => {
  if (event.target.closest('.add-row')) {
    event.target.closest('form').querySelector('.rows').append(document.querySelector('#component-template').content.cloneNode(true));
  }
  if (event.target.closest('.remove-row')) (event.target.closest('.component-entry') || event.target.closest('.component-row')).remove();
});
document.querySelectorAll('.retire-form').forEach(form => form.addEventListener('submit', event => {
  if (!confirm('Propose retiring this product? Related BOMs will be checked before submission.')) event.preventDefault();
}));
document.querySelectorAll('.discard-form').forEach(form => form.addEventListener('submit', event => {
  if (!confirm('Discard all changes in this draft?')) event.preventDefault();
}));
