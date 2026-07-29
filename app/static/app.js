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

const browserTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

document.querySelectorAll("[data-time-zone]").forEach((label) => {
    label.textContent = browserTimeZone ? browserTimeZone.replaceAll("_", " ") : "your device time zone";
});

document.querySelectorAll("[data-local-time]").forEach((element) => {
    const timestamp = Date.parse(element.dateTime);
    if (Number.isNaN(timestamp)) {
        return;
    }

    const full = element.dataset.localTime === "full";
    const formatter = new Intl.DateTimeFormat(undefined, {
        year: full ? "numeric" : undefined,
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short",
    });
    element.textContent = formatter.format(timestamp);
    element.title = `Displayed in ${browserTimeZone || "your device time zone"}`;
});

const formatRemainingTime = (milliseconds) => {
    const totalSeconds = Math.max(0, Math.ceil(milliseconds / 1000));
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;

    if (days > 0) {
        return `${days}d ${hours}h ${minutes}m`;
    }
    if (hours > 0) {
        return `${hours}h ${minutes}m ${seconds}s`;
    }
    if (minutes > 0) {
        return `${minutes}m ${seconds}s`;
    }
    return `${seconds}s`;
};

const updateLinkCountdowns = () => {
    const now = Date.now();

    document.querySelectorAll("[data-expires-at]").forEach((countdown) => {
        const expiresAt = Date.parse(countdown.dataset.expiresAt);
        if (Number.isNaN(expiresAt)) {
            countdown.textContent = "Expiry unavailable";
            return;
        }

        const remaining = expiresAt - now;
        if (remaining <= 0) {
            countdown.textContent = "Expired";
            const status = countdown.closest(".file-item")?.querySelector("[data-live-link-status]");
            if (status) {
                status.innerHTML = '<span class="state-badge state-expired"><i class="bi bi-clock-history"></i> Expired</span>';
                status.removeAttribute("data-live-link-status");
            }
            return;
        }

        countdown.textContent = `Expires in ${formatRemainingTime(remaining)}`;
    });

    const activeLinkCount = document.querySelector("[data-active-link-count]");
    if (activeLinkCount) {
        activeLinkCount.textContent = document.querySelectorAll("[data-live-link-status]").length;
    }
};

if (document.querySelector("[data-expires-at]")) {
    updateLinkCountdowns();
    window.setInterval(updateLinkCountdowns, 1000);
}
