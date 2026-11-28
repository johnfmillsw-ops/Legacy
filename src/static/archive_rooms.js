document.addEventListener("DOMContentLoaded", () => {

    const world = document.querySelector(".archive-world");

    if (!world) return;

    const params = new URLSearchParams(window.location.search);

    const room = params.get("room") || "";

    const sections = {
        library: "archive-library",
        oral: "archive-oral",
        gallery: "archive-gallery",
        documents: "archive-documents",
        memories: "archive-memories",
        timeline: "archive-timeline"
    };

    const names = {
        library: "The Library",
        oral: "Oral Histories",
        gallery: "The Gallery",
        documents: "Special Collections",
        memories: "The Memory Collection",
        timeline: "A Life in Time"
    };

    const illustrations = {

        library: `
            <rect x="30" y="15" width="180" height="115" rx="2"/>
            <path d="M30 72H210 M30 130H210"/>
            <rect x="42" y="25" width="18" height="47" fill="#64503a"/>
            <rect x="64" y="20" width="23" height="52" fill="#413c2f"/>
            <rect x="91" y="29" width="15" height="43" fill="#72543c"/>
            <rect x="111" y="22" width="24" height="50" fill="#494037"/>
            <rect x="141" y="26" width="18" height="46" fill="#5c4a38"/>
            <rect x="165" y="18" width="25" height="54" fill="#4b4b37"/>
            <rect x="45" y="84" width="28" height="46" fill="#594333"/>
            <rect x="79" y="78" width="18" height="52" fill="#494a39"/>
            <rect x="103" y="88" width="23" height="42" fill="#70543b"/>
            <rect x="132" y="80" width="28" height="50" fill="#514136"/>
            <rect x="166" y="88" width="23" height="42" fill="#494a39"/>
        `,

        oral: `
            <rect x="96" y="12" width="48" height="82" rx="24" fill="#493c2e"/>
            <path d="M107 27H133 M107 38H133 M107 49H133 M107 60H133"/>
            <path d="M84 60V72A36 36 0 0 0 156 72V60"/>
            <path d="M120 108V133 M85 133H155"/>
            <path d="M22 74H38L45 50L54 97L64 65H78"/>
            <path d="M162 74H176L185 49L195 96L205 65H220"/>
        `,

        gallery: `
            <rect x="18" y="30" width="85" height="88" fill="#493c2e"/>
            <rect x="26" y="38" width="69" height="72"/>
            <circle cx="61" cy="57" r="10" fill="#756044"/>
            <path d="M26 100L48 76L65 91L78 72L95 96"/>
            <rect x="119" y="16" width="102" height="72" fill="#493c2e"/>
            <rect x="127" y="24" width="86" height="56"/>
            <path d="M127 73L150 45L170 64L187 39L213 73"/>
            <rect x="135" y="99" width="67" height="37"/>
            <path d="M144 127L162 111L177 123L193 110"/>
        `,

        documents: `
            <path d="M51 35L153 20L173 117L71 133Z" fill="#40372a"/>
            <path d="M77 17H171L190 36V128H77Z" fill="#65543b"/>
            <path d="M171 17V36H190"/>
            <path d="M93 49H172 M93 62H172 M93 75H160 M93 88H172 M93 101H145"/>
            <circle cx="162" cy="112" r="11" fill="#704737"/>
            <path d="M32 126L52 69L57 83L43 126Z"/>
        `,

        memories: `
            <path d="M35 30Q77 15 120 39Q163 15 205 30V121Q163 106 120 130Q77 106 35 121Z" fill="#584831"/>
            <path d="M120 39V130"/>
            <path d="M47 43Q82 34 107 47 M47 57Q82 48 107 61 M47 71Q82 62 107 75 M47 85Q82 76 107 89"/>
            <path d="M133 47Q158 34 193 43 M133 61Q158 48 193 57 M133 75Q158 62 193 71 M133 89Q158 76 193 85"/>
            <path d="M120 40L129 48V111L120 104Z" fill="#8b6940"/>
        `,

        timeline: `
            <circle cx="120" cy="75" r="58" fill="#40372a"/>
            <circle cx="120" cy="75" r="48"/>
            <path d="M120 30V39 M120 111V120 M75 75H84 M156 75H165"/>
            <path d="M120 45V75L149 91" stroke-width="3"/>
            <circle cx="120" cy="75" r="4" fill="#bda27a"/>
            <path d="M15 75H48 M192 75H225"/>
            <circle cx="25" cy="75" r="4"/>
            <circle cx="215" cy="75" r="4"/>
        `
    };

    const roomLinks = world.querySelectorAll(".archive-room");

    for (const link of roomLinks) {

        const original = link.getAttribute("href") || "";

        const key = Object.keys(sections).find(
            item => original === "#" + sections[item]
        );

        if (!key) continue;

        link.href = "/archive?room=" + key;

        const heading = link.querySelector("h3");
        const description = link.querySelector("p");
        const action = link.querySelector(".archive-room-link");
        const number = link.querySelector(".archive-room-number");

        const art = document.createElement("div");
        art.className = "archive-room-art";

        art.innerHTML = `
            <svg viewBox="0 0 240 150"
                 fill="none"
                 stroke="#bda27a"
                 stroke-width="1.4"
                 aria-hidden="true">
                ${illustrations[key]}
            </svg>
        `;

        const copy = document.createElement("div");
        copy.className = "archive-room-copy";

        for (const item of [heading, description, action]) {
            if (item) copy.append(item);
        }

        link.replaceChildren();

        if (number) link.append(number);

        link.append(art, copy);
    }

    const selected = sections[room] || null;

    for (const section of world.querySelectorAll(".archive-section")) {
        section.hidden = section.id !== selected;
    }

    if (selected) {

        world.classList.add("archive-room-page");

        for (const selector of [
            ".archive-entrance",
            ".archive-introduction",
            ".archive-rooms"
        ]) {

            const element = world.querySelector(selector);

            if (element) element.hidden = true;
        }

        const breadcrumbs = document.createElement("nav");

        breadcrumbs.className = "archive-breadcrumbs";
        breadcrumbs.setAttribute("aria-label", "Breadcrumb");

        const home = document.createElement("a");

        home.href = "/archive";
        home.textContent = "The Archive";

        const separator = document.createElement("span");
        separator.textContent = "›";

        const current = document.createElement("span");
        current.textContent = names[room];
        current.setAttribute("aria-current", "page");

        breadcrumbs.append(home, separator, current);

        world.prepend(breadcrumbs);
    }

    const documentTools = world.querySelector(
        "#archive-documents .archive-tools"
    );

    if (documentTools) {

        const details = document.createElement("details");

        details.className = "archive-document-tools";

        const summary = document.createElement("summary");

        summary.textContent = "Manage and preserve documents";

        documentTools.before(details);

        details.append(summary, documentTools);
    }

});
