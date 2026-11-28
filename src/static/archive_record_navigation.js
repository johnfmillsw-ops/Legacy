(function () {

    "use strict";

    const originalFetch = window.fetch.bind(window);

    const dialogRecords = new WeakMap();

    function recordFromURL(value) {

        let url;

        try {

            url = new URL(
                typeof value === "string"
                    ? value
                    : value.url,
                window.location.origin
            );

        } catch (_) {

            return null;
        }

        if (url.origin !== window.location.origin) {
            return null;
        }

        const patterns = [
            {
                regex: /^\/api\/archive\/memories\/([^/]+)$/,
                type: "memory",
                dialog: "archiveCollectionDialog"
            },
            {
                regex: /^\/api\/archive\/documents\/([^/]+)$/,
                type: "document",
                dialog: "archiveCollectionDialog"
            },
            {
                regex: /^\/api\/journals\/entries\/([^/]+)$/,
                type: "journal",
                dialog: "archiveRecordDialog"
            },
            {
                regex: /^\/voice-journal\/([^/]+)$/,
                type: "voice",
                dialog: "archiveRecordDialog"
            }
        ];

        for (const pattern of patterns) {

            const match = url.pathname.match(pattern.regex);

            if (!match) continue;

            if (["list", "history"].includes(match[1])) {
                continue;
            }

            return {
                id: match[1],
                type: pattern.type,
                dialog: pattern.dialog
            };
        }

        return null;
    }

    function updateLink(record) {

        const dialog = document.getElementById(record.dialog);

        if (!dialog) return;

        dialogRecords.set(dialog, record);

        let link = dialog.querySelector(
            ".archive-full-record-link"
        );

        if (!link) {

            const container = document.createElement("div");

            container.className =
                "archive-full-record-navigation";

            link = document.createElement("a");

            link.className =
                "archive-action archive-full-record-link";

            link.textContent =
                "Open full historical record →";

            container.append(link);

            dialog.append(container);
        }

        link.href =
            "/archive/connections/record/" +
            encodeURIComponent(record.type) +
            "/" +
            record.id;

        link.hidden = false;
    }

    // Observe successful record retrieval without changing
    // the existing Archive request or response behavior.

    window.fetch = async function (resource, options) {

        const response = await originalFetch(
            resource,
            options
        );

        const method = String(
            options?.method ||
            resource?.method ||
            "GET"
        ).toUpperCase();

        if (response.ok && method === "GET") {

            const record = recordFromURL(resource);

            if (record) updateLink(record);
        }

        return response;
    };

})();
