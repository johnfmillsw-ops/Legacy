
document.addEventListener("DOMContentLoaded", () => {

    const data = JSON.parse(
        document.getElementById(
            "identityPortraitData"
        ).textContent
    );

    const radar = document.getElementById("identityRadar");
    const buttons = document.getElementById("identityDimensions");
    const evidence = document.getElementById("identityEvidence");
    const ns = "http://www.w3.org/2000/svg";

    let selected = 0;

    function point(index, radius) {
        const angle = index * Math.PI / 3;
        return [
            200 + Math.sin(angle) * radius,
            170 - Math.cos(angle) * radius
        ];
    }

    function element(name, attrs, text) {
        const node = document.createElementNS(ns, name);

        Object.entries(attrs).forEach(([key, value]) => {
            node.setAttribute(key, value);
        });

        if (text !== undefined) {
            node.textContent = text;
        }

        radar.appendChild(node);
        return node;
    }

    function polygon(radius) {
        return data.map((_, index) =>
            point(index, radius).join(",")
        ).join(" ");
    }

    function drawRadar() {

        radar.replaceChildren();

        [36, 72, 108].forEach(radius => {
            element("polygon", {
                points: polygon(radius),
                fill: "none",
                stroke: "currentColor",
                "stroke-opacity": ".16"
            });
        });

        data.forEach((dimension, index) => {

            const end = point(index, 108);
            const label = point(index, 150);

            element("line", {
                x1: 200,
                y1: 170,
                x2: end[0],
                y2: end[1],
                stroke: "currentColor",
                "stroke-opacity": ".2"
            });

            element("text", {
                x: label[0],
                y: label[1] + 4,
                fill: index === selected
                    ? "#c5ab85"
                    : "currentColor",
                "font-size": 12,
                "text-anchor": "middle"
            }, dimension.name);
        });

        element("polygon", {
            points: data.map((dimension, index) =>
                point(index, dimension.level * 36).join(",")
            ).join(" "),
            fill: "#c5ab85",
            "fill-opacity": ".2",
            stroke: "#c5ab85",
            "stroke-width": 2
        });

        data.forEach((dimension, index) => {

            if (!dimension.level) return;

            const p = point(
                index,
                dimension.level * 36
            );

            element("circle", {
                cx: p[0],
                cy: p[1],
                r: index === selected ? 5 : 3,
                fill: "#c5ab85"
            });
        });
    }

    function selectDimension(index) {

        selected = index;
        const dimension = data[index];

        document.getElementById(
            "identityDimensionName"
        ).textContent = dimension.name;

        document.getElementById(
            "identityDimensionStatus"
        ).textContent = dimension.status;

        document.getElementById(
            "identityDimensionDescription"
        ).textContent = dimension.description;

        document.getElementById(
            "identityEvidenceCount"
        ).textContent =
            dimension.evidence_count +
            " documented records from " +
            dimension.source_count +
            " distinct sources";

        evidence.replaceChildren();

        if (!dimension.evidence.length) {
            const empty = document.createElement("p");
            empty.className = "legacy-muted";
            empty.textContent =
                "This area will develop as you share more of your story.";
            evidence.appendChild(empty);
        }

        dimension.evidence.forEach(item => {

            const row = document.createElement("div");
            row.className = "identity-evidence-item";

            const label = document.createElement("small");
            label.textContent =
                item.type + " · " + item.source;

            const content = document.createElement("div");
            content.textContent = item.text;

            row.append(label, content);

            if (item.excerpt) {

                const details = document.createElement("details");
                const summary = document.createElement("summary");
                const quote = document.createElement("p");

                summary.textContent = "Source excerpt";
                quote.textContent = item.excerpt;

                details.append(summary, quote);
                row.appendChild(details);
            }

            evidence.appendChild(row);
        });

        Array.from(buttons.children).forEach((button, i) => {
            button.setAttribute(
                "aria-pressed",
                String(i === selected)
            );
        });

        drawRadar();
    }

    data.forEach((dimension, index) => {

        const button = document.createElement("button");

        button.type = "button";
        button.className = "identity-dimension";
        button.textContent = dimension.name;

        button.addEventListener("click", () => {
            selectDimension(index);
        });

        buttons.appendChild(button);
    });

    selectDimension(0);
});
