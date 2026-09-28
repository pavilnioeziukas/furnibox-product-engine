document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('.tab-panel').forEach(panel => { panel.hidden = panel.id !== button.dataset.tab; });
  document.querySelectorAll('[data-tab]').forEach(tab => { tab.classList.toggle('active', tab === button); tab.setAttribute('aria-selected', String(tab === button)); });
}));
document.querySelector('#search')?.addEventListener('input', event => {
  const query = event.target.value.toLocaleLowerCase().trim();
  document.querySelectorAll('.product').forEach(product => { product.hidden = !product.dataset.search.includes(query); });
});
for (const name of ['product', 'bom']) document.querySelector(`#new-${name}-button`)?.addEventListener('click', () => {
  const editor = document.querySelector(`#new-${name}`); editor.open = true; editor.scrollIntoView({behavior: 'smooth'}); editor.querySelector('input:not([type=hidden]),select').focus();
});
document.addEventListener('click', event => {
  if (event.target.closest('.add-row')) {
    event.target.closest('form').querySelector('.rows').append(document.querySelector('#component-template').content.cloneNode(true));
  }
  if (event.target.closest('.remove-row')) event.target.closest('.component-row').remove();
});
document.querySelectorAll('.retire-form').forEach(form => form.addEventListener('submit', event => {
  if (!confirm('Siūlyti nutraukti šio produkto naudojimą? Prieš pateikiant bus patikrinti susiję BOM.')) event.preventDefault();
}));
document.querySelectorAll('.discard-form').forEach(form => form.addEventListener('submit', event => {
  if (!confirm('Atšaukti visus šio juodraščio pakeitimus?')) event.preventDefault();
}));
