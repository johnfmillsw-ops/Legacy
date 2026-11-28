(function () {
    "use strict";

    const root = document.getElementById("baselineApp");
    if (!root) return;

    const $ = (id) => document.getElementById(id);
    const api = root.dataset.api;
    const csrf = $("baselineCsrf").value;

    const welcome = $("baselineWelcome");
    const questionsView = $("baselineQuestions");
    const resultsView = $("baselineResults");
    const errorBox = $("baselineError");
    const statusBox = $("baselineGlobalStatus");

    const controls = [
        "baselineStart",
        "baselineBack",
        "baselineNext",
        "baselineFinish",
        "baselineSaveExit",
        "baselineRetake"
    ];

    let instrument = null;
    let assessmentId = null;
    let responses = {};
    let index = 0;
    let busy = false;

    const labels = {
        extraversion: "Extraversion",
        agreeableness: "Agreeableness",
        conscientiousness: "Conscientiousness",
        emotional_stability: "Emotional Stability",
        openness: "Openness / Imagination"
    };

    function setBusy(value) {
        busy = value;
        controls.forEach((id) => {
            const element = $(id);
            element.disabled = value;
        });
        $("baselineOptions")
            .querySelectorAll('input[type="radio"]')
            .forEach((radio) => {
                radio.disabled = value;
            });

        questionsView.setAttribute(
            "aria-busy", String(value)
        );

        if (!value && questionsView.hidden === false) {
            $("baselineBack").disabled = index === 0;
        }
    }

    function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = !message;
    }

    function show(section) {
        welcome.hidden = section !== "welcome";
        questionsView.hidden = section !== "questions";
        resultsView.hidden = section !== "results";
        showError("");
    }

    async function request(path, method, values) {
        const options = {
            method: method || "GET",
            credentials: "same-origin",
            headers: {
                "Accept": "application/json"
            }
        };

        if (options.method === "POST") {
            const body = new URLSearchParams();
            body.set("_csrf_token", csrf);
            Object.entries(values || {}).forEach(([key, value]) => {
                body.set(key, value);
            });
            options.body = body;
            options.headers["Content-Type"] =
                "application/x-www-form-urlencoded;charset=UTF-8";
        }

        const result = await fetch(api + path, options);
        const data = await result.json().catch(() => ({}));

        if (!result.ok) {
            throw new Error(
                data.error ||
                "Unable to complete the request. Please try again."
            );
        }
        return data;
    }

    function countAnswered() {
        return instrument.questions.reduce((count, question) => {
            return count + (
                Object.prototype.hasOwnProperty.call(
                    responses, String(question.id)
                ) ? 1 : 0
            );
        }, 0);
    }

    function renderProgress() {
        const answered = countAnswered();
        const total = instrument.questions.length;
        $("baselineAnsweredCount").textContent =
            answered + " of " + total + " answered";
        $("baselineProgressFill").style.width =
            (100 * answered / total) + "%";
        $("baselineProgress").setAttribute(
            "aria-valuenow", String(answered)
        );
    }

    function renderQuestion() {
        const question = instrument.questions[index];
        const id = String(question.id);

        $("baselineQuestionCount").textContent =
            "Question " + (index + 1) +
            " of " + instrument.questions.length;

        $("baselineQuestionText").textContent = question.text;
        $("baselineOptions").replaceChildren();

        Object.entries(instrument.response_options)
            .sort((a, b) => Number(a[0]) - Number(b[0]))
            .forEach(([value, label]) => {
                const wrapper = document.createElement("label");
                wrapper.className = "baseline-option";

                const radio = document.createElement("input");
                radio.type = "radio";
                radio.name = "baselineAnswer";
                radio.value = value;
                radio.disabled = busy;
                radio.checked =
                    responses[id] === Number(value);

                radio.addEventListener("change", () => {
                    if (busy) {
                        radio.checked =
                            responses[id] === Number(value);
                        return;
                    }

                    responses[id] = Number(value);
                    $("baselineSaveStatus").textContent =
                        "Answer selected. Continue to save.";
                    renderProgress();
                });

                const span = document.createElement("span");
                span.textContent = label;

                wrapper.append(radio, span);
                $("baselineOptions").append(wrapper);
            });

        $("baselineBack").disabled = busy || index === 0;
        $("baselineNext").hidden =
            index === instrument.questions.length - 1;
        $("baselineFinish").hidden =
            index !== instrument.questions.length - 1;

        $("baselineSaveStatus").textContent = "";
        renderProgress();
    }

    async function saveProgress() {
        const data = await request(
            "/" + encodeURIComponent(assessmentId) + "/save",
            "POST",
            { responses: JSON.stringify(responses) }
        );
        responses = data.assessment.responses || {};
        $("baselineSaveStatus").textContent = "Progress saved.";
    }

    async function execute(task) {
        if (busy) return;
        setBusy(true);
        showError("");
        try {
            await task();
        } catch (error) {
            showError(error.message || "An unexpected error occurred.");
        } finally {
            setBusy(false);
        }
    }

    async function begin() {
        await execute(async () => {
            const data = await request("/start", "POST");
            assessmentId = data.assessment.id;
            responses = data.assessment.responses || {};

            const firstUnanswered = instrument.questions.findIndex(
                (question) => !Object.prototype.hasOwnProperty.call(
                    responses, String(question.id)
                )
            );

            index = firstUnanswered === -1
                ? instrument.questions.length - 1
                : firstUnanswered;

            show("questions");
            statusBox.textContent =
                "Your answers are saved to your Legacy profile.";
            renderQuestion();
        });
    }

    function displayResults(scores) {
        const container = $("baselineScores");
        container.replaceChildren();

        Object.entries(labels).forEach(([key, label]) => {
            const score = scores[key];
            if (typeof score !== "number") return;

            const item = document.createElement("div");
            item.className = "baseline-score";

            const heading = document.createElement("div");
            heading.className = "baseline-score-head";

            const name = document.createElement("strong");
            name.textContent = label;

            const value = document.createElement("span");
            value.textContent = Math.round(score) + " / 100";

            heading.append(name, value);

            const track = document.createElement("div");
            track.className = "baseline-score-track";

            const fill = document.createElement("div");
            fill.className = "baseline-score-fill";
            fill.style.width = Math.max(
                0, Math.min(100, score)
            ) + "%";

            track.append(fill);
            item.append(heading, track);
            container.append(item);
        });

        show("results");
        statusBox.textContent =
            "Assessment completed and saved.";
    }

    $("baselineStart").addEventListener("click", begin);
    $("baselineRetake").addEventListener("click", begin);

    $("baselineNext").addEventListener("click", () => {
        execute(async () => {
            const id = String(instrument.questions[index].id);

            if (!Object.prototype.hasOwnProperty.call(
                responses, id
            )) {
                throw new Error(
                    "Please choose an answer before continuing."
                );
            }

            await saveProgress();
            index += 1;
            renderQuestion();
        });
    });

    $("baselineBack").addEventListener("click", () => {
        execute(async () => {
            await saveProgress();
            index = Math.max(0, index - 1);
            renderQuestion();
        });
    });

    $("baselineSaveExit").addEventListener("click", () => {
        execute(async () => {
            await saveProgress();
            window.location.assign(root.dataset.identity);
        });
    });

    $("baselineFinish").addEventListener("click", () => {
        execute(async () => {
            const missing = instrument.questions.findIndex(
                (question) => !Object.prototype.hasOwnProperty.call(
                    responses, String(question.id)
                )
            );

            if (missing !== -1) {
                index = missing;
                renderQuestion();
                throw new Error(
                    "Please answer all questions before submitting."
                );
            }

            await saveProgress();

            const data = await request(
                "/" + encodeURIComponent(assessmentId) +
                    "/complete",
                "POST"
            );

            displayResults(
                data.assessment.normalized_scores || {}
            );
        });
    });

    async function initialize() {
        try {
            const data = await request("/instrument");
            instrument = data;

            if (
                !Array.isArray(instrument.questions) ||
                instrument.questions.length !== 50 ||
                !instrument.response_options
            ) {
                throw new Error(
                    "Assessment configuration is incomplete."
                );
            }

            const latest = await request("/latest");

            if (latest.assessment) {
                const completed =
                    latest.assessment.completed_utc || "";
                $("baselinePrevious").textContent =
                    "Previous completed assessment: " +
                    completed.slice(0, 10);

                displayResults(
                    latest.assessment.normalized_scores || {}
                );
            } else {
                show("welcome");
            }

            statusBox.textContent = "";
            $("baselineStart").disabled = false;
        } catch (error) {
            showError(
                error.message ||
                "Unable to load your personality assessment."
            );
            statusBox.textContent = "";
        }
    }

    initialize();
})();
