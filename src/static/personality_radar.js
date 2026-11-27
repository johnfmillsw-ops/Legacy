(() => {
    "use strict";

    const data = document.getElementById("psychRadarData");
    const svg = document.getElementById("psychRadar");
    const buttons = document.getElementById("psychRadarButtons");
    const details = document.getElementById("psychRadarDetails");
    const selection = document.getElementById("psychRadarSelection");
    const description = document.getElementById("psychRadarDescription");
    const note = document.getElementById("psychRadarNote");

    if (!data || !svg || !buttons || !details ||
        !selection || !description || !note) {
        return;
    }

    const groups = JSON.parse(data.textContent);

    const NS = "http://www.w3.org/2000/svg";

    const CX = 260;
    const CY = 230;
    const RADIUS = 137;

    let selected = null;

    function svgElement(tag, attributes = {}) {
        const node = document.createElementNS(NS, tag);

        Object.entries(attributes).forEach(([key, value]) => {
            node.setAttribute(key, String(value));
        });

        return node;
    }

    function point(index, total, radius) {
        const angle = index * Math.PI * 2 / total;

        return {
            x: CX + Math.sin(angle) * radius,
            y: CY - Math.cos(angle) * radius
        };
    }

    function polygonPoints(values) {
        return values.map((value, index) => {
            const p = point(
                index,
                values.length,
                RADIUS * value / 100
            );

            return `${p.x},${p.y}`;
        }).join(" ");
    }

    function knownScore(value) {
        return typeof value === "number" &&
               Number.isFinite(value) &&
               value >= 0 &&
               value <= 100;
    }

    function coverage(group) {
        const known = group.traits.filter(
            trait => knownScore(trait.score)
        ).length;

        return {
            known,
            total: group.traits.length,
            value: group.traits.length
                ? 100 * known / group.traits.length
                : 0
        };
    }

    function splitLabel(label) {
        const words = label.split(" ");
        const lines = [];
        let current = "";

        words.forEach(word => {
            if (
                current &&
                `${current} ${word}`.length > 18
            ) {
                lines.push(current);
                current = word;
            } else {
                current += current ? ` ${word}` : word;
            }
        });

        if (current) {
            lines.push(current);
        }

        return lines;
    }

    function drawRadar(axes, onSelect) {
        svg.replaceChildren();

        const total = axes.length;

        if (total < 3) {
            return;
        }

        [25, 50, 75, 100].forEach(level => {
            svg.appendChild(svgElement("polygon", {
                points: polygonPoints(
                    Array(total).fill(level)
                ),
                class: "psych-radar-ring"
            }));

            const label = svgElement("text", {
                x: CX + 7,
                y: CY - RADIUS * level / 100 + 12,
                fill: "#777d85",
                "font-size": 9
            });

            label.textContent = level;
            svg.appendChild(label);
        });

        axes.forEach((axis, index) => {
            const p = point(index, total, RADIUS);

            svg.appendChild(svgElement("line", {
                x1: CX,
                y1: CY,
                x2: p.x,
                y2: p.y,
                class: "psych-radar-axis"
            }));
        });

        const complete = axes.every(
            axis => knownScore(axis.value)
        );

        if (complete) {
            svg.appendChild(svgElement("polygon", {
                points: polygonPoints(
                    axes.map(axis => axis.value)
                ),
                class: "psych-radar-shape"
            }));
        } else {
            // Connect only neighboring known values.
            // Missing traits are never plotted as zero.

            axes.forEach((axis, index) => {
                const next = (index + 1) % total;

                if (
                    !knownScore(axis.value) ||
                    !knownScore(axes[next].value)
                ) {
                    return;
                }

                const a = point(
                    index, total,
                    RADIUS * axis.value / 100
                );

                const b = point(
                    next, total,
                    RADIUS * axes[next].value / 100
                );

                svg.appendChild(svgElement("line", {
                    x1: a.x,
                    y1: a.y,
                    x2: b.x,
                    y2: b.y,
                    stroke: "#c5ab85",
                    "stroke-width": 1.8
                }));
            });
        }

        axes.forEach((axis, index) => {

            if (knownScore(axis.value)) {
                const p = point(
                    index,
                    total,
                    RADIUS * axis.value / 100
                );

                const dot = svgElement("circle", {
                    cx: p.x,
                    cy: p.y,
                    r: 4,
                    class: "psych-radar-point"
                });

                const tooltip = svgElement("title");

                tooltip.textContent =
                    `${axis.label}: ${Math.round(axis.value)}`;

                dot.appendChild(tooltip);
                svg.appendChild(dot);
            }

            const p = point(index, total, RADIUS + 37);

            const label = svgElement("text", {
                x: p.x,
                y: p.y,
                "text-anchor": "middle",
                class: "psych-radar-label",
                tabindex: 0,
                role: "button",
                "aria-label": axis.label
            });

            const lines = splitLabel(axis.label);

            lines.forEach((line, lineIndex) => {
                const span = svgElement("tspan", {
                    x: p.x,
                    dy: lineIndex === 0
                        ? -(lines.length - 1) * 6
                        : 13
                });

                span.textContent = line;
                label.appendChild(span);
            });

            label.addEventListener("click", () => {
                onSelect(axis.key);
            });

            label.addEventListener("keydown", event => {
                if (
                    event.key === "Enter" ||
                    event.key === " "
                ) {
                    event.preventDefault();
                    onSelect(axis.key);
                }
            });

            svg.appendChild(label);
        });
    }

    function addRow(label, value, caption, action) {
        const row = document.createElement("div");
        row.className = "psych-radar-row";

        const header = document.createElement("div");
        header.className = "psych-radar-row-header";

        const name = document.createElement("button");
        name.type = "button";
        name.className = "psych-radar-row-button";
        name.textContent = label;
        name.addEventListener("click", action);

        const score = document.createElement("span");
        score.className = knownScore(value)
            ? "psych-radar-value"
            : "psych-radar-unknown";

        score.textContent = caption;

        header.append(name, score);
        row.appendChild(header);

        const bar = document.createElement("div");
        bar.className = "psych-radar-bar";

        if (knownScore(value)) {
            const fill = document.createElement("div");
            fill.className = "psych-radar-bar-fill";
            fill.style.width = `${value}%`;
            bar.appendChild(fill);
        }

        row.appendChild(bar);
        details.appendChild(row);
    }

    function revealTrait(key) {
        const card = document.getElementById(
            `psych-trait-${key}`
        );

        if (!card) {
            return;
        }

        document.querySelectorAll(
            ".psych-trait-highlight"
        ).forEach(node => {
            node.classList.remove("psych-trait-highlight");
        });

        const group = card.closest(".psych-group");

        if (group) {
            group.open = true;
        }

        const detail = card.querySelector(".psych-detail");

        if (detail) {
            detail.open = true;
        }

        card.classList.add("psych-trait-highlight");

        card.scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    }

    function renderButtons() {
        buttons.replaceChildren();

        const options = [
            {key: null, label: "Overview"},
            ...groups
        ];

        options.forEach(option => {
            const button = document.createElement("button");

            button.type = "button";
            button.className = "psych-radar-button";

            if (selected === option.key) {
                button.classList.add("active");
            }

            button.setAttribute(
                "aria-pressed",
                String(selected === option.key)
            );

            button.textContent = option.label;

            button.addEventListener("click", () => {
                selected = option.key;
                render();
            });

            buttons.appendChild(button);
        });
    }

    function renderOverview() {
        selection.textContent = "Psychological Overview";

        description.textContent =
            "Assessment coverage across the eight " +
            "psychological dimensions.";

        note.textContent =
            "This overview measures how much of each " +
            "category has been assessed, not the strength " +
            "or quality of your personality.";

        drawRadar(
            groups.map(group => ({
                key: group.key,
                label: group.label,
                value: coverage(group).value
            })),
            key => {
                selected = key;
                render();
            }
        );

        groups.forEach(group => {
            const state = coverage(group);

            addRow(
                group.label,
                state.value,
                `${state.known}/${state.total} assessed`,
                () => {
                    selected = group.key;
                    render();
                }
            );
        });
    }

    function renderGroup(group) {
        selection.textContent = group.label;

        const state = coverage(group);

        description.textContent =
            `${state.known} of ${state.total} traits assessed.`;

        note.textContent =
            "The radar shows estimated trait expression " +
            "from 0 to 100. Missing points indicate " +
            "insufficient evidence, not low expression.";

        drawRadar(
            group.traits.map(trait => ({
                key: trait.key,
                label: trait.label,
                value: trait.score
            })),
            revealTrait
        );

        group.traits.forEach(trait => {
            addRow(
                trait.label,
                trait.score,
                knownScore(trait.score)
                    ? `${Math.round(trait.score)}/100`
                    : "Unassessed",
                () => revealTrait(trait.key)
            );
        });
    }

    function render() {
        details.replaceChildren();

        renderButtons();

        const group = groups.find(
            item => item.key === selected
        );

        if (group) {
            renderGroup(group);
        } else {
            renderOverview();
        }
    }

    render();
})();
