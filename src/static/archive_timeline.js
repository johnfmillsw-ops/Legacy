document.addEventListener("DOMContentLoaded", () => {

    const container = document.getElementById(
        "archiveUnifiedTimeline"
    );

    if (!container) return;

    const params = new URLSearchParams(
        window.location.search
    );

    if (params.get("room") !== "timeline") return;

    const search = document.getElementById(
        "archiveTimelineSearch"
    );

    const collection = document.getElementById(
        "archiveTimelineCollection"
    );

    const direction = document.getElementById(
        "archiveTimelineDirection"
    );

    const status = document.getElementById(
        "archiveTimelineStatus"
    );

    const explanation = document.getElementById(
        "archiveTimelineExplanation"
    );

    const previous = document.getElementById(
        "archiveTimelinePrevious"
    );

    const next = document.getElementById(
        "archiveTimelineNext"
    );

    const pageLabel = document.getElementById(
        "archiveTimelinePage"
    );

    const modes = document.querySelectorAll(
        "[data-timeline-mode]"
    );

    let mode = "event";
    let page = 1;
    let pages = 1;
    let version = 0;
    let searchTimer;

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

    function formatDate(value) {

        if (!value) return "Date not recorded";

        const parts = value.split("-");

        if (parts.length === 1) {
            return parts[0];
        }

        const year = Number(parts[0]);
        const month = Number(parts[1]);
        const day = Number(parts[2] || 1);

        if (month < 1 || month > 12) return value;

        const date = new Date(0);

        date.setUTCFullYear(year, month - 1, day);
        date.setUTCHours(0, 0, 0, 0);

        if (
            date.getUTCFullYear() !== year ||
            date.getUTCMonth() !== month - 1 ||
            date.getUTCDate() !== day
        ) return value;

        const options = {
            year: "numeric",
            month: "long",
            timeZone: "UTC"
        };

        if (parts.length === 3) {
            options.day = "numeric";
        }

        return date.toLocaleDateString(
            undefined,
            options
        );
    }

    function render(records) {

        container.replaceChildren();

        if (!records.length) {

            container.append(
                node(
                    "p",
                    "No historical records match this selection.",
                    "archive-note"
                )
            );

            return;
        }

        let currentYear = null;
        let group = null;

        for (const record of records) {

            const date = mode === "event"
                ? record.event_date
                : record.preserved_date;

            const year = date
                ? date.slice(0, 4)
                : "Undated records";

            if (year !== currentYear) {

                currentYear = year;

                group = node(
                    "section",
                    null,
                    "archive-chronology-year"
                );

                group.append(
                    node(
                        "h3",
                        year,
                        "archive-chronology-year-title"
                    )
                );

                container.append(group);
            }

            const article = node(
                "article",
                null,
                "archive-chronology-record"
            );

            const detail = node(
                "div",
                null,
                "archive-chronology-detail"
            );

            detail.append(
                node(
                    "span",
                    record.label,
                    "archive-eyebrow"
                ),
                node(
                    "p",
                    formatDate(date),
                    "archive-chronology-date"
                ),
                node(
                    "h4",
                    String(
                        record.title || "Untitled record"
                    ).replaceAll("_", " ")
                )
            );

            if (record.preview) {

                detail.append(
                    node(
                        "p",
                        record.preview,
                        "archive-chronology-preview"
                    )
                );
            }

            if (
                mode === "event" &&
                !record.event_date &&
                record.original_event_date
            ) {

                detail.append(
                    node(
                        "p",
                        "Recorded date description: " +
                        record.original_event_date,
                        "archive-note"
                    )
                );
            }

            if (mode === "event") {

                detail.append(
                    node(
                        "p",
                        "Preserved " +
                        formatDate(record.preserved_date),
                        "archive-note"
                    )
                );
            }

            if (
                mode === "preserved" &&
                record.event_date
            ) {

                detail.append(
                    node(
                        "p",
                        "Historical date: " +
                        formatDate(record.event_date),
                        "archive-note"
                    )
                );
            }

            const link = node(
                "a",
                "Explore historical record →",
                "archive-action"
            );

            link.href = record.url;

            detail.append(link);

            if (record.thumbnail) {

                const imageLink = node("a");

                imageLink.href = record.url;

                const image = node(
                    "img",
                    null,
                    "archive-chronology-photo"
                );

                image.src = record.thumbnail;
                image.alt = record.title || "Photograph";
                image.loading = "lazy";

                imageLink.append(image);
                article.append(imageLink);
            }

            article.append(detail);
            group.append(article);
        }
    }

    async function load() {

        const current = ++version;

        previous.disabled = true;
        next.disabled = true;

        status.textContent = "Opening the chronology...";

        const query = new URLSearchParams({
            mode,
            page: String(page),
            collection: collection.value,
            direction: direction.value,
            q: search.value
        });

        try {

            const response = await fetch(
                "/api/archive/timeline?" +
                query.toString(),
                {
                    credentials: "same-origin",
                    cache: "no-store"
                }
            );

            if (!response.ok) {
                throw new Error(
                    "Unable to load the historical timeline."
                );
            }

            const data = await response.json();

            if (current !== version) return;

            page = data.page;
            pages = data.pages;

            render(data.records || []);

            status.textContent =
                `${data.total} preserved records`;

            pageLabel.textContent =
                `Page ${page} of ${pages}`;

            previous.disabled = page <= 1;
            next.disabled = page >= pages;

        } catch (error) {

            if (current !== version) return;

            status.textContent = error.message;
        }
    }

    modes.forEach(button => {

        button.addEventListener("click", () => {

            mode = button.dataset.timelineMode;

            modes.forEach(item => {

                item.setAttribute(
                    "aria-pressed",
                    String(
                        item.dataset.timelineMode === mode
                    )
                );
            });

            explanation.textContent = mode === "event"
                ? "Organized by known historical dates. Undated records appear separately."
                : "Organized by when each record was preserved in Legacy (UTC).";

            page = 1;
            load();
        });
    });

    search.addEventListener("input", () => {

        clearTimeout(searchTimer);

        searchTimer = setTimeout(() => {

            page = 1;
            load();

        }, 300);
    });

    [collection, direction].forEach(control => {

        control.addEventListener("change", () => {

            page = 1;
            load();
        });
    });

    previous.addEventListener("click", () => {

        if (page <= 1) return;

        page--;
        load();

        container.scrollIntoView({
            behavior: "smooth"
        });
    });

    next.addEventListener("click", () => {

        if (page >= pages) return;

        page++;
        load();

        container.scrollIntoView({
            behavior: "smooth"
        });
    });

    load();
});
