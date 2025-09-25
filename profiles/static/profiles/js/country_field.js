const countrySelect = document.getElementById('id_primary_country');

function setColor(element) {
    if (!element.value) {
        element.style.color = '#aab7c4';
    } else {
        element.style.color = '#000';
    }
}

setColor(countrySelect);

countrySelect.addEventListener('change', function() {
    setColor(this);
});