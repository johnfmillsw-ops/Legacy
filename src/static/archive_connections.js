document.addEventListener("DOMContentLoaded", () => {

    const form = document.getElementById(
        "archiveConnectionForm"
    );

    if (!form) return;

    const search = document.getElementById(
        "archiveConnectionSearch"
    );

    const type = document.getElementById(
        "archiveConnectionType"
    );

    const results = document.getElementById(
        "archiveConnectionResults"
    );

    const message = document.getElementById(
        "archiveConnectionMessage"
    );

    const csrf = form.querySelector(
        'input[name="_csrf_token"]'
    ).value;

    let version = 0;

    function element(tag, text, className) {

        const node = document.createElement(tag);

        if (text != null) node.textContent = text;
        if (className) node.className = className;

        return node;
    }

    async function requestJSON(url, fields = null) {

        const options = {
            credentials: "same-origin",
            cache: "no-store"
        };

        if (fields !== null) {

            const body = new FormData();

            body.append("_csrf_token", csrf);

            for (const [key, value] of Object.entries(fields)) {
                body.append(key, value);
            }

            options.method = "POST";
            options.body = body;
        }

        const response = await fetch(url, options);

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Unable to complete request."
            );
        }

        return data;
    }

    function renderRecords(records, targetType) {

        results.replaceChildren();

        if (!records.length) {

            message.textContent =
                "No matching historical records found.";

            return;
        }

        message.textContent =
            `${records.length} matching records`;

        for (const record of records) {

            const article = element(
                "article",
                null,
                "archive-connected-record"
            );

            article.append(
                element(
                    "h3",
                    String(record.title || "Untitled record")
                        .replaceAll("_", " ")
                ),
                element(
                    "p",
                    record.event_date || "",
                    "archive-note"
                ),
                element("p", record.preview || "")
            );

            const button = element(
                "button",
                "Connect this record",
                "archive-action"
            );

            button.type = "button";

            button.addEventListener("click", async () => {

                button.disabled = true;

                try {

                    await requestJSON(
                        "/archive/connections/link",
                        {
                            asset_id: form.dataset.assetId,
                            target_type: targetType,
                            target_id: record.id
                        }
                    );

                    window.location.reload();

                } catch (error) {

                    message.textContent = error.message;
                    button.disabled = false;
                }
            });

            article.append(button);
            results.append(article);
        }
    }

    form.addEventListener("submit", async event => {

        event.preventDefault();

        const current = ++version;
        const selectedType = type.value;

        results.replaceChildren();

        message.textContent = "Searching the collection...";

        try {

            const params = new URLSearchParams({
                q: search.value,
                type: selectedType
            });

            const data = await requestJSON(
                "/archive/connections/search?" +
                params.toString()
            );

            if (current !== version) return;

            renderRecords(
                data.records || [],
                selectedType
            );

        } catch (error) {

            if (current !== version) return;

            message.textContent = error.message;
        }
    });

    type.addEventListener("change", () => {
        version++;
        results.replaceChildren();
        message.textContent = "";
    });

    document.querySelectorAll(
        "[data-remove-connection]"
    ).forEach(button => {

        button.addEventListener("click", async () => {

            if (!window.confirm(
                "Remove this connection? Both original records will be preserved."
            )) return;

            button.disabled = true;

            try {

                await requestJSON(
                    "/archive/connections/unlink",
                    {
                        relationship_id:
                            button.dataset.removeConnection
                    }
                );

                window.location.reload();

            } catch (error) {

                window.alert(error.message);
                button.disabled = false;
            }
        });
    });

});
