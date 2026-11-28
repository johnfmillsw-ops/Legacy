document.addEventListener("DOMContentLoaded", () => {

    const section = document.getElementById("archive-memories");

    if (!section || section.hidden) return;

    const records = document.getElementById("archiveMemories");
    const search = document.getElementById("archiveMemorySearch");
    const category = document.getElementById("archiveMemoryCategory");
    const count = document.getElementById("archiveMemoryCount");

    if (!records || !search || !category || !count) return;

    const toolbar = search.closest(".archive-toolbar");

    const volumes = document.createElement("div");

    volumes.className = "archive-volume-list";

    const heading = document.createElement("div");

    heading.className = "archive-volume-heading";

    const headingTitle = document.createElement("h3");

    headingTitle.textContent = "Volumes of remembrance";

    const headingDescription = document.createElement("p");

    headingDescription.textContent =
        "Explore the experiences preserved within each collection.";

    heading.append(headingTitle, headingDescription);

    toolbar.before(heading, volumes);

    const navigation = document.createElement("div");

    navigation.className = "archive-memory-navigation";

    const back = document.createElement("button");

    back.type = "button";
    back.className = "archive-action";
    back.textContent = "← All volumes";

    const currentTitle = document.createElement("h3");

    navigation.append(back, currentTitle);

    toolbar.before(navigation);

    const pagination = document.createElement("div");

    pagination.className = "archive-pagination";

    const previous = document.createElement("button");
    const next = document.createElement("button");
    const pageLabel = document.createElement("span");

    previous.type = "button";
    next.type = "button";

    previous.className = "archive-action";
    next.className = "archive-action";

    previous.textContent = "← Previous";
    next.textContent = "Next →";

    pagination.append(previous, pageLabel, next);

    records.after(pagination);

    records.classList.add("archive-reading-list");

    let selected = "";
    let page = 1;

    const pageSize = 10;

    const colors = [
        "#514337",
        "#51403b",
        "#3d493d",
        "#35434d",
        "#504838",
        "#453b4b"
    ];

    function label(value) {

        return String(value || "Uncategorized")
            .replaceAll("_", " ")
            .replace(/\b\w/g, character => character.toUpperCase());
    }

    function changeCategory(value) {

        category.value = value;

        category.dispatchEvent(
            new Event("change", { bubbles: true })
        );
    }

    function showVolumes() {

        selected = "";
        page = 1;

        heading.hidden = false;
        volumes.hidden = false;

        navigation.hidden = true;
        toolbar.hidden = true;
        records.hidden = true;
        count.hidden = true;
        pagination.hidden = true;

        search.value = "";

        changeCategory("");
    }

    function openVolume(value, title) {

        selected = value;
        page = 1;

        heading.hidden = true;
        volumes.hidden = true;

        navigation.hidden = false;
        toolbar.hidden = false;
        records.hidden = false;
        count.hidden = false;

        category.hidden = true;

        currentTitle.textContent = title;

        search.value = "";

        changeCategory(
            value === "__all__" ? "" : value
        );

        applyPagination();

        section.scrollIntoView({
            behavior: "auto",
            block: "start"
        });
    }

    function addVolume(value, title, total, index) {

        const volume = document.createElement("button");

        volume.type = "button";
        volume.className = "archive-volume";

        const book = document.createElement("span");

        book.className = "archive-volume-book";
        book.style.background = colors[index % colors.length];

        book.textContent = "✦";

        const copy = document.createElement("div");

        copy.className = "archive-volume-copy";

        const name = document.createElement("h3");

        name.textContent = title;

        const description = document.createElement("p");

        description.textContent =
            `${total} ${total === 1 ? "memory" : "memories"}`;

        copy.append(name, description);

        const arrow = document.createElement("span");

        arrow.className = "archive-volume-arrow";
        arrow.textContent = "›";

        volume.append(book, copy, arrow);

        volume.addEventListener("click", () => {
            openVolume(value, title);
        });

        volumes.append(volume);
    }

    function applyPagination() {

        if (!selected) return;

        const cards = Array.from(
            records.querySelectorAll(":scope > .archive-record")
        );

        const totalPages = Math.max(
            1,
            Math.ceil(cards.length / pageSize)
        );

        page = Math.min(page, totalPages);

        cards.forEach((card, index) => {

            card.hidden =
                index < (page - 1) * pageSize ||
                index >= page * pageSize;
        });

        pagination.hidden = totalPages <= 1;

        previous.disabled = page <= 1;
        next.disabled = page >= totalPages;

        pageLabel.textContent =
            `Page ${page} of ${totalPages}`;
    }

    const observer = new MutationObserver(() => {
        applyPagination();
    });

    observer.observe(records, {
        childList: true
    });

    previous.addEventListener("click", () => {

        page = Math.max(1, page - 1);

        applyPagination();

        navigation.scrollIntoView({
            behavior: "auto",
            block: "start"
        });
    });

    next.addEventListener("click", () => {

        page++;

        applyPagination();

        navigation.scrollIntoView({
            behavior: "auto",
            block: "start"
        });
    });

    search.addEventListener("input", () => {

        page = 1;

        applyPagination();
    });

    back.addEventListener("click", showVolumes);

    showVolumes();

    volumes.textContent = "Opening your collection...";

    fetch("/api/archive/collections", {
        credentials: "same-origin",
        cache: "no-store"
    })
        .then(response => {

            if (!response.ok) {
                throw new Error(
                    "Unable to retrieve memory volumes."
                );
            }

            return response.json();
        })
        .then(result => {

            const memories = result.memories || [];

            const groups = new Map();

            for (const memory of memories) {

                const key = memory.category || "";

                groups.set(
                    key,
                    (groups.get(key) || 0) + 1
                );
            }

            volumes.replaceChildren();

            addVolume(
                "__all__",
                "The Complete Collection",
                memories.length,
                0
            );

            const ordered = [...groups.entries()].sort(
                (a, b) => label(a[0]).localeCompare(label(b[0]))
            );

            ordered.forEach(([key, total], index) => {

                if (!key) return;

                addVolume(
                    key,
                    label(key),
                    total,
                    index + 1
                );
            });

            headingDescription.textContent =
                `${memories.length} preserved memories across ` +
                `${groups.size} historical categories.`;
        })
        .catch(error => {
            volumes.textContent = error.message;
        });

});
