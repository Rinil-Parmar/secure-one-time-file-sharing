"use strict";

document.querySelectorAll("[data-copy-value]").forEach((button) => {
    button.addEventListener("click", async () => {
        try {
            await navigator.clipboard.writeText(button.dataset.copyValue);
            button.classList.add("copied");
            button.querySelector("span").textContent = "Copied";
            button.querySelector("i").className = "bi bi-check2";
            window.setTimeout(() => {
                button.classList.remove("copied");
                button.querySelector("span").textContent = "Copy link";
                button.querySelector("i").className = "bi bi-copy";
            }, 2200);
        } catch {
            const input = button.closest(".copy-field").querySelector("input");
            input.select();
            document.execCommand("copy");
        }
    });
});

document.querySelectorAll("[data-file-input]").forEach((input) => {
    input.addEventListener("change", () => {
        const label = input.closest(".upload-dropzone").querySelector("[data-file-label]");
        label.textContent = input.files.length ? input.files[0].name : "Choose a file or drag it here";
    });
});

document.querySelectorAll("[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
        if (!window.confirm(form.dataset.confirm)) {
            event.preventDefault();
        }
    });
});
