"use strict";

(() => {

    const app = document.getElementById("cognitiveApp");

    if (!app) return;

    const $ = name =>
        document.getElementById("cognitive" + name);

    const renderer = window.LegacyCognitiveRenderer;

    const domains = {
        fluid_reasoning: "Fluid Reasoning",
        visual_spatial: "Visual-Spatial Ability",
        verbal_comprehension: "Verbal Comprehension",
        quantitative_reasoning: "Quantitative Reasoning",
        working_memory: "Working Memory",
        processing_speed: "Processing Speed"
    };

    const families = {
        abstract_matrices: "Abstract Matrices",
        logical_sequences: "Logical Sequences",
        deductive_reasoning: "Deductive Reasoning",
        mental_rotation: "Mental Rotation",
        spatial_transformation: "Spatial Transformation",
        spatial_relationships: "Spatial Relationships",
        verbal_analogies: "Verbal Analogies",
        semantic_relationships: "Semantic Relationships",
        concept_classification: "Concept Classification",
        number_sequences: "Number Sequences",
        quantitative_relationships: "Quantitative Relationships",
        mathematical_logic: "Mathematical Logic",
        sequence_recognition: "Sequence Recognition",
        spatial_memory: "Spatial Memory",
        sequence_manipulation: "Sequence Manipulation",
        symbol_comparison: "Symbol Comparison",
        visual_discrimination: "Visual Discrimination",
        pattern_matching: "Pattern Matching"
    };

    let assessment = null;
    let selectedOption = null;
    let resultId = null;
    let busy = false;
    let timer = null;
    let memoryTimer = null;
    let memoryProgress = null;
    let pendingInterruption = null;
    let loadedPreferences = null;

    const terminalStates = new Set([
        "completed",
        "interrupted",
        "abandoned"
    ]);

    function node(tag, text, className) {

        const item = document.createElement(tag);

        if (text !== undefined) {
            item.textContent = String(text);
        }

        if (className) {
            item.className = className;
        }

        return item;
    }

    function button(text, handler) {

        const item = node(
            "button",
            text,
            "legacy-button"
        );

        item.type = "button";
        item.addEventListener("click", handler);

        return item;
    }

    function activeAssessment() {

        return assessment
            && !terminalStates.has(assessment.state);
    }

    function error(message) {

        $("Error").textContent = message;
        $("Error").hidden = !message;
    }

    function clearTimers() {

        clearInterval(timer);
        clearTimeout(memoryTimer);
        clearInterval(memoryProgress);

        timer = null;
        memoryTimer = null;
        memoryProgress = null;
    }

    function clearQuestion() {

        $("MemoryStimulus").replaceChildren();
        $("Stimulus").replaceChildren();
        $("Options").replaceChildren();
        $("Prompt").textContent = "";

        selectedOption = null;
        $("Submit").disabled = true;
    }

    function showPage(name) {

        [
            "Welcome",
            "History",
            "Administration",
            "Results"
        ].forEach(section => {

            $(section).hidden =
                section !== name
                && !(
                    name === "Welcome"
                    && section === "History"
                );
        });
    }

    async function api(path, fields = null) {

        const options = {
            credentials: "same-origin",
            cache: "no-store",
            headers: {
                Accept: "application/json"
            }
        };

        if (fields !== null) {

            options.method = "POST";

            const body = new URLSearchParams();

            body.set(
                "_csrf_token",
                $("Csrf").value
            );

            Object.entries(fields).forEach(
                ([key, value]) => {

                    if (
                        value !== null
                        && value !== undefined
                    ) {
                        body.set(key, String(value));
                    }
                }
            );

            options.body = body;
        }

        const response = await fetch(
            app.dataset.api + path,
            options
        );

        let data;

        try {
            data = await response.json();
        } catch {
            throw new Error(
                "The server returned an unexpected response."
            );
        }

        if (!response.ok) {

            const failure = new Error(
                data.error || "Request failed."
            );

            failure.status = response.status;

            throw failure;
        }

        return data;
    }

    function lockControls(locked) {

        [
            "BeginBlock",
            "Advance",
            "Interrupt"
        ].forEach(name => {
            $(name).disabled = locked;
        });

        $("Submit").disabled =
            locked || !selectedOption;

        $("Options").querySelectorAll(
            "button"
        ).forEach(item => {
            item.disabled = locked;
        });
    }

    async function recoverAssessment() {

        clearTimers();
        clearQuestion();

        if (!assessment) return;

        const id = assessment.session_id;

        const response = await api(
            `/${encodeURIComponent(id)}/status`
        );

        assessment = response.assessment;

        if (assessment.state === "completed") {

            await showResults(id);
            return;
        }

        if (terminalStates.has(assessment.state)) {

            assessment = null;
            await loadHistory();
            return;
        }

        const interrupted = await api(
            `/${encodeURIComponent(id)}/action`,
            {
                action: "interrupt",
                revision: assessment.revision,
                interruption_reason:
                    "network_interruption"
            }
        );

        assessment = interrupted.assessment;

        if (assessment.state === "completed") {

            await showResults(id);
            return;
        }

        assessment = null;

        await loadHistory();

        error(
            "The assessment was ended because "
            + "administration continuity was lost."
        );
    }

    async function performAction(
        action,
        fields = {}
    ) {

        if (busy || !activeAssessment()) return;

        busy = true;

        error("");
        lockControls(true);

        const id = assessment.session_id;

        try {

            const response = await api(
                `/${encodeURIComponent(id)}/action`,
                {
                    action,
                    revision: assessment.revision,
                    ...fields
                }
            );

            assessment = response.assessment;

            if (
                pendingInterruption
                && activeAssessment()
            ) {

                const reason = pendingInterruption;
                pendingInterruption = null;

                const interrupted = await api(
                    `/${encodeURIComponent(id)}/action`,
                    {
                        action: "interrupt",
                        revision: assessment.revision,
                        interruption_reason: reason
                    }
                );

                assessment = interrupted.assessment;
            }

            if (assessment.state === "answered" && assessment.mode === "timed_queue" && !pendingInterruption) {
                const advanced = await api(`/${encodeURIComponent(id)}/action`, {
                    action: "advance", revision: assessment.revision
                });
                assessment = advanced.assessment;
            }
            if (pendingInterruption && activeAssessment()) {
                const reason = pendingInterruption;
                pendingInterruption = null;
                const stopped = await api(`/${encodeURIComponent(id)}/action`, {
                    action: "interrupt", revision: assessment.revision,
                    interruption_reason: reason
                });
                assessment = stopped.assessment;
            }
            await renderState();

        } catch (failure) {

            error(failure.message);

            try {
                await recoverAssessment();
            } catch (recoveryFailure) {

                error(
                    "Assessment continuity was lost. "
                    + "Reload the page to recover its status. "
                    + recoveryFailure.message
                );

                clearTimers();
                clearQuestion();
            }

        } finally {

            busy = false;
            lockControls(false);

            if (
                pendingInterruption
                && activeAssessment()
            ) {

                const reason = pendingInterruption;
                pendingInterruption = null;

                void interrupt(reason);
            }
        }
    }

    async function interrupt(reason) {

        if (!activeAssessment()) return;

        clearTimers();
        clearQuestion();

        if (busy) {

            pendingInterruption = reason;
            return;
        }

        await performAction(
            "interrupt",
            {
                interruption_reason: reason
            }
        );
    }

    function startCountdown(deadline) {

        if (!Number.isFinite(deadline)) return;

        $("Timer").hidden = false;

        const localDeadline = performance.now() + Math.max(0, deadline - Number(assessment.server_now_ms));

        function update() {

            const remaining = Math.max(
                0,
                localDeadline - performance.now()
            );

            const seconds = Math.ceil(
                remaining / 1000
            );

            const minutes = Math.floor(
                seconds / 60
            );

            $("TimerValue").textContent =
                String(minutes).padStart(2, "0")
                + ":"
                + String(seconds % 60).padStart(2, "0");

            $("Timer").classList.toggle(
                "is-expiring",
                seconds <= 15
            );

            if (remaining === 0 && !busy) {

                clearInterval(timer);

                clearQuestion();

                void performAction("tick");
            }
        }

        timer = setInterval(update, 100);

        update();
    }

    function startMemory(question) {

        renderer.renderMemory(
            question,
            $("MemoryStimulus")
        );

        const duration = Number(
            question.exposure_duration_ms
            || question.presentation_ms
        );

        if (
            !Number.isFinite(duration)
            || duration <= 0
        ) {
            throw new Error(
                "Invalid memory exposure duration."
            );
        }

        const started = performance.now();

        $("MemoryProgress").value = 100;

        memoryProgress = setInterval(() => {

            const elapsed =
                performance.now() - started;

            $("MemoryProgress").value =
                Math.max(
                    0,
                    100 * (1 - elapsed / duration)
                );

        }, 40);

        const questionId = question.id;

        memoryTimer = setTimeout(() => {

            $("MemoryStimulus").replaceChildren();

            clearInterval(memoryProgress);

            $("MemoryProgress").value = 0;

            void performAction(
                "finish_memory_exposure",
                {
                    question_id: questionId
                }
            );

        }, duration);
    }

    async function renderState() {

        clearTimers();
        clearQuestion();

        if (!assessment) return;

        if (assessment.state === "completed") {

            const id = assessment.session_id;

            assessment = null;

            await showResults(id);

            return;
        }

        if (terminalStates.has(assessment.state)) {

            assessment = null;

            await loadHistory();

            error(
                "The assessment ended before completion. "
                + "No composite score was generated."
            );

            return;
        }

        showPage("Administration");

        [
            "BlockIntro",
            "MemoryStage",
            "QuestionStage",
            "AnsweredStage",
            "Timer"
        ].forEach(name => {
            $(name).hidden = true;
        });

        $("Domain").textContent =
            domains[assessment.domain]
            || "Cognitive Assessment";

        $("ProgressText").textContent =
            `Section ${assessment.block_number}`
            + ` of ${assessment.total_blocks}`
            + ` · Item ${assessment.item_number}`
            + ` of ${assessment.block_item_count}`;

        $("Progress").max =
            assessment.total_blocks;

        $("Progress").value =
            Math.max(
                0,
                assessment.block_number - 1
            );

        $("AdministrationStatus").textContent = "";

        switch (assessment.state) {

            case "ready":

                $("BlockIntro").hidden = false;

                $("BlockTitle").textContent =
                    families[assessment.family]
                    || domains[assessment.domain];

                if (
                    assessment.domain
                    === "processing_speed"
                ) {

                    $("BlockInstructions").textContent =
                        "You have two minutes. "
                        + "Answer as quickly and accurately "
                        + "as possible.";

                } else if (
                    assessment.domain
                    === "working_memory"
                ) {

                    $("BlockInstructions").textContent =
                        "Study each stimulus carefully. "
                        + "It will disappear automatically "
                        + "before the answer choices appear.";

                } else {

                    $("BlockInstructions").textContent =
                        "Choose the best answer to each "
                        + "question. Submitted answers "
                        + "cannot be changed.";
                }

                break;

            case "memorize":

                $("MemoryStage").hidden = false;

                if (!assessment.question) {
                    throw new Error(
                        "Memory stimulus unavailable."
                    );
                }

                startMemory(assessment.question);

                break;

            case "respond":

                $("QuestionStage").hidden = false;
                $("Submit").hidden = assessment.mode === "timed_queue";

                if (!assessment.question) {
                    throw new Error(
                        "Question presentation unavailable."
                    );
                }

                renderer.renderQuestion(
                    assessment.question,
                    $("Prompt"),
                    $("Stimulus"),
                    $("Options"),
                    optionId => {

                        selectedOption = optionId;

                        $("Submit").disabled = busy;
                        if (assessment.mode === "timed_queue" && !busy) {
                            void performAction("submit_response", {
                                question_id: assessment.question.id,
                                selected_option_id: optionId
                            });
                        }
                    }
                );

                break;

            case "answered":

                $("AnsweredStage").hidden = false;

                break;

            default:

                throw new Error(
                    "Unknown assessment state."
                );
        }

        if (
            assessment.block_deadline_ms !== null
            && assessment.block_deadline_ms !== undefined
            && assessment.state !== "ready"
        ) {

            startCountdown(
                Number(
                    assessment.block_deadline_ms
                )
            );
        }
    }

    async function loadHistory() {

        showPage("Welcome");

        $("Start").disabled = true;

        $("HistoryList").textContent =
            "Loading assessment history...";

        const response = await api("/history");

        const records = response.assessments || [];

        $("HistoryList").replaceChildren();

        let hasActive = false;

        records.forEach(record => {

            const row = node(
                "div",
                undefined,
                "cognitive-history-row"
            );

            const description = node("div");

            const date = record.created_utc
                ? new Date(
                    record.created_utc
                ).toLocaleDateString()
                : "Assessment";

            description.appendChild(
                node("strong", date)
            );

            description.appendChild(
                node(
                    "p",
                    record.status,
                    "cognitive-muted"
                )
            );

            row.appendChild(description);

            const actions = node("div");

            if (record.status === "completed") {

                actions.appendChild(
                    button(
                        "View results",
                        () => safely(
                            () => showResults(record.assessment_id)
                        )
                    )
                );

            } else if (
                !terminalStates.has(record.status)
            ) {

                hasActive = true;

                actions.appendChild(
                    button(
                        "End unfinished assessment",
                        () => safely(async () => {

                            const status = await api(
                                `/${encodeURIComponent(record.assessment_id)}/status`
                            );

                            assessment =
                                status.assessment;

                            await interrupt("page_reload");
                        })
                    )
                );

            } else {

                actions.appendChild(
                    button(
                        "Delete",
                        () => safely(
                            () => deleteRecord(record.assessment_id)
                        )
                    )
                );
            }

            row.appendChild(actions);

            $("HistoryList").appendChild(row);
        });

        if (!records.length) {

            $("HistoryList").appendChild(
                node(
                    "p",
                    "No previous assessments.",
                    "cognitive-muted"
                )
            );
        }

        $("Start").dataset.active =
            String(hasActive);

        $("Start").disabled =
            hasActive
            || !$("Acknowledgement").checked;

        $("GlobalStatus").textContent =
            hasActive
                ? "End the unfinished assessment "
                  + "before beginning another."
                : "";
    }

    async function showResults(id) {

        const response = await api(
            `/${encodeURIComponent(id)}/results`
        );

        const preferenceResponse = await api(
            "/preferences"
        );

        const results = response.results;

        loadedPreferences =
            preferenceResponse.preferences;

        resultId = id;

        $("CompositeScore").textContent =
            results.estimated_iq === null
                ? "Unavailable"
                : Math.round(results.estimated_iq);

        $("DomainResults").replaceChildren();

        Object.entries(domains).forEach(
            ([key, label]) => {

                const result =
                    results.domain_results[key];

                if (!result) return;

                const card = node(
                    "article",
                    undefined,
                    "cognitive-result-card"
                );

                card.appendChild(
                    node("h3", label)
                );

                if (key === "processing_speed") {

                    card.appendChild(
                        node(
                            "strong",
                            Number(
                                result.correct_per_minute
                            ).toFixed(2)
                        )
                    );

                    card.appendChild(
                        node(
                            "p",
                            "Correct responses per minute",
                            "cognitive-muted"
                        )
                    );

                } else {

                    card.appendChild(
                        node(
                            "strong",
                            Math.round(
                                result.theoretical_scale_score
                            )
                        )
                    );

                    card.appendChild(
                        node(
                            "p",
                            `${result.correct_count} of `
                            + `${result.item_count} correct`,
                            "cognitive-muted"
                        )
                    );

                    card.appendChild(
                        node(
                            "p",
                            "Theoretical domain estimate",
                            "cognitive-muted cognitive-small"
                        )
                    );
                }

                $("DomainResults").appendChild(card);
            }
        );

        const p = loadedPreferences;

        $("ModelIntegration").checked =
            p.model_integration_enabled
            && p.model_assessment_id === id;

        $("DisplayHome").checked =
            p.display_on_home
            && p.display_assessment_id === id;

        $("DisplayPage").checked =
            p.display_on_cognitive_page
            && p.display_assessment_id === id;

        $("PreferenceStatus").textContent = "";

        showPage("Results");
    }

    async function savePreferences() {

        if (!resultId || !loadedPreferences) return;

        const id = resultId;
        const previous = loadedPreferences;

        const model = $("ModelIntegration").checked;
        const home = $("DisplayHome").checked;
        const page = $("DisplayPage").checked;

        $("SavePreferences").disabled = true;

        try {

            if (
                model
                || previous.model_assessment_id === id
            ) {

                const response = await api(
                    "/preferences/model",
                    {
                        enabled: model,
                        assessment_id: id
                    }
                );

                loadedPreferences =
                    response.preferences;
            }

            if (
                home
                || page
                || previous.display_assessment_id === id
            ) {

                const response = await api(
                    "/preferences/display",
                    {
                        display_on_home: home,
                        display_on_cognitive_page: page,
                        assessment_id: id
                    }
                );

                loadedPreferences =
                    response.preferences;
            }

            $("PreferenceStatus").textContent =
                "Preferences saved.";

        } finally {

            $("SavePreferences").disabled = false;
        }
    }

    async function deleteRecord(id) {

        if (!window.confirm(
            "Permanently delete this assessment "
            + "and its associated results and responses?"
        )) return;

        await api(
            `/${encodeURIComponent(id)}/delete`,
            {}
        );

        resultId = null;

        await loadHistory();
    }

    async function safely(operation) {

        error("");

        try {
            await operation();
        } catch (failure) {
            error(failure.message);
        }
    }

    $("Acknowledgement").addEventListener(
        "change",
        () => {

            $("Start").disabled =
                !$("Acknowledgement").checked
                || $("Start").dataset.active === "true";
        }
    );

    $("Start").addEventListener("click", () => {

        if (busy || !$("Acknowledgement").checked) {
            return;
        }

        void safely(async () => {

            busy = true;
            $("Start").disabled = true;

            try {

                const response = await api(
                    "/start",
                    {}
                );

                assessment = response.assessment;

                await renderState();

            } finally {

                busy = false;
                lockControls(false);
            }
        });
    });

    $("BeginBlock").addEventListener(
        "click",
        () => performAction("begin_block")
    );

    $("Submit").addEventListener("click", () => {

        if (!selectedOption || !assessment?.question) {
            return;
        }

        void performAction(
            "submit_response",
            {
                question_id: assessment.question.id,
                selected_option_id: selectedOption
            }
        );
    });

    $("Advance").addEventListener(
        "click",
        () => performAction("advance")
    );

    $("Interrupt").addEventListener("click", () => {

        if (window.confirm(
            "End this assessment? "
            + "An incomplete assessment cannot be scored."
        )) {

            void interrupt("user_requested_break");
        }
    });

    $("Return").addEventListener(
        "click",
        () => safely(loadHistory)
    );

    $("SavePreferences").addEventListener(
        "click",
        () => safely(savePreferences)
    );

    $("Delete").addEventListener(
        "click",
        () => safely(
            () => deleteRecord(resultId)
        )
    );

    document.addEventListener(
        "visibilitychange",
        () => {

            if (document.hidden && activeAssessment()) {

                void interrupt("visibility_lost");
            }
        }
    );

    window.addEventListener("blur", () => {

        if (
            activeAssessment()
            && assessment.state !== "ready"
        ) {

            void interrupt("window_focus_lost");
        }
    });

    window.addEventListener("offline", () => {

        if (activeAssessment()) {

            void interrupt("network_interruption");
        }
    });

    window.addEventListener("beforeunload", event => {

        if (activeAssessment()) {

            event.preventDefault();
            event.returnValue = "";
        }
    });

    window.addEventListener("pagehide", () => {

        if (!activeAssessment()) return;

        const body = new URLSearchParams({
            _csrf_token: $("Csrf").value,
            action: "interrupt",
            revision: String(assessment.revision),
            interruption_reason: "page_reload"
        });

        navigator.sendBeacon(
            app.dataset.api
            + "/"
            + encodeURIComponent(assessment.session_id)
            + "/action",
            body
        );
    });

    void safely(loadHistory);

})();
