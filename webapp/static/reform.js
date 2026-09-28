document.addEventListener('click', event => {
  if (event.target.closest('.add-row')) {
    event.target.closest('form').querySelector('.rows').append(document.querySelector('#component-template').content.cloneNode(true));
  }
  if (event.target.closest('.remove-row')) (event.target.closest('.component-entry') || event.target.closest('.component-row')).remove();
});
document.querySelectorAll('.retire-form').forEach(form => form.addEventListener('submit', event => {
  if (!confirm('Siūlyti nutraukti šio produkto naudojimą? Prieš pateikiant bus patikrinti susiję BOM.')) event.preventDefault();
}));
document.querySelectorAll('.discard-form').forEach(form => form.addEventListener('submit', event => {
  if (!confirm('Atšaukti visus šio juodraščio pakeitimus?')) event.preventDefault();
}));
