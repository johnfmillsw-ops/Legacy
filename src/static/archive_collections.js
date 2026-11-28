document.addEventListener("DOMContentLoaded", () => {

    const documentsContainer =
        document.getElementById("archiveDocuments");

    const memoriesContainer =
        document.getElementById("archiveMemories");

    if (!documentsContainer || !memoriesContainer) return;

    const documentSearch =
        document.getElementById("archiveDocumentSearch");

    const memorySearch =
        document.getElementById("archiveMemorySearch");

    const memoryCategory =
        document.getElementById("archiveMemoryCategory");

    const dialog =
        document.getElementById("archiveCollectionDialog");

    const dialogTitle =
        document.getElementById("archiveCollectionTitle");

    const dialogMeta =
        document.getElementById("archiveCollectionMeta");

    const dialogBody =
        document.getElementById("archiveCollectionBody");

    const dialogRelated =
        document.getElementById("archiveCollectionRelated");

    let documents = [];
    let memories = [];
    let requestVersion = 0;

    function node(tag, text, className) {
        const element = document.createElement(tag);

        if (text != null) {
            element.textContent = text;
        }

        if (className) {
            element.className = className;
        }

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

    function humanize(value) {
        return String(value || "Uncategorized")
            .replaceAll("_", " ");
    }

    function formatDate(value) {

        if (!value) return "Date not recorded";

        const text = String(value);

        if (/^\d{4}$/.test(text)) return text;

        if (/^\d{4}-\d{2}$/.test(text)) return text;

        if (!/^\d{4}-\d{2}-\d{2}/.test(text)) {
            return text;
        }

        const date = new Date(
            /^\d{4}-\d{2}-\d{2}$/.test(text)
                ? `${text}T00:00:00`
                : text
        );

        return Number.isNaN(date.getTime())
            ? text
            : date.toLocaleDateString(undefined, {
                year: "numeric",
                month: "long",
                day: "numeric"
            });
    }

    async function getJSON(url) {

        const response = await fetch(url, {
            credentials: "same-origin",
            cache: "no-store"
        });

        if (!response.ok) {
            throw new Error(
                `Unable to retrieve record (${response.status}).`
            );
        }

        return response.json();
    }

    function prepareDialog(title) {

        const version = ++requestVersion;

        dialogTitle.textContent = title;
        dialogMeta.textContent = "";
        dialogBody.textContent = "Loading historical record...";
        dialogRelated.replaceChildren();

        if (!dialog.open) {
            dialog.showModal();
        }

        return version;
    }

    async function openDocument(id) {

        const version = prepareDialog("Historical document");

        try {

            const result = await getJSON(
                `/api/archive/documents/${encodeURIComponent(id)}`
            );

            if (version !== requestVersion) return;

            const record = result.document;

            dialogTitle.textContent =
                record.title || "Untitled document";

            dialogMeta.textContent = [
                humanize(record.source_type),
                `Preserved ${formatDate(record.created_utc)}`
            ].join(" · ");

            dialogBody.textContent =
                record.original_text ||
                "No document text is available.";

            const related = result.memories || [];

            if (related.length) {

                dialogRelated.append(
                    node("h3", "Memories from this document"),
                    node(
                        "p",
                        `${related.length} connected memories`,
                        "archive-note"
                    )
                );

                for (const memory of related) {

                    const card = node(
                        "article",
                        null,
                        "archive-record"
                    );

                    card.append(
                        node(
                            "span",
                            humanize(memory.category),
                            "archive-eyebrow"
                        ),
                        node("p", memory.preview || ""),
                        button(
                            "Explore memory",
                            () => openMemory(memory.id)
                        )
                    );

                    dialogRelated.append(card);
                }
            }

        } catch (error) {

            if (version !== requestVersion) return;

            dialogBody.textContent = error.message;
        }
    }

    async function openMemory(id) {

        const version = prepareDialog("Personal memory");

        try {

            const result = await getJSON(
                `/api/archive/memories/${encodeURIComponent(id)}`
            );

            if (version !== requestVersion) return;

            const memory = result.memory;

            dialogTitle.textContent =
                humanize(memory.category);

            dialogMeta.textContent = [
                `Event: ${formatDate(memory.event_date)}`,
                `Status: ${humanize(memory.status)}`,
                humanize(memory.interpretation_type)
            ].join(" · ");

            dialogBody.textContent =
                memory.memory_text || "";

            if (memory.source_excerpt) {

                dialogRelated.append(
                    node("h3", "Original source excerpt"),
                    node(
                        "blockquote",
                        memory.source_excerpt,
                        "archive-source-excerpt"
                    )
                );
            }

            if (memory.document_id) {

                dialogRelated.append(
                    node("h3", "Source document"),
                    button(
                        memory.document_title || "Open source",
                        () => openDocument(memory.document_id)
                    )
                );
            }

        } catch (error) {

            if (version !== requestVersion) return;

            dialogBody.textContent = error.message;
        }
    }

    function renderDocuments() {

        const query =
            documentSearch.value.trim().toLowerCase();

        const filtered = documents.filter(record =>
            [
                record.title,
                record.source_type,
                record.preview
            ].join(" ").toLowerCase().includes(query)
        );

        documentsContainer.replaceChildren();

        document.getElementById("archiveDocumentCount")
            .textContent =
                `${filtered.length} of ${documents.length} documents`;

        if (!filtered.length) {
            documentsContainer.append(
                node("p", "No matching documents.")
            );
            return;
        }

        for (const record of filtered) {

            const card = node(
                "article",
                null,
                "archive-record"
            );

            card.append(
                node(
                    "span",
                    humanize(record.source_type),
                    "archive-eyebrow"
                ),
                node("h3", record.title || "Untitled document"),
                node(
                    "p",
                    formatDate(record.created_utc),
                    "archive-note"
                ),
                node("p", record.preview || ""),
                button(
                    "Read document",
                    () => openDocument(record.id)
                )
            );

            documentsContainer.append(card);
        }
    }

    function renderMemories() {

        const query =
            memorySearch.value.trim().toLowerCase();

        const category = memoryCategory.value;

        const filtered = memories.filter(record => {

            if (category && record.category !== category) {
                return false;
            }

            return [
                record.preview,
                record.category,
                record.event_date,
                record.status
            ].join(" ").toLowerCase().includes(query);
        });

        memoriesContainer.replaceChildren();

        document.getElementById("archiveMemoryCount")
            .textContent =
                `${filtered.length} of ${memories.length} memories`;

        if (!filtered.length) {
            memoriesContainer.append(
                node("p", "No matching memories.")
            );
            return;
        }

        for (const record of filtered) {

            const card = node(
                "article",
                null,
                "archive-record"
            );

            card.append(
                node(
                    "span",
                    humanize(record.category),
                    "archive-eyebrow"
                ),
                node("p", record.preview || ""),
                node(
                    "p",
                    [
                        formatDate(record.event_date),
                        humanize(record.status)
                    ].join(" · "),
                    "archive-note"
                ),
                button(
                    "Explore memory",
                    () => openMemory(record.id)
                )
            );

            memoriesContainer.append(card);
        }
    }

    async function loadCollections() {

        try {

            const result = await getJSON(
                "/api/archive/collections"
            );

            documents = result.documents || [];
            memories = result.memories || [];

            const categories = [
                ...new Set(
                    memories.map(record => record.category)
                        .filter(Boolean)
                )
            ].sort();

            for (const category of categories) {

                const option = node(
                    "option",
                    humanize(category)
                );

                option.value = category;

                memoryCategory.append(option);
            }

            renderDocuments();
            renderMemories();

        } catch (error) {

            documentsContainer.textContent = error.message;
            memoriesContainer.textContent = error.message;
        }
    }

    documentSearch.addEventListener(
        "input",
        renderDocuments
    );

    memorySearch.addEventListener(
        "input",
        renderMemories
    );

    memoryCategory.addEventListener(
        "change",
        renderMemories
    );

    document.getElementById("archiveCloseCollection")
        .addEventListener("click", () => dialog.close());

    dialog.addEventListener("close", () => {
        requestVersion++;
    });

    loadCollections();

});
