function initializePhotoRelationships(dialog) {

    const panel = document.getElementById(
        "archivePhotoRelationships"
    );

    if (!panel) throw new Error("Missing photograph relationship panel.");

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

    return function openRelationships(id) {
        assetId = id;
        const readingRoom = document.getElementById("archivePhotoReadingRoom");
        if (readingRoom) {
            readingRoom.href = "/archive/connections/photo/" + encodeURIComponent(id);
            readingRoom.hidden = false;
        }
        list.replaceChildren();
        loadRelationships(false);
    };
}

document.addEventListener("DOMContentLoaded", () => {

    const gallery = document.getElementById("archivePhotoGallery");

    if (!gallery) return;

    const form = document.getElementById("archivePhotoForm");
    const message = document.getElementById("archivePhotoMessage");
    const search = document.getElementById("archivePhotoSearch");
    const sort = document.getElementById("archivePhotoSort");
    const count = document.getElementById("archivePhotoCount");

    const dialog = document.getElementById("archivePhotoDialog");
    const dialogTitle = document.getElementById("archivePhotoTitle");
    const dialogImage = document.getElementById("archivePhotoImage");
    const dialogDescription =
        document.getElementById("archivePhotoDescription");
    const dialogMetadata =
        document.getElementById("archivePhotoMetadata");
    const download =
        document.getElementById("archivePhotoDownload");

    let openRelationships;
    try {
        openRelationships = initializePhotoRelationships(dialog);
    } catch (error) {
        const status = document.getElementById("archiveRelationshipMessage");
        if (status) status.textContent = "Connections unavailable: " + error.message;
        console.error(error);
    }

    let assets = [];
    const editForm = document.getElementById("archivePhotoEditForm");
    const manage = document.getElementById("archivePhotoManage");
    const manageMessage = document.getElementById("archivePhotoManageMessage");
    const deleteButton = document.getElementById("archivePhotoDelete");
    let managing = false;
    async function managePhoto(action) {
        if (managing) return;
        const id = dialog.dataset.assetId;
        if (!id) return;
        if (action === "delete" && !window.confirm("Permanently delete this photograph and its connections? Other historical records will remain.")) return;
        managing = true;
        const controls = [...editForm.querySelectorAll("button")];
        controls.forEach(button => button.disabled = true);
        manageMessage.textContent = action === "edit" ? "Saving changes…" : "Deleting photograph…";
        try {
            const response = await fetch("/api/archive/gallery/" + encodeURIComponent(id) + "/" + action, {
                method: "POST", credentials: "same-origin", body: new FormData(editForm)
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || "Request failed.");
            if (action === "delete") {
                assets = assets.filter(asset => asset.id !== id);
                if (dialog.dataset.assetId === id) dialog.close();
                message.textContent = "Photograph deleted.";
            } else {
                assets = assets.map(asset => asset.id === id ? result.asset : asset);
                if (dialog.open && dialog.dataset.assetId === id) {
                    openPhoto(result.asset);
                    manageMessage.textContent = "Changes saved. Discover connections again to refresh suggestions.";
                }
            }
            renderGallery();
        } catch (error) {
            manageMessage.textContent = error.message;
        } finally {
            managing = false;
            controls.forEach(button => button.disabled = false);
        }
    }
    editForm.addEventListener("submit", event => { event.preventDefault(); managePhoto("edit"); });
    deleteButton.addEventListener("click", () => managePhoto("delete"));


    function node(tag, text, className) {

        const element = document.createElement(tag);

        if (text != null) element.textContent = text;
        if (className) element.className = className;

        return element;
    }

    function openPhoto(asset) {

        dialogTitle.textContent = asset.title;
        manage.open = false;
        manageMessage.textContent = "";
        for (const key of ["title", "description", "event_date", "location", "people"]) {
            editForm.elements.namedItem(key).value = asset[key] || "";
        }


        dialogImage.src = asset.image_url;
        dialogImage.alt = asset.title;

        dialogDescription.textContent =
            asset.description || "No description recorded.";

        dialogMetadata.replaceChildren();

        const details = [
            ["Event date", asset.event_date],
            ["Location", asset.location],
            ["People", asset.people],
            ["Original filename", asset.original_filename],
            ["Preserved", new Date(asset.created_utc)
                .toLocaleDateString()]
        ];

        for (const [label, value] of details) {

            if (!value) continue;

            const row = node("div", null, "archive-photo-detail");

            row.append(
                node("strong", label),
                node("span", value)
            );

            dialogMetadata.append(row);
        }

        download.href = asset.image_url + "?download=1";

        dialog.dataset.assetId = asset.id;

        if (!dialog.open) dialog.showModal();

        if (openRelationships) openRelationships(asset.id);

    }

    function renderGallery() {

        const query = search.value.trim().toLowerCase();

        const filtered = assets.filter(asset =>
            [
                asset.title,
                asset.description,
                asset.location,
                asset.people,
                asset.event_date
            ].join(" ").toLowerCase().includes(query)
        );

        filtered.sort((a, b) => {

            if (sort.value === "title") {
                return a.title.localeCompare(b.title);
            }

            if (sort.value === "event") {

                if (!a.event_date) return b.event_date ? 1 : 0;
                if (!b.event_date) return -1;

                return a.event_date.localeCompare(b.event_date);
            }

            return new Date(b.created_utc) -
                   new Date(a.created_utc);
        });

        gallery.replaceChildren();

        count.textContent =
            `${filtered.length} of ${assets.length} photographs`;

        if (!filtered.length) {

            gallery.append(
                node(
                    "p",
                    query
                        ? "No matching photographs."
                        : "Your photographic collection begins here."
                )
            );

            return;
        }

        for (const asset of filtered) {

            const card = node(
                "button",
                null,
                "archive-photo-card"
            );

            card.type = "button";

            const image = node("img");

            image.src = asset.thumbnail_url;
            image.alt = asset.title;
            image.loading = "lazy";
            image.decoding = "async";

            const caption = node(
                "div",
                null,
                "archive-photo-caption"
            );

            caption.append(
                node("h3", asset.title),
                node(
                    "p",
                    [
                        asset.event_date,
                        asset.location
                    ].filter(Boolean).join(" · ") ||
                    "Date and location not recorded"
                )
            );

            card.append(image, caption);

            card.addEventListener(
                "click",
                () => openPhoto(asset)
            );

            gallery.append(card);
        }
    }

    async function loadGallery() {

        const response = await fetch(
            "/api/archive/gallery",
            {
                credentials: "same-origin",
                cache: "no-store"
            }
        );

        if (!response.ok) {
            throw new Error("Unable to retrieve photographs.");
        }

        const result = await response.json();

        assets = result.assets || [];

        renderGallery();
    }

    form.addEventListener("submit", async event => {

        event.preventDefault();

        const submit = form.querySelector(
            'button[type="submit"]'
        );

        submit.disabled = true;
        message.textContent = "Preserving photograph...";

        try {

            const response = await fetch(
                "/api/archive/gallery",
                {
                    method: "POST",
                    credentials: "same-origin",
                    body: new FormData(form)
                }
            );

            const result = await response.json();

            if (!response.ok) {
                throw new Error(
                    result.error || "Photograph upload failed."
                );
            }

            form.reset();

            message.textContent =
                "Photograph successfully preserved.";

            try {
                await loadGallery();
            } catch {
                message.textContent =
                    "Photograph saved. Refresh to view it.";
            }

        } catch (error) {

            message.textContent = error.message;

        } finally {

            submit.disabled = false;
        }
    });

    search.addEventListener("input", renderGallery);
    sort.addEventListener("change", renderGallery);

    document.getElementById("archiveClosePhoto")
        .addEventListener("click", () => dialog.close());

    dialog.addEventListener("close", () => {
        dialogImage.removeAttribute("src");
    });

    loadGallery().catch(error => {
        gallery.textContent = error.message;
    });

});
