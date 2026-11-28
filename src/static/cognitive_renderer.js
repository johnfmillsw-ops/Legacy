"use strict";

window.LegacyCognitiveRenderer = (() => {

    const SVG_NS = "http://www.w3.org/2000/svg";

    function element(tag, className, text) {
        const node = document.createElement(tag);

        if (className) {
            node.className = className;
        }

        if (text !== undefined) {
            node.textContent = String(text);
        }

        return node;
    }

    function svgElement(tag, attributes = {}) {
        const node = document.createElementNS(
            SVG_NS,
            tag
        );

        Object.entries(attributes).forEach(
            ([key, value]) => {
                node.setAttribute(key, String(value));
            }
        );

        return node;
    }

    function svgCanvas(width, height) {
        return svgElement("svg", {
            viewBox: `0 0 ${width} ${height}`,
            width,
            height,
            class: "cognitive-svg",
            "aria-hidden": "true"
        });
    }

    function polygonPoints(count, radius, angle = -90) {
        return Array.from(
            { length: count },
            (_, index) => {
                const radians = (
                    angle + index * 360 / count
                ) * Math.PI / 180;

                return [
                    Math.cos(radians) * radius,
                    Math.sin(radians) * radius
                ].join(",");
            }
        ).join(" ");
    }

    function shape(
        name,
        x,
        y,
        size,
        orientation = 0,
        filled = true
    ) {
        const group = svgElement("g", {
            transform:
                `translate(${x} ${y}) rotate(${orientation})`,
            fill: filled ? "currentColor" : "none",
            stroke: "currentColor",
            "stroke-width": 1.8,
            "stroke-linejoin": "round"
        });

        const r = size / 2;
        let node;

        switch (name) {

            case "circle":
                node = svgElement("circle", {
                    cx: 0,
                    cy: 0,
                    r
                });
                break;

            case "square":
                node = svgElement("rect", {
                    x: -r,
                    y: -r,
                    width: size,
                    height: size
                });
                break;

            case "triangle":
                node = svgElement("polygon", {
                    points: polygonPoints(3, r)
                });
                break;

            case "pentagon":
                node = svgElement("polygon", {
                    points: polygonPoints(5, r)
                });
                break;

            case "diamond":
                node = svgElement("polygon", {
                    points:
                        `0,${-r} ${r},0 0,${r} ${-r},0`
                });
                break;

            case "arrow":
                node = svgElement("polygon", {
                    points: [
                        `0,${-r}`,
                        `${r},0`,
                        `${r / 3},0`,
                        `${r / 3},${r}`,
                        `${-r / 3},${r}`,
                        `${-r / 3},0`,
                        `${-r},0`
                    ].join(" ")
                });
                break;

            case "cross":
                node = svgElement("polygon", {
                    points: [
                        [-r / 3, -r],
                        [r / 3, -r],
                        [r / 3, -r / 3],
                        [r, -r / 3],
                        [r, r / 3],
                        [r / 3, r / 3],
                        [r / 3, r],
                        [-r / 3, r],
                        [-r / 3, r / 3],
                        [-r, r / 3],
                        [-r, -r / 3],
                        [-r / 3, -r / 3]
                    ].map(p => p.join(",")).join(" ")
                });
                break;

            case "star":
                node = svgElement("polygon", {
                    points: Array.from(
                        { length: 10 },
                        (_, i) => {
                            const angle =
                                (-90 + i * 36)
                                * Math.PI / 180;

                            const radius =
                                i % 2 === 0
                                    ? r
                                    : r * 0.42;

                            return [
                                Math.cos(angle) * radius,
                                Math.sin(angle) * radius
                            ].join(",");
                        }
                    ).join(" ")
                });
                break;

            default:
                throw new Error(
                    "Unsupported visual shape: " + name
                );
        }

        group.appendChild(node);

        return group;
    }

    function visualCell(cell) {
        const svg = svgCanvas(100, 100);

        if (cell === null) {
            const mark = svgElement("text", {
                x: 50,
                y: 64,
                "text-anchor": "middle",
                "font-size": 42,
                fill: "currentColor"
            });

            mark.textContent = "?";
            svg.appendChild(mark);

            return svg;
        }

        const positions = {
            1: [[50, 50]],
            2: [[28, 50], [72, 50]],
            3: [[50, 26], [28, 72], [72, 72]],
            4: [[28, 28], [72, 28], [28, 72], [72, 72]]
        };

        const layout = positions[cell.quantity];

        if (!layout) {
            throw new Error(
                "Unsupported visual quantity."
            );
        }

        layout.forEach(([x, y]) => {
            svg.appendChild(
                shape(
                    cell.shape,
                    x,
                    y,
                    cell.quantity === 1 ? 48 : 28,
                    cell.orientation,
                    cell.fill === "solid"
                )
            );
        });

        return svg;
    }

    function matrix(stimulus) {
        const container = element(
            "div",
            "cognitive-matrix"
        );

        container.style.gridTemplateColumns =
            `repeat(${stimulus.columns}, minmax(0, 1fr))`;

        stimulus.cells.forEach(cell => {
            const tile = element(
                "div",
                "cognitive-matrix-cell"
            );

            tile.appendChild(visualCell(cell));
            container.appendChild(tile);
        });

        return container;
    }

    function coordinateShape(points, extent) {

        const size = 120;
        const svg = svgCanvas(size, size);
        const unit = 96 / extent;

        const maxX = Math.max(
            ...points.map(point => point[0])
        );

        const maxY = Math.max(
            ...points.map(point => point[1])
        );

        const offsetX =
            (size - (maxX + 1) * unit) / 2;

        const offsetY =
            (size - (maxY + 1) * unit) / 2;

        points.forEach(([x, y]) => {
            svg.appendChild(
                svgElement("rect", {
                    x: offsetX + x * unit,
                    y: offsetY + y * unit,
                    width: unit,
                    height: unit,
                    fill: "currentColor",
                    stroke: "#242424",
                    "stroke-width": 1.2
                })
            );
        });

        return svg;
    }

    function highlightedGrid(size, positions) {
        const svg = svgCanvas(120, 120);

        const gap = 2;
        const cell = 108 / size;

        const highlighted = new Set(positions);

        for (let index = 0;
             index < size * size;
             index++) {

            const row = Math.floor(index / size);
            const column = index % size;

            svg.appendChild(
                svgElement("rect", {
                    x: 6 + column * cell,
                    y: 6 + row * cell,
                    width: cell - gap,
                    height: cell - gap,
                    rx: 1,
                    fill: highlighted.has(index)
                        ? "currentColor"
                        : "none",
                    stroke: "currentColor",
                    "stroke-opacity": 0.65,
                    "stroke-width": 1
                })
            );
        }

        return svg;
    }

    function symbolSequence(symbols) {
        const unit = 34;

        const svg = svgCanvas(
            symbols.length * unit + 12,
            46
        );

        symbols.forEach((symbol, index) => {
            svg.appendChild(
                shape(
                    symbol,
                    23 + index * unit,
                    23,
                    22
                )
            );
        });

        return svg;
    }

    function textSequence(values) {
        const container = element(
            "div",
            "cognitive-sequence"
        );

        values.forEach(value => {
            container.appendChild(
                element(
                    "span",
                    "cognitive-sequence-item",
                    value
                )
            );
        });

        return container;
    }

    function parseOption(option) {
        return typeof option.value === "string"
            ? JSON.parse(option.value)
            : option.value;
    }

    function spatialExtent(question) {

        const points = [
            ...question.stimulus.points
        ];

        question.options.forEach(option => {
            points.push(...parseOption(option));
        });

        return Math.max(
            ...points.flat()
        ) + 1;
    }

    function renderStimulus(question, target) {

        target.replaceChildren();

        const stimulus = question.stimulus;

        if (!stimulus) {
            return;
        }

        let content;

        switch (stimulus.type) {

            case "visual_matrix":
                content = matrix(stimulus);
                break;

            case "spatial_object":
                content = coordinateShape(
                    stimulus.points,
                    spatialExtent(question)
                );
                break;

            case "deductive_premises":
                content = element(
                    "div",
                    "cognitive-premises"
                );

                stimulus.premises.forEach(premise => {
                    content.appendChild(
                        element("p", "", premise)
                    );
                });
                break;

            case "symbol_sequence":
                content = textSequence([
                    ...stimulus.terms,
                    ...(stimulus.missing ? ["?"] : [])
                ]);
                break;

            case "speed_symbol_comparison":
            case "speed_pattern_matching":
                content = symbolSequence(
                    stimulus.reference
                );
                break;

            case "speed_visual_discrimination":
                content = highlightedGrid(
                    stimulus.grid_size,
                    stimulus.reference
                );
                break;

            case "spatial_navigation":
            case "verbal_analogy":
            case "semantic_relationship":
            case "concept_classification":

                // The full task is already in the prompt.
                // Do not add diagrams that reveal answers.

                return;

            default:
                throw new Error(
                    "Unsupported stimulus: "
                    + stimulus.type
                );
        }

        target.appendChild(content);
    }

    function renderMemory(question, target) {

        target.replaceChildren();

        if (question.stage !== "memorize") {
            throw new Error(
                "Invalid memory presentation stage."
            );
        }

        target.appendChild(
            element(
                "p",
                "cognitive-memory-instruction",
                question.instruction
            )
        );

        if (question.response_instruction) {
            target.appendChild(
                element(
                    "p",
                    "cognitive-memory-instruction",
                    question.response_instruction
                )
            );
        }

        if (question.type === "memory_grid") {
            target.appendChild(
                highlightedGrid(
                    question.grid_size,
                    question.memorize
                )
            );

        } else if (
            question.type === "memory_sequence"
            || question.type === "memory_manipulation"
        ) {
            target.appendChild(
                textSequence(question.memorize)
            );

        } else {
            throw new Error(
                "Unsupported memory stimulus."
            );
        }
    }

    function renderOption(question, option) {

        const stimulus = question.stimulus || {};

        const format =
            question.option_format
            || stimulus.option_format;

        switch (format) {

            case "visual_cell_json":
                return visualCell(
                    parseOption(option)
                );

            case "coordinate_shape_json":
                return coordinateShape(
                    parseOption(option),
                    spatialExtent(question)
                );

            case "symbol_sequence_json":
                return symbolSequence(
                    parseOption(option)
                );

            case "speed_grid_json":
                return highlightedGrid(
                    stimulus.grid_size,
                    parseOption(option)
                );

            case "memory_grid_json":
                return highlightedGrid(
                    question.grid_size,
                    parseOption(option)
                );

            case undefined:
            case null:
                return element(
                    "span",
                    "cognitive-option-text",
                    option.value
                );

            default:
                throw new Error(
                    "Unsupported option format: "
                    + format
                );
        }
    }

    function renderQuestion(
        question,
        promptTarget,
        stimulusTarget,
        optionsTarget,
        onSelect
    ) {

        promptTarget.textContent = question.prompt;

        renderStimulus(
            question,
            stimulusTarget
        );

        optionsTarget.replaceChildren();

        const format =
            question.option_format
            || question.stimulus?.option_format;

        optionsTarget.classList.toggle(
            "cognitive-visual-options",
            [
                "visual_cell_json",
                "coordinate_shape_json",
                "speed_grid_json",
                "memory_grid_json"
            ].includes(format)
        );

        question.options.forEach(option => {

            const button = element(
                "button",
                "cognitive-option"
            );

            button.type = "button";

            button.setAttribute(
                "aria-pressed",
                "false"
            );

            button.appendChild(
                element(
                    "span",
                    "cognitive-option-letter",
                    option.id
                )
            );

            button.appendChild(
                renderOption(question, option)
            );

            button.addEventListener("click", () => {

                optionsTarget.querySelectorAll(
                    "button"
                ).forEach(item => {

                    item.classList.remove(
                        "is-selected"
                    );

                    item.setAttribute(
                        "aria-pressed",
                        "false"
                    );
                });

                button.classList.add(
                    "is-selected"
                );

                button.setAttribute(
                    "aria-pressed",
                    "true"
                );

                onSelect(option.id);
            });

            optionsTarget.appendChild(button);
        });
    }

    return Object.freeze({
        renderQuestion,
        renderMemory
    });

})();
