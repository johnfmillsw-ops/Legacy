document.addEventListener("DOMContentLoaded", () => {

    const panel = document.getElementById(
        "archivePhotoRelationships"
    );

    if (!panel) return;

    const list = document.getElementById(
        "archiveRelationshipList"
    );

    const discover = document.getElementById(
        "archiveDiscoverRelationships"
    );

    const message = document.getElementById(
        "archiveRelationshipMessage"
    );

    const csrf = document.querySelector(
        '#archivePhotoForm input[name="_csrf_token"]'
    )?.value;

    let assetId = null;
    let version = 0;

    function node(tag, text, className) {

        const element = document.createElement(tag);

        if (text != null) element.textContent = text;
        if (className) element.className = className;

        return element;
    }

    function button(label, callback) {

        const element = node(
            "button",
            label,
            "archive-action"
        );

        element.type = "button";

        element.addEventListener("click", callback);

        return element;
    }

    async function requestJSON(url, fields = null) {

        const options = {
            credentials: "same-origin",
            cache: "no-store"
        };

        if (fields !== null) {

            const body = new FormData();

            if (!csrf) {
                throw new Error(
                    "Session token unavailable. Refresh the Archive."
                );
            }

            body.append("_csrf_token", csrf);

            for (const [key, value] of Object.entries(fields)) {
                body.append(key, value);
            }

            options.method = "POST";
            options.body = body;
        }

        const response = await fetch(url, options);

        let result;

        try {

            result = await response.json();

        } catch (_) {

            throw new Error(
                "Relationship request failed (HTTP " +
                response.status + ")."
            );
        }

        if (!response.ok) {

            throw new Error(
                result.error || "Unable to retrieve connections."
            );
        }

        return result;
    }

    async function changeDecision(record, status) {

        const current = version;

        try {

            await requestJSON(
                "/api/archive/relationships/decision/" +
                encodeURIComponent(record.id),
                {status}
            );

            if (current !== version) return;

            await loadRelationships(false);

        } catch (error) {

            if (current !== version) return;

            message.textContent = error.message;
        }
    }

    function render(records) {

        list.replaceChildren();

        if (!records.length) {

            list.append(
                node(
                    "p",
                    "No connections found yet.",
                    "archive-note"
                )
            );

            return;
        }

        for (const record of records) {

            const item = node(
                "article",
                null,
                "archive-relationship"
            );

            const confirmed =
                record.status === "confirmed";

            const typeNames = {
                memory: "Memory",
                journal: "Journal entry",
                document: "Historical document",
                voice: "Oral history"
            };

            item.append(
                node(
                    "span",
                    confirmed
                        ? "CONFIRMED CONNECTION"
                        : "SUGGESTED CONNECTION",
                    "archive-eyebrow"
                ),
                node(
                    "h3",
                    String(record.title || "Untitled record")
                        .replaceAll("_", " ")
                ),
                node(
                    "p",
                    [
                        typeNames[record.target_type],
                        record.event_date
                    ].filter(Boolean).join(" · "),
                    "archive-note"
                ),
                node("p", record.preview || "")
            );

            const reasons = node(
                "details",
                null,
                "archive-match-reasons"
            );

            reasons.append(
                node("summary", "Why these records are connected")
            );

            for (const reason of record.match_reasons || []) {

                reasons.append(
                    node("p", reason, "archive-note")
                );
            }

            item.append(reasons);

            const recordLink = node(
                "a",
                "Read historical record →",
                "archive-action archive-connected-record-link"
            );

            recordLink.href =
                "/archive/connections/record/" +
                encodeURIComponent(record.target_type) +
                "/" +
                encodeURIComponent(record.target_id);

            item.append(recordLink);


            const controls = node(
                "div",
                null,
                "archive-relationship-actions"
            );

            if (!confirmed) {

                controls.append(
                    button(
                        "Confirm connection",
                        () => changeDecision(record, "confirmed")
                    )
                );
            }

            controls.append(
                button(
                    confirmed
                        ? "Remove connection"
                        : "Not related",
                    () => changeDecision(record, "rejected")
                )
            );

            item.append(controls);

            list.append(item);
        }
    }

    async function loadRelationships(scan) {

        if (!assetId) return;

        const current = ++version;

        discover.disabled = true;

        message.textContent = scan
            ? "Searching your historical collection..."
            : "Retrieving connections...";

        try {

            const base =
                "/api/archive/relationships/" +
                encodeURIComponent(assetId);

            const result = await requestJSON(
                scan ? base + "/discover" : base,
                scan ? {} : null
            );

            if (current !== version) return;

            render(result.relationships || []);

            message.textContent = scan
                ? "Collection search complete."
                : "";

        } catch (error) {

            if (current !== version) return;

            message.textContent = error.message;

        } finally {

            if (current === version) {
                discover.disabled = false;
            }
        }
    }

    discover.addEventListener("click", event => {

        event.preventDefault();

        const photoDialog = document.getElementById(
            "archivePhotoDialog"
        );

        assetId = photoDialog?.dataset.assetId || assetId;

        if (!assetId) {

            message.textContent =
                "No photograph selected. Close and reopen the photograph.";

            return;
        }

        loadRelationships(true);
    });

    document.addEventListener(
        "archive:photo-opened",
        event => {

            assetId = event.detail.id;

            const readingRoom = document.getElementById(
                "archivePhotoReadingRoom"
            );

            if (readingRoom) {

                readingRoom.href =
                    "/archive/connections/photo/" +
                    encodeURIComponent(assetId);

                readingRoom.hidden = false;
            }


            list.replaceChildren();

            loadRelationships(false);
        }
    );

});
