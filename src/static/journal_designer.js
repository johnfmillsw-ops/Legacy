
document.addEventListener("DOMContentLoaded", () => {

    const dialog = document.getElementById(
        "journalDesigner"
    );

    if (!dialog) {
        return;
    }

    const form = document.getElementById(
        "journalDesignerForm"
    );

    const book = document.getElementById(
        "designerBook"
    );

    const paper = document.getElementById(
        "designerPaper"
    );

    const emblem = document.getElementById(
        "designerEmblem"
    );

    const saveButton = document.getElementById(
        "designerSave"
    );

    const errorMessage = document.getElementById(
        "designerError"
    );

    const apiUrl = dialog.dataset.apiUrl;

    let activeJournal = null;
    let saving = false;

    const defaults = {
        cover_style: "leather",
        cover_color: "#594536",
        accent_color: "#c5ab85",
        emblem: "none",
        typography: "classic",
        paper_style: "lined",
        page_layout: "single"
    };

    const options = {
        cover_style: [
            "leather", "linen", "minimal"
        ],
        emblem: [
            "none", "compass", "tree", "stars"
        ],
        typography: [
            "classic", "modern", "elegant"
        ],
        paper_style: [
            "lined", "blank", "dotted", "dark"
        ],
        page_layout: [
            "single", "spread"
        ]
    };

    const emblems = {

        none: "",

        compass: `
            <svg viewBox="0 0 48 48"
                 aria-hidden="true">
                <circle cx="24" cy="24" r="19"/>
                <circle cx="24" cy="24" r="15"/>
                <path d="M24 5V10"/>
                <path d="M24 38V43"/>
                <path d="M5 24H10"/>
                <path d="M38 24H43"/>
                <path d="M30 17L26 26L17 31L22 22Z"/>
                <path d="M24 11L27 21L37 24L27 27
                         L24 37L21 27L11 24L21 21Z"/>
            </svg>
        `,

        tree: `
            <svg viewBox="0 0 48 48"
                 aria-hidden="true">
                <path d="M24 43V22"/>
                <path d="M24 31L14 20"/>
                <path d="M24 27L34 17"/>
                <path d="M24 22V12"/>
                <path d="M17 35H31"/>
                <path d="M12 28
                         C2 25 4 13 12 12
                         C12 4 22 2 27 7
                         C35 2 44 10 40 17
                         C48 25 36 34 30 29"/>
                <path d="M15 43H33"/>
            </svg>
        `,

        stars: `
            <svg viewBox="0 0 48 48"
                 aria-hidden="true">
                <path d="M24 4L28 19L43 24
                         L28 28L24 44L20 28
                         L5 24L20 19Z"/>
                <path d="M9 5V15M4 10H14"/>
                <path d="M39 33V43M34 38H44"/>
            </svg>
        `
    };


    // ----------------------------------------------
    // Validate stored design
    // ----------------------------------------------

    function normalizeDesign(design = {}) {

        const result = { ...defaults };

        Object.keys(defaults).forEach(key => {

            const value = design[key];

            if (typeof value !== "string") {
                return;
            }

            if (options[key]) {

                if (options[key].includes(value)) {
                    result[key] = value;
                }

            } else if (
                /^#[0-9a-f]{6}$/i.test(value)
            ) {

                result[key] = value.toLowerCase();
            }
        });

        return result;
    }


    // ----------------------------------------------
    // Populate controls
    // ----------------------------------------------

    function applyDesign(design) {

        const values = normalizeDesign(design);

        Object.entries(values).forEach(
            ([key, value]) => {

                const control =
                    form.elements.namedItem(key);

                if (control) {
                    control.value = value;
                }
            }
        );

        updatePreview();
    }


    // ----------------------------------------------
    // Read current selections
    // ----------------------------------------------

    function getDesign() {

        const data = new FormData(form);

        const design = {};

        Object.keys(defaults).forEach(key => {
            design[key] = data.get(key);
        });

        return normalizeDesign(design);
    }


    // ----------------------------------------------
    // Live preview
    // ----------------------------------------------

    function updatePreview() {

        const design = getDesign();

        book.className = [
            "designer-book",
            design.cover_style,
            design.typography
        ].join(" ");

        book.style.setProperty(
            "--cover-color",
            design.cover_color
        );

        book.style.setProperty(
            "--accent-color",
            design.accent_color
        );

        emblem.innerHTML = emblems[design.emblem];

        paper.className = [
            "designer-paper",
            design.paper_style,
            design.page_layout
        ].join(" ");

        dialog.querySelectorAll(
            ".designer-swatch"
        ).forEach(button => {

            const selected =
                button.dataset.color.toLowerCase() ===
                design.cover_color.toLowerCase();

            button.classList.toggle(
                "selected",
                selected
            );

            button.setAttribute(
                "aria-pressed",
                String(selected)
            );
        });
    }


    // ----------------------------------------------
    // Open design studio
    // ----------------------------------------------

    function openDesigner(journal) {

        if (
            !journal ||
            typeof journal.id !== "string" ||
            saving ||
            dialog.open
        ) {
            return;
        }

        activeJournal = journal;

        document.getElementById(
            "designerBookTitle"
        ).textContent =
            journal.title || "My Journal";

        document.getElementById(
            "designerBookSubtitle"
        ).textContent =
            journal.subtitle || "";

        errorMessage.hidden = true;

        applyDesign(journal.design || {});

        dialog.showModal();
    }


    // ----------------------------------------------
    // Close design studio
    // ----------------------------------------------

    function closeDesigner() {

        if (saving) {
            return;
        }

        dialog.close();
        activeJournal = null;
        errorMessage.hidden = true;
    }


    // ----------------------------------------------
    // Color swatches
    // ----------------------------------------------

    dialog.querySelectorAll(
        ".designer-swatch"
    ).forEach(button => {

        button.addEventListener("click", () => {

            document.getElementById(
                "designerCoverColor"
            ).value = button.dataset.color;

            updatePreview();
        });
    });


    form.addEventListener(
        "input",
        updatePreview
    );

    form.addEventListener(
        "change",
        updatePreview
    );


    // ----------------------------------------------
    // Reset and cancel
    // ----------------------------------------------

    document.getElementById(
        "designerReset"
    ).addEventListener("click", () => {

        if (!saving) {
            applyDesign(defaults);
        }
    });

    document.getElementById(
        "designerClose"
    ).addEventListener(
        "click",
        closeDesigner
    );

    document.getElementById(
        "designerCancel"
    ).addEventListener(
        "click",
        closeDesigner
    );

    dialog.addEventListener("cancel", event => {

        event.preventDefault();

        closeDesigner();
    });


    // ----------------------------------------------
    // Save design
    // ----------------------------------------------

    form.addEventListener("submit", async event => {

        event.preventDefault();

        if (!activeJournal || saving) {
            return;
        }

        const journalId = activeJournal.id;

        const design = getDesign();

        const body = new FormData();

        body.set(
            "_csrf_token",
            form.elements.namedItem(
                "_csrf_token"
            ).value
        );

        Object.entries(design).forEach(
            ([key, value]) => {
                body.set(key, value);
            }
        );

        saving = true;
        saveButton.textContent = "Saving...";
        errorMessage.hidden = true;

        const controls = Array.from(
            dialog.querySelectorAll(
                "button, input"
            )
        );

        const previousStates = controls.map(
            control => control.disabled
        );

        controls.forEach(control => {
            control.disabled = true;
        });

        let savedJournal = null;

        try {

            const response = await fetch(
                apiUrl + "/" +
                encodeURIComponent(journalId) +
                "/design",
                {
                    method: "POST",
                    credentials: "same-origin",
                    body: body
                }
            );

            const contentType =
                response.headers.get(
                    "content-type"
                ) || "";

            if (
                !contentType.includes(
                    "application/json"
                )
            ) {

                throw new Error(
                    "Unable to save. Please check your session."
                );
            }

            const data = await response.json();

            if (!response.ok || !data.success) {

                throw new Error(
                    data.error ||
                    "Unable to save journal design."
                );
            }

            savedJournal = data.journal;

        } catch (error) {

            errorMessage.textContent =
                error.message;

            errorMessage.hidden = false;

        } finally {

            saving = false;

            controls.forEach(
                (control, index) => {

                    control.disabled =
                        previousStates[index];
                }
            );

            saveButton.textContent =
                "Save design";
        }

        if (savedJournal) {

            closeDesigner();

            document.dispatchEvent(
                new CustomEvent(
                    "legacy:journal-design-saved",
                    {
                        detail: savedJournal
                    }
                )
            );
        }
    });


    // ----------------------------------------------
    // Public interface for journal library
    // ----------------------------------------------

    window.LegacyJournalDesigner = {
        open: openDesigner
    };

});
