
document.addEventListener("DOMContentLoaded", () => {

    const dialog = document.getElementById(
        "journalEditor"
    );

    if (!dialog) {
        return;
    }

    const byId = id => document.getElementById(id);

    const form = byId("journalEditorForm");
    const book = byId("editorBook");
    const title = byId("editorTitle");
    const content = byId("editorContent");

    const saveStatus = byId("editorSaveStatus");
    const errorMessage = byId("editorError");

    const previousButton = byId("editorPrevious");
    const nextButton = byId("editorNext");
    const newButton = byId("editorNewEntry");
    const saveButton = byId("editorSaveDraft");
    const finishButton = byId("editorFinish");
    const closeButton = byId("editorClose");

    const apiUrl = dialog.dataset.apiUrl;

    const csrfToken = form.elements.namedItem(
        "_csrf_token"
    ).value;

    let activeJournal = null;
    let activeEntry = null;
    let entries = [];

    let dirty = false;
    let busy = false;
    let saveTimer = null;
    let savePromise = null;
    let revision = 0;
    let changed = false;

    const autosaveDelay = 1500;


    // ----------------------------------------------
    // API requests
    // ----------------------------------------------

    async function requestData(url, options = {}) {

        const response = await fetch(url, {
            credentials: "same-origin",
            cache: "no-store",
            ...options
        });

        const type = response.headers.get(
            "content-type"
        ) || "";

        if (!type.includes("application/json")) {

            throw new Error(
                "Unable to access your journal. " +
                "Please check your session."
            );
        }

        const data = await response.json();

        if (!response.ok || !data.success) {

            throw new Error(
                data.error || "Journal request failed."
            );
        }

        return data;
    }


    function journalUrl(journalId) {

        return apiUrl + "/" +
            encodeURIComponent(journalId);
    }


    function entryUrl(entryId) {

        return apiUrl + "/entries/" +
            encodeURIComponent(entryId);
    }


    function postBody(values = {}) {

        const body = new FormData();

        body.set("_csrf_token", csrfToken);

        Object.entries(values).forEach(
            ([key, value]) => {
                body.set(key, value);
            }
        );

        return body;
    }


    // ----------------------------------------------
    // Interface state
    // ----------------------------------------------

    function setStatus(message, state = "") {

        saveStatus.textContent = message;

        saveStatus.className = [
            "editor-save-status",
            state
        ].filter(Boolean).join(" ");
    }


    function showError(message) {

        errorMessage.textContent = message;
        errorMessage.hidden = false;
    }


    function clearError() {

        errorMessage.textContent = "";
        errorMessage.hidden = true;
    }


    function currentIndex() {

        if (!activeEntry) {
            return -1;
        }

        return entries.findIndex(
            entry => entry.id === activeEntry.id
        );
    }


    function updateControls() {

        const index = currentIndex();

        previousButton.disabled =
            busy || index <= 0;

        nextButton.disabled =
            busy ||
            index < 0 ||
            index >= entries.length - 1;

        newButton.disabled =
            busy || !activeJournal;

        closeButton.disabled = busy;

        saveButton.disabled =
            busy || !activeEntry;

        finishButton.disabled =
            busy || !activeEntry;

        title.readOnly =
            busy || !activeEntry;

        content.readOnly =
            busy || !activeEntry;

        byId("editorPosition").textContent =
            index >= 0
                ? `Entry ${index + 1} of ${entries.length}`
                : "No entry selected";

        if (activeEntry) {

            const published =
                activeEntry.status === "published";

            finishButton.textContent =
                published
                    ? "Save and close"
                    : "Finish entry";

            byId("editorEntryStatus").textContent =
                published ? "Completed" : "Draft";
        }
    }


    function setBusy(value) {

        busy = value;
        updateControls();
    }


    function updateWordCount() {

        const text = content.value.trim();

        const count = text
            ? text.split(/\s+/u).length
            : 0;

        byId("editorWordCount").textContent =
            count.toLocaleString() +
            (count === 1 ? " word" : " words");
    }


    function formatDate(value) {

        if (!value) {
            return "";
        }

        const date = new Date(
            value + "T12:00:00"
        );

        if (Number.isNaN(date.getTime())) {
            return value;
        }

        return date.toLocaleDateString(
            undefined,
            {
                weekday: "long",
                year: "numeric",
                month: "long",
                day: "numeric"
            }
        );
    }


    // ----------------------------------------------
    // Apply saved journal design
    // ----------------------------------------------

    function applyDesign(design = {}) {

        const paperStyles = [
            "lined",
            "blank",
            "dotted",
            "dark"
        ];

        const layouts = [
            "single",
            "spread"
        ];

        const typography = [
            "classic",
            "modern",
            "elegant"
        ];

        const paper = paperStyles.includes(
            design.paper_style
        )
            ? design.paper_style
            : "lined";

        const layout = layouts.includes(
            design.page_layout
        )
            ? design.page_layout
            : "single";

        const font = typography.includes(
            design.typography
        )
            ? design.typography
            : "classic";

        book.className = [
            "editor-book",
            paper,
            layout,
            font
        ].join(" ");

        const color =
            /^#[0-9a-f]{6}$/i.test(
                design.cover_color || ""
            )
                ? design.cover_color
                : "#594536";

        book.style.setProperty(
            "--cover-color",
            color
        );
    }


    // ----------------------------------------------
    // Load and display entries
    // ----------------------------------------------

    function displayEntry(entry) {
        queueMicrotask(refreshPrivacyControls);


        clearTimeout(saveTimer);

        activeEntry = entry;

        title.value = entry.title || "";
        content.value = entry.content || "";

        byId("editorDate").textContent =
            formatDate(entry.entry_date);

        byId("editorDate").dateTime =
            entry.entry_date || "";

        dirty = false;
        revision = 0;

        clearError();
        setStatus("All changes saved");

        updateWordCount();
        updateControls();
    }


    async function refreshEntries() {

        const data = await requestData(
            journalUrl(activeJournal.id)
        );

        activeJournal = data.journal;

        entries = [...data.entries].sort(
            (a, b) => {

                const first =
                    a.entry_date + a.created_utc;

                const second =
                    b.entry_date + b.created_utc;

                return first.localeCompare(second);
            }
        );

        applyDesign(
            activeJournal.design || {}
        );

        updateControls();
    }


    async function loadEntry(entryId) {

        const data = await requestData(
            entryUrl(entryId)
        );

        if (
            data.entry.journal_id !== activeJournal.id
        ) {

            throw new Error(
                "Entry does not belong to this journal."
            );
        }

        displayEntry(data.entry);
    }


    async function createEntry() {

        const data = await requestData(
            journalUrl(activeJournal.id) +
            "/entries",
            {
                method: "POST",
                body: postBody()
            }
        );

        changed = true;

        entries.push(data.entry);

        displayEntry(data.entry);
    }


    // ----------------------------------------------
    // Autosave
    // ----------------------------------------------

    function scheduleAutosave() {

        clearTimeout(saveTimer);

        if (!dirty || !activeEntry) {
            return;
        }

        saveTimer = setTimeout(() => {

            saveEntry(false);

        }, autosaveDelay);
    }


    async function saveEntry(publish = false) {

        clearTimeout(saveTimer);

        if (!activeEntry) {
            return true;
        }

        if (savePromise) {

            const successful = await savePromise;

            if (!successful) {
                return false;
            }
        }

        if (!dirty && !publish) {
            return true;
        }

        if (publish && !content.value.trim()) {

            showError(
                "Write something before finishing your entry."
            );

            return false;
        }

        const entryId = activeEntry.id;
        const savedRevision = revision;

        const body = postBody({
            title: title.value,
            content: content.value,
            publish: publish ? "true" : "false"
        });

        setStatus("Saving...", "pending");
        clearError();

        const operation = (async () => {

            try {

                const data = await requestData(
                    entryUrl(entryId) + "/save",
                    {
                        method: "POST",
                        body: body
                    }
                );

                if (
                    activeEntry &&
                    activeEntry.id === entryId
                ) {

                    activeEntry = data.entry;
        refreshPrivacyControls();

                    const index = currentIndex();

                    if (index >= 0) {
                        entries[index] = data.entry;
                    }

                    dirty = revision !== savedRevision;

                    setStatus(
                        dirty
                            ? "Unsaved changes"
                            : "All changes saved",
                        dirty ? "pending" : ""
                    );
                }

                changed = true;

                updateControls();

                return true;

            } catch (error) {

                dirty = true;

                setStatus(
                    "Not saved",
                    "failed"
                );

                showError(
                    error.message +
                    " Your writing is still in the editor."
                );

                return false;
            }

        })();

        savePromise = operation;

        const successful = await operation;

        if (savePromise === operation) {
            savePromise = null;
        }

        if (successful && dirty && !busy) {
            scheduleAutosave();
        }

        return successful;
    }


    async function flushChanges() {

        clearTimeout(saveTimer);

        if (savePromise) {

            const successful = await savePromise;

            if (!successful) {
                return false;
            }
        }

        if (dirty) {
            return await saveEntry(false);
        }

        return true;
    }


    function markChanged() {

        if (!activeEntry || busy) {
            return;
        }

        revision++;
        dirty = true;

        setStatus(
            "Unsaved changes",
            "pending"
        );

        updateWordCount();
        scheduleAutosave();
    }


    title.addEventListener(
        "input",
        markChanged
    );

    content.addEventListener(
        "input",
        markChanged
    );


    // ----------------------------------------------
    // Open journal editor
    // ----------------------------------------------

    async function openEditor(
        journal,
        entryId = null
    ) {

        if (
            busy ||
            dialog.open ||
            !journal ||
            typeof journal.id !== "string"
        ) {
            return;
        }

        activeJournal = journal;
        activeEntry = null;
        entries = [];

        dirty = false;
        changed = false;
        revision = 0;

        title.value = "";
        content.value = "";

        byId("editorDate").textContent = "";
        byId("editorEntryStatus").textContent = "";

        byId("editorJournalName").textContent =
            journal.title || "My Journal";

        applyDesign(journal.design || {});

        clearError();
        updateWordCount();

        setBusy(true);
        setStatus("Opening journal...", "pending");

        dialog.showModal();

        try {

            await refreshEntries();

            if (entryId) {

                await loadEntry(entryId);

            } else {

                const draft = [...entries]
                    .reverse()
                    .find(
                        entry => entry.status === "draft"
                    );

                if (draft) {

                    await loadEntry(draft.id);

                } else if (entries.length) {

                    await loadEntry(
                        entries[entries.length - 1].id
                    );

                } else {

                    await createEntry();
                }
            }

        } catch (error) {

            showError(error.message);
            setStatus("Unable to open", "failed");

        } finally {

            setBusy(false);
        }

        if (activeEntry) {
            content.focus();
        }
    }


    // ----------------------------------------------
    // Entry navigation
    // ----------------------------------------------

    async function navigate(direction) {

        if (busy || !activeEntry) {
            return;
        }

        const target = entries[
            currentIndex() + direction
        ];

        if (!target) {
            return;
        }

        setBusy(true);

        try {

            if (!(await flushChanges())) {
                return;
            }

            await loadEntry(target.id);

        } catch (error) {

            showError(error.message);

        } finally {

            setBusy(false);
        }
    }


    previousButton.addEventListener(
        "click",
        () => navigate(-1)
    );

    nextButton.addEventListener(
        "click",
        () => navigate(1)
    );


    // ----------------------------------------------
    // New entry
    // ----------------------------------------------

    newButton.addEventListener(
        "click",
        async () => {

            if (busy || !activeJournal) {
                return;
            }

            setBusy(true);

            try {

                if (!(await flushChanges())) {
                    return;
                }

                await createEntry();

            } catch (error) {

                showError(error.message);

            } finally {

                setBusy(false);
            }

            if (activeEntry) {
                title.focus();
            }
        }
    );


    // ----------------------------------------------
    // Manual save
    // ----------------------------------------------

    saveButton.addEventListener(
        "click",
        async () => {

            if (busy || !activeEntry) {
                return;
            }

            setBusy(true);

            try {

                await flushChanges();

            } finally {

                setBusy(false);
            }
        }
    );


    // ----------------------------------------------
    // Close editor safely
    // ----------------------------------------------

    function completeClose() {

        clearTimeout(saveTimer);

        const journalId = activeJournal
            ? activeJournal.id
            : null;

        const notify = changed;

        dialog.close();

        activeJournal = null;
        activeEntry = null;
        entries = [];

        title.value = "";
        content.value = "";

        dirty = false;
        changed = false;

        clearError();

        if (notify && journalId) {

            document.dispatchEvent(
                new CustomEvent(
                    "legacy:journal-entries-changed",
                    {
                        detail: {
                            journalId: journalId
                        }
                    }
                )
            );
        }
    }


    async function closeEditor() {

        if (busy) {
            return;
        }

        setBusy(true);

        try {

            if (!(await flushChanges())) {
                return;
            }

            completeClose();

        } finally {

            setBusy(false);
        }
    }


    closeButton.addEventListener(
        "click",
        closeEditor
    );

    dialog.addEventListener(
        "cancel",
        event => {

            event.preventDefault();
            closeEditor();
        }
    );


    // ----------------------------------------------
    // Finalize entry
    // ----------------------------------------------

    form.addEventListener(
        "submit",
        async event => {

            event.preventDefault();

            if (busy || !activeEntry) {
                return;
            }

            setBusy(true);

            try {

                if (!(await flushChanges())) {
                    return;
                }

                if (
                    activeEntry.status !== "published"
                ) {

                    const successful =
                        await saveEntry(true);

                    if (!successful) {
                        return;
                    }
                }

                completeClose();

            } finally {

                setBusy(false);
            }
        }
    );


    // ----------------------------------------------
    // Protect unsaved writing
    // ----------------------------------------------

    window.addEventListener(
        "beforeunload",
        event => {

            if (dirty || savePromise) {

                event.preventDefault();
                event.returnValue = "";
            }
        }
    );


    // ----------------------------------------------
    // Public editor interface
    // ----------------------------------------------



    // JOURNAL PRIVACY CONTROLS

    const journalPrivacyControl =
        document.getElementById("editorJournalPrivacy");

    const entryPrivacyControl =
        document.getElementById("editorEntryPrivacy");

    const privacyMessage = document.createElement("p");

    privacyMessage.setAttribute("role", "status");
    privacyMessage.style.fontSize = "0.85rem";
    privacyMessage.style.marginTop = "8px";

    entryPrivacyControl.insertAdjacentElement(
        "afterend",
        privacyMessage
    );

    let privacySaving = false;

    function refreshPrivacyControls() {

        if (!activeJournal || !activeEntry) {
            journalPrivacyControl.disabled = true;
            entryPrivacyControl.disabled = true;
            return;
        }

        journalPrivacyControl.value =
            activeJournal.ai_default_enabled
                ? "include"
                : "private";

        entryPrivacyControl.value =
            activeEntry.ai_preference || "inherit";

        journalPrivacyControl.disabled = privacySaving;
        entryPrivacyControl.disabled = privacySaving;

        const preference =
            activeEntry.ai_preference || "inherit";

        const included =
            preference === "include" ||
            (
                preference === "inherit" &&
                activeJournal.ai_default_enabled
            );

        if (!included) {
            privacyMessage.textContent =
                "Private — excluded from AI learning.";
        } else if (activeEntry.status === "draft") {
            privacyMessage.textContent =
                "Legacy will learn from this entry when finalized, if account AI consent is enabled.";
        } else {
            privacyMessage.textContent =
                "Included in Legacy, subject to account AI consent.";
        }
    }


    async function updatePrivacy(scope, value) {

        if (
            privacySaving ||
            !activeJournal ||
            !activeEntry
        ) {
            return;
        }

        privacySaving = true;

        const journalId = activeJournal.id;
        const entryId = activeEntry.id;

        refreshPrivacyControls();

        try {

            await flushChanges();

            if (dirty) {
                throw new Error(
                    "Save your writing before changing privacy."
                );
            }

            const body = new URLSearchParams();

            const csrf = document.querySelector(
                '#journalEditorForm input[name="_csrf_token"]'
            );

            if (csrf) {
                body.set("_csrf_token", csrf.value);
            }

            let endpoint;

            if (scope === "journal") {

                endpoint =
                    apiUrl + "/" +
                    encodeURIComponent(journalId) +
                    "/privacy";

                body.set(
                    "ai_default_enabled",
                    value === "include" ? "true" : "false"
                );

                body.set("apply_to_existing", "false");

            } else {

                endpoint =
                    apiUrl + "/entries/" +
                    encodeURIComponent(entryId) +
                    "/privacy";

                body.set("ai_preference", value);
            }

            privacyMessage.textContent =
                "Updating AI settings...";

            const result = await requestData(
                endpoint,
                {
                    method: "POST",
                    body: body
                }
            );

            if (
                !activeJournal ||
                activeJournal.id !== journalId
            ) {
                return;
            }

            if (scope === "journal") {

                activeJournal.ai_default_enabled =
                    value === "include";

            } else if (
                activeEntry &&
                activeEntry.id === entryId
            ) {

                activeEntry.ai_preference = value;
            }

            changed = true;

            refreshPrivacyControls();

            if (
                result.indexing &&
                (
                    result.indexing.status === "retry_required" ||
                    result.indexing.entries_failed > 0
                )
            ) {
                privacyMessage.textContent =
                    "Settings saved. Some AI indexing needs retrying.";
            }

        } catch (error) {

            refreshPrivacyControls();

            privacyMessage.textContent =
                error.message ||
                "Unable to update AI settings.";

        } finally {

            privacySaving = false;

            journalPrivacyControl.disabled = false;
            entryPrivacyControl.disabled = false;
        }
    }


    journalPrivacyControl.addEventListener(
        "change",
        function () {
            updatePrivacy("journal", this.value);
        }
    );

    entryPrivacyControl.addEventListener(
        "change",
        function () {
            updatePrivacy("entry", this.value);
        }
    );


    window.LegacyJournalEditor = {
        open: openEditor
    };

});
