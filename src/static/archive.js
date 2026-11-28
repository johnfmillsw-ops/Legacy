document.addEventListener("DOMContentLoaded", () => {

    const voiceList =
        document.getElementById("archiveVoiceRecords");

    if (!voiceList) return;

    const writtenList =
        document.getElementById("archiveWrittenRecords");

    const search =
        document.getElementById("archiveVoiceSearch");

    const sort =
        document.getElementById("archiveVoiceSort");

    const count =
        document.getElementById("archiveVoiceCount");

    const dialog =
        document.getElementById("archiveRecordDialog");

    const title =
        document.getElementById("archiveRecordTitle");

    const metadata =
        document.getElementById("archiveRecordMetadata");

    const audio =
        document.getElementById("archiveRecordAudio");

    const content =
        document.getElementById("archiveRecordContent");

    let recordings = [];
    let requestVersion = 0;
    let listVersion = 0;

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

    function element(tag, value, className) {

        const node = document.createElement(tag);

        if (value != null) {
            node.textContent = value;
        }

        if (className) {
            node.className = className;
        }

        return node;
    }

    function action(label, handler) {

        const button = element(
            "button",
            label,
            "archive-action"
        );

        button.type = "button";
        button.addEventListener("click", handler);

        return button;
    }

    function formatDate(value) {

        if (!value) return "Date unavailable";

        const date = new Date(
            /^\d{4}-\d{2}-\d{2}$/.test(value)
                ? `${value}T00:00:00`
                : value
        );

        return Number.isNaN(date.getTime())
            ? "Date unavailable"
            : date.toLocaleDateString(undefined, {
                year: "numeric",
                month: "long",
                day: "numeric"
            });
    }

    function duration(seconds) {

        if (seconds == null) return "";

        const total = Math.max(0, Math.floor(seconds));

        if (!Number.isFinite(total)) return "";

        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const remainder = total % 60;

        return [
            hours ? `${hours} hr` : "",
            minutes ? `${minutes} min` : "",
            `${remainder} sec`
        ].filter(Boolean).join(" ");
    }

    function stopAudio() {

        audio.pause();
        audio.removeAttribute("src");
        audio.load();
        audio.hidden = true;
    }

    function prepareDialog(recordTitle) {

        const version = ++requestVersion;

        stopAudio();

        title.textContent = recordTitle || "Untitled record";
        metadata.textContent = "";
        content.textContent = "Loading record...";

        if (!dialog.open) {
            dialog.showModal();
        }

        return version;
    }

    async function openRecording(record) {

        const version = prepareDialog(record.title);

        try {

            const result = await getJSON(
                `/voice-journal/${encodeURIComponent(record.id)}`
            );

            if (version !== requestVersion) return;

            const journal = result.journal;

            title.textContent =
                journal.title || "Untitled recording";

            metadata.textContent = [
                formatDate(journal.created_utc),
                duration(journal.duration_seconds)
            ].filter(Boolean).join(" · ");

            if (journal.audio_url) {

                const url = new URL(
                    journal.audio_url,
                    window.location.origin
                );

                if (url.origin === window.location.origin) {
                    audio.hidden = false;
                    audio.src = url.href;
                    audio.load();
                }
            }

            content.textContent =
                journal.transcript ||
                "A transcript is not currently available.";

        } catch (error) {

            if (version !== requestVersion) return;

            content.textContent = error.message;
        }
    }

    function renderRecordings() {

        const query = search.value.trim().toLowerCase();

        const filtered = recordings.filter(record =>
            String(record.title || "")
                .toLowerCase()
                .includes(query)
        );

        filtered.sort((a, b) => {

            if (sort.value === "title") {
                return String(a.title || "").localeCompare(
                    String(b.title || "")
                );
            }

            const difference =
                new Date(b.created_utc).getTime() -
                new Date(a.created_utc).getTime();

            return sort.value === "oldest"
                ? -difference
                : difference;
        });

        voiceList.replaceChildren();

        count.textContent =
            `${filtered.length} of ${recordings.length} recordings`;

        if (!filtered.length) {

            voiceList.append(
                element(
                    "p",
                    query
                        ? "No matching recordings."
                        : "Your preserved recordings will appear here."
                )
            );

            return;
        }

        for (const record of filtered) {

            const card = element(
                "article",
                null,
                "archive-record"
            );

            card.append(
                element("span", "ORIGINAL RECORDING", "archive-eyebrow"),
                element("h3", record.title || "Untitled recording"),
                element(
                    "p",
                    [
                        formatDate(record.created_utc),
                        duration(record.duration_seconds)
                    ].filter(Boolean).join(" · "),
                    "archive-note"
                ),
                action(
                    "Listen & read transcript",
                    () => openRecording(record)
                )
            );

            voiceList.append(card);
        }
    }

    async function loadRecordings() {

        const version = ++listVersion;

        try {

            const result = await getJSON("/voice-journal/list");

            if (version !== listVersion) return;

            recordings = Array.isArray(result.journals)
                ? result.journals
                : [];

            renderRecordings();

        } catch (error) {

            if (version !== listVersion) return;

            count.textContent = error.message;

            if (!recordings.length) {
                voiceList.textContent = error.message;
            }
        }
    }

    async function openWrittenEntry(entry) {

        const version = prepareDialog(entry.title);

        try {

            const result = await getJSON(
                `/api/journals/entries/${encodeURIComponent(entry.id)}`
            );

            if (version !== requestVersion) return;

            const record = result.entry;

            title.textContent =
                record.title || "Untitled entry";

            metadata.textContent =
                formatDate(record.entry_date || record.created_utc);

            content.textContent =
                record.content || "This entry is empty.";

        } catch (error) {

            if (version !== requestVersion) return;

            content.textContent = error.message;
        }
    }

    async function openWrittenJournal(journal) {

        const version = prepareDialog(journal.title);

        try {

            const result = await getJSON(
                `/api/journals/${encodeURIComponent(journal.id)}`
            );

            if (version !== requestVersion) return;

            const entries = Array.isArray(result.entries)
                ? result.entries
                : [];

            metadata.textContent =
                `${entries.length} written entries`;

            content.replaceChildren();

            if (!entries.length) {

                content.textContent =
                    "This journal has no entries yet.";

                return;
            }

            for (const entry of entries) {

                const card = element(
                    "article",
                    null,
                    "archive-record"
                );

                card.append(
                    element("h3", entry.title || "Untitled entry"),
                    element(
                        "p",
                        formatDate(entry.entry_date || entry.created_utc),
                        "archive-note"
                    ),
                    element("p", entry.preview || ""),
                    action(
                        "Read entry",
                        () => openWrittenEntry(entry)
                    )
                );

                content.append(card);
            }

        } catch (error) {

            if (version !== requestVersion) return;

            content.textContent = error.message;
        }
    }

    async function loadWrittenJournals() {

        try {

            const result = await getJSON("/api/journals");

            const journals = Array.isArray(result.journals)
                ? result.journals
                : [];

            writtenList.replaceChildren();

            if (!journals.length) {

                writtenList.append(
                    element(
                        "p",
                        "Your written journals will appear here."
                    )
                );

                return;
            }

            for (const journal of journals) {

                const card = element(
                    "article",
                    null,
                    "archive-record"
                );

                card.append(
                    element("span", "WRITTEN COLLECTION", "archive-eyebrow"),
                    element("h3", journal.title || "Untitled journal"),
                    element("p", journal.subtitle || ""),
                    element(
                        "p",
                        `${journal.entry_count || 0} entries`,
                        "archive-note"
                    ),
                    action(
                        "Explore journal",
                        () => openWrittenJournal(journal)
                    )
                );

                writtenList.append(card);
            }

        } catch (error) {

            writtenList.textContent = error.message;
        }
    }

    search.addEventListener("input", renderRecordings);

    sort.addEventListener("change", renderRecordings);

    document.getElementById("archiveVoiceRefresh")
        .addEventListener("click", loadRecordings);

    document.getElementById("archiveCloseRecord")
        .addEventListener("click", () => dialog.close());

    dialog.addEventListener("close", () => {
        requestVersion++;
        stopAudio();
    });

    window.addEventListener("pagehide", stopAudio);

    loadRecordings();
    loadWrittenJournals();

});
