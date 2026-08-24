(() => {
  const form = document.querySelector(".chunked-upload");
  if (!form) return;

  const input = form.querySelector('input[type="file"]');
  const button = form.querySelector('button[type="submit"]');
  const progressBox = form.querySelector(".upload-progress");
  const progress = progressBox.querySelector("progress");
  const percent = progressBox.querySelector("span");
  const message = form.querySelector(".upload-message");
  const chunkSize = 4 * 1024 * 1024;

  const responseJson = async (response) => {
    if (response.ok) return response.json();
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  };

  const sendChunk = async (url, chunk, offset) => {
    let lastError;
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      try {
        return await responseJson(await fetch(url, {
          method: "PUT",
          headers: {"Content-Type": "application/octet-stream", "Upload-Offset": String(offset)},
          body: chunk,
        }));
      } catch (error) {
        lastError = error;
        if (attempt < 3) await new Promise((resolve) => setTimeout(resolve, 500 * attempt));
      }
    }
    throw lastError;
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = input.files[0];
    if (!file) return;
    button.disabled = true;
    progressBox.hidden = false;
    message.textContent = "Ruošiamas įkėlimas…";

    try {
      const started = await responseJson(await fetch(form.dataset.startUrl, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({filename: file.name, size: file.size}),
      }));
      let offset = started.offset;
      while (offset < file.size) {
        const chunk = file.slice(offset, Math.min(offset + chunkSize, file.size));
        const result = await sendChunk(
          `${form.dataset.startUrl}/${started.upload_id}`, chunk, offset,
        );
        offset = result.offset;
        const value = Math.round((offset / file.size) * 100);
        progress.value = value;
        percent.textContent = `${value}%`;
        message.textContent = `Įkelta ${offset.toLocaleString("lt-LT")} iš ${file.size.toLocaleString("lt-LT")} baitų`;
      }
      await responseJson(await fetch(`${form.dataset.startUrl}/${started.upload_id}/complete`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: "{}",
      }));
      message.textContent = "Failas sėkmingai įkeltas.";
      window.location.reload();
    } catch (error) {
      message.textContent = `Įkelti nepavyko: ${error.message}`;
      button.disabled = false;
    }
  });
})();
