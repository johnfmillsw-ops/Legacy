
document.addEventListener("DOMContentLoaded", () => {

    const recordButton = document.getElementById("voiceRecord");

    if (!recordButton) return;

    const pauseButton = document.getElementById("voicePause");
    const stopButton = document.getElementById("voiceStop");
    const saveButton = document.getElementById("voiceSave");
    const discardButton = document.getElementById("voiceDiscard");

    const titleInput = document.getElementById("voiceTitle");
    const fileInput = document.getElementById("voiceFile");

    const status = document.getElementById("voiceStatus");
    const timer = document.getElementById("voiceTimer");
    const message = document.getElementById("voiceMessage");

    const preview = document.getElementById("voicePreview");
    const playback = document.getElementById("voicePlayback");

    const canvas = document.getElementById("voiceWaveform");
    const canvasContext = canvas.getContext("2d");

    const historyList = document.getElementById("voiceHistoryList");
    const historyMessage = document.getElementById("voiceHistoryMessage");
    const refreshHistoryButton = document.getElementById("voiceRefreshHistory");

    const reviewPanel = document.getElementById("voiceJournalReview");
    const reviewTitle = document.getElementById("voiceReviewTitle");
    const reviewStatus = document.getElementById("voiceReviewStatus");
    const reviewMetadata = document.getElementById("voiceReviewMetadata");
    const reviewAudio = document.getElementById("voiceReviewAudio");
    const reviewMessage = document.getElementById("voiceReviewMessage");

    const transcriptSection = document.getElementById("voiceTranscriptSection");
    const transcriptEditor = document.getElementById("voiceTranscriptEditor");
    const originalTranscript = document.getElementById("voiceOriginalTranscript");

    const closeReviewButton = document.getElementById("voiceCloseReview");
    const saveTranscriptButton = document.getElementById("voiceSaveTranscript");
    const approveTranscriptButton = document.getElementById("voiceApproveTranscript");

    const MAX_DURATION = 60 * 60 * 1000;
    const MAX_FILE_SIZE = 100 * 1024 * 1024;

    let recorder = null;
    let stream = null;
    let audioContext = null;
    let analyser = null;

    let chunks = [];
    let audioBlob = null;
    let audioURL = null;
    let selectedFilename = null;

    let startedAt = 0;
    let elapsedBeforePause = 0;

    let timerInterval = null;
    let animationFrame = null;

    let busy = false;
    let reviewBusy = false;
    let historyBusy = false;

    let activeJournal = null;
    let reviewRequestId = 0;
    let historyTimer = null;


    // --------------------------------------------------
    // Messages and API helpers
    // --------------------------------------------------

    function setMessage(text, isError = false) {

        message.textContent = text;

        message.style.color = isError
            ? "#f87171"
            : "#94a3b8";
    }


    function setReviewMessage(text, isError = false) {

        reviewMessage.textContent = text;

        reviewMessage.style.color = isError
            ? "#f87171"
            : "#94a3b8";
    }


    function getCsrfToken() {

        const token = document.querySelector(
            'input[name="_csrf_token"]'
        )?.value;

        if (!token) {
            throw new Error("Security token unavailable.");
        }

        return token;
    }


    async function apiRequest(url, options = {}) {

        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
        });

        const result = await response.json().catch(() => ({}));

        if (!response.ok) {

            throw new Error(
                result.error || `Request failed (${response.status}).`
            );
        }

        return result;
    }


    // --------------------------------------------------
    // Recording timer
    // --------------------------------------------------

    function formatTime(milliseconds) {

        const totalSeconds = Math.max(
            0,
            Math.floor(milliseconds / 1000)
        );

        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;

        return [hours, minutes, seconds]
            .map(value => String(value).padStart(2, "0"))
            .join(":");
    }


    function elapsedTime() {

        if (recorder?.state === "recording") {

            return elapsedBeforePause
                + performance.now()
                - startedAt;
        }

        return elapsedBeforePause;
    }


    function updateTimer() {

        const elapsed = elapsedTime();

        timer.textContent = formatTime(elapsed);

        if (elapsed >= MAX_DURATION) {

            stopRecording();

            setMessage(
                "Maximum recording duration reached."
            );
        }
    }


    function startTimer() {

        stopTimer();

        timerInterval = setInterval(updateTimer, 200);
    }


    function stopTimer() {

        if (timerInterval !== null) {

            clearInterval(timerInterval);
            timerInterval = null;
        }
    }


    // --------------------------------------------------
    // Audio waveform
    // --------------------------------------------------

    function drawIdleWaveform() {

        canvasContext.clearRect(
            0, 0, canvas.width, canvas.height
        );

        canvasContext.beginPath();
        canvasContext.strokeStyle = "#475569";
        canvasContext.lineWidth = 2;

        canvasContext.moveTo(0, canvas.height / 2);

        canvasContext.lineTo(
            canvas.width,
            canvas.height / 2
        );

        canvasContext.stroke();
    }


    function drawWaveform() {

        if (!analyser) return;

        const samples = new Uint8Array(analyser.fftSize);

        analyser.getByteTimeDomainData(samples);

        canvasContext.clearRect(
            0, 0, canvas.width, canvas.height
        );

        canvasContext.beginPath();
        canvasContext.strokeStyle = "#60a5fa";
        canvasContext.lineWidth = 2;

        const sliceWidth = canvas.width / samples.length;

        for (let i = 0; i < samples.length; i++) {

            const x = i * sliceWidth;

            const y = (samples[i] / 128)
                * canvas.height / 2;

            if (i === 0) {

                canvasContext.moveTo(x, y);

            } else {

                canvasContext.lineTo(x, y);
            }
        }

        canvasContext.stroke();

        animationFrame = requestAnimationFrame(drawWaveform);
    }


    function stopWaveform() {

        if (animationFrame !== null) {

            cancelAnimationFrame(animationFrame);
            animationFrame = null;
        }

        drawIdleWaveform();
    }


    // --------------------------------------------------
    // Microphone management
    // --------------------------------------------------

    function releaseMicrophone() {

        stopWaveform();

        if (stream) {

            stream.getTracks().forEach(track => track.stop());

            stream = null;
        }

        if (audioContext) {

            audioContext.close().catch(() => {});

            audioContext = null;
        }

        analyser = null;
    }


    function supportedMimeType() {

        const types = [
            "audio/webm;codecs=opus",
            "audio/mp4",
            "audio/webm",
            "audio/ogg;codecs=opus",
        ];

        return types.find(type =>
            MediaRecorder.isTypeSupported(type)
        ) || "";
    }


    // --------------------------------------------------
    // Recording preview
    // --------------------------------------------------

    function clearPreview() {

        playback.pause();
        playback.removeAttribute("src");
        playback.load();

        if (audioURL) {

            URL.revokeObjectURL(audioURL);
            audioURL = null;
        }

        audioBlob = null;
        selectedFilename = null;

        preview.hidden = true;
    }


    function showPreview(blob) {

        audioBlob = blob;

        audioURL = URL.createObjectURL(blob);

        playback.src = audioURL;

        preview.hidden = false;

        status.textContent = "Recording ready";

        const size = (blob.size / 1024 / 1024).toFixed(2);

        setMessage(`Audio ready (${size} MB).`);
    }


    function resetControls() {

        recordButton.disabled = false;
        fileInput.disabled = false;

        pauseButton.hidden = true;
        pauseButton.disabled = false;
        pauseButton.textContent = "Pause";

        stopButton.hidden = true;

        busy = false;
    }


    // --------------------------------------------------
    // Start recording
    // --------------------------------------------------

    async function startRecording() {

        if (busy || (recorder && recorder.state !== "inactive")) {
            return;
        }

        if (audioBlob && !confirm(
            "Replace your unsaved recording?"
        )) {
            return;
        }

        if (
            !navigator.mediaDevices?.getUserMedia
            || !window.MediaRecorder
        ) {

            setMessage(
                "Audio recording is unavailable in this browser.",
                true
            );

            return;
        }

        busy = true;
        recordButton.disabled = true;
        fileInput.disabled = true;
        saveButton.disabled = true;
        discardButton.disabled = true;

        try {

            stream = await navigator.mediaDevices.getUserMedia({
                audio: true,
            });

            const mimeType = supportedMimeType();

            const options = {
                audioBitsPerSecond: 64000,
            };

            if (mimeType) {
                options.mimeType = mimeType;
            }

            recorder = new MediaRecorder(stream, options);

            clearPreview();

            chunks = [];
            elapsedBeforePause = 0;

            timer.textContent = "00:00:00";

            recorder.ondataavailable = event => {

                if (event.data.size > 0) {

                    chunks.push(event.data);
                }
            };


            recorder.onstop = () => {

                stopTimer();

                const blob = new Blob(chunks, {
                    type: recorder.mimeType
                        || mimeType
                        || "audio/webm",
                });

                releaseMicrophone();

                resetControls();

                if (blob.size > 0) {

                    showPreview(blob);

                } else {

                    setMessage("No audio was captured.", true);
                }

                chunks = [];
            };


            recorder.onerror = () => {

                stopTimer();
                releaseMicrophone();
                resetControls();

                status.textContent = "Recording failed";

                setMessage(
                    "An error occurred during recording.",
                    true
                );
            };


            recorder.start(1000);

            startedAt = performance.now();

            status.textContent = "Recording...";

            pauseButton.hidden = false;
            stopButton.hidden = false;

            startTimer();

            busy = false;

            try {

                const AudioContextClass =
                    window.AudioContext
                    || window.webkitAudioContext;

                if (AudioContextClass) {

                    audioContext = new AudioContextClass();

                    await audioContext.resume();

                    analyser = audioContext.createAnalyser();

                    analyser.fftSize = 2048;

                    const source =
                        audioContext.createMediaStreamSource(stream);

                    source.connect(analyser);

                    drawWaveform();
                }

            } catch (error) {

                console.warn("Waveform unavailable.", error);
            }

        } catch (error) {

            releaseMicrophone();
            resetControls();

            setMessage(
                `Unable to access microphone: ${error.message}`,
                true
            );

        } finally {

            saveButton.disabled = false;
            discardButton.disabled = false;
        }
    }


    // --------------------------------------------------
    // Pause and stop recording
    // --------------------------------------------------

    function togglePause() {

        if (!recorder) return;

        if (recorder.state === "recording") {

            elapsedBeforePause = elapsedTime();

            recorder.pause();

            stopTimer();
            stopWaveform();

            pauseButton.textContent = "Resume";
            status.textContent = "Paused";

        } else if (recorder.state === "paused") {

            recorder.resume();

            startedAt = performance.now();

            pauseButton.textContent = "Pause";
            status.textContent = "Recording...";

            startTimer();

            if (analyser) drawWaveform();
        }
    }


    function stopRecording() {

        if (!recorder || recorder.state === "inactive") {
            return;
        }

        elapsedBeforePause = elapsedTime();

        stopTimer();

        pauseButton.hidden = true;
        stopButton.hidden = true;

        recorder.stop();
    }


    function discardRecording() {

        if (busy || !audioBlob) return;

        if (!confirm("Discard this recording?")) return;

        clearPreview();

        elapsedBeforePause = 0;

        timer.textContent = "00:00:00";
        fileInput.value = "";

        status.textContent = "Ready to record";

        setMessage("Recording discarded.");
    }


    // --------------------------------------------------
    // Upload existing audio
    // --------------------------------------------------

    function getExtension(mimeType) {

        if (mimeType.includes("mp4")) return "m4a";
        if (mimeType.includes("mpeg")) return "mp3";
        if (mimeType.includes("wav")) return "wav";
        if (mimeType.includes("ogg")) return "ogg";
        if (mimeType.includes("aac")) return "aac";
        if (mimeType.includes("flac")) return "flac";

        return "webm";
    }


    function handleAudioUpload() {

        if (busy) return;

        const file = fileInput.files[0];

        if (!file) return;

        if (file.size > MAX_FILE_SIZE || file.size === 0) {

            setMessage(
                "Audio must be nonempty and no larger than 100 MB.",
                true
            );

            fileInput.value = "";

            return;
        }

        const allowedExtension =
            /\.(webm|m4a|mp3|wav|ogg|mp4|aac|flac)$/i;

        if (!allowedExtension.test(file.name)) {

            setMessage("Unsupported audio format.", true);

            fileInput.value = "";

            return;
        }

        if (audioBlob && !confirm(
            "Replace your unsaved recording?"
        )) {

            fileInput.value = "";

            return;
        }

        clearPreview();

        selectedFilename = file.name;

        showPreview(file);

        if (!titleInput.value.trim()) {

            titleInput.value = file.name.replace(
                /\.[^.]+$/,
                ""
            ).slice(0, 200);
        }

        status.textContent = "Audio file ready";
    }


    // --------------------------------------------------
    // Save recording to Legacy
    // --------------------------------------------------

    async function saveRecording() {

        if (!audioBlob || busy) return;

        if (audioBlob.size > MAX_FILE_SIZE) {

            setMessage("Recording exceeds 100 MB.", true);

            return;
        }

        busy = true;

        saveButton.disabled = true;
        discardButton.disabled = true;
        recordButton.disabled = true;
        fileInput.disabled = true;

        setMessage("Saving recording to Legacy...");

        try {

            const formData = new FormData();

            formData.append("_csrf_token", getCsrfToken());

            formData.append(
                "title",
                titleInput.value.trim() || "Untitled Journal"
            );

            const filename = selectedFilename
                || `recording.${getExtension(audioBlob.type)}`;

            formData.append("audio", audioBlob, filename);

            if (Number.isFinite(playback.duration)) {

                formData.append(
                    "duration_seconds",
                    playback.duration.toString()
                );
            }

            const result = await apiRequest(
                "/voice-journal/upload",
                {
                    method: "POST",
                    body: formData,
                }
            );

            if (!result.success) {

                throw new Error("Unable to save recording.");
            }

            clearPreview();

            titleInput.value = "";
            fileInput.value = "";

            elapsedBeforePause = 0;

            timer.textContent = "00:00:00";

            status.textContent = "Ready to record";

            if (result.transcription_started) {

                setMessage(
                    "Recording saved. Legacy is transcribing your journal."
                );

            } else {

                setMessage(
                    "Recording saved, but transcription could not start.",
                    true
                );
            }

            await loadJournalHistory();

        } catch (error) {

            setMessage(
                `Unable to save recording: ${error.message}`,
                true
            );

        } finally {

            busy = false;

            saveButton.disabled = false;
            discardButton.disabled = false;
            recordButton.disabled = false;
            fileInput.disabled = false;
        }
    }


    // --------------------------------------------------
    // Journal status labels
    // --------------------------------------------------

    function statusLabel(value) {

        const labels = {

            uploaded: "Awaiting transcription",
            transcribing: "Transcribing...",
            transcribed: "Ready for review",
            approved: "Approved — awaiting indexing",
            indexing: "Processing knowledge...",
            indexed: "Added to Legacy knowledge",
            failed: "Processing failed",
        };

        return labels[value] || value;
    }


    function formatDate(value) {

        if (!value) return "";

        const date = new Date(value);

        return Number.isNaN(date.getTime())
            ? ""
            : date.toLocaleString();
    }


    // --------------------------------------------------
    // Journal history
    // --------------------------------------------------

    async function loadJournalHistory() {

        if (historyBusy) return;

        historyBusy = true;

        try {

            const result = await apiRequest(
                "/voice-journal/list"
            );

            const journals = result.journals || [];

            historyList.replaceChildren();

            historyMessage.textContent = "";

            if (!journals.length) {

                const empty = document.createElement("p");

                empty.className = "voice-hint";

                empty.textContent =
                    "Your saved voice journals will appear here.";

                historyList.appendChild(empty);

                return;
            }

            for (const journal of journals) {

                const item = document.createElement("div");

                item.className = "voice-history-item";

                const information = document.createElement("div");

                const title = document.createElement("h4");

                title.textContent = journal.title;

                const details = document.createElement("p");

                details.className = "voice-history-details";

                const duration = journal.duration_seconds == null
                    ? ""
                    : ` · ${formatTime(journal.duration_seconds * 1000)}`;

                details.textContent =
                    formatDate(journal.created_utc) + duration;

                const journalStatus = document.createElement("span");

                journalStatus.className = "voice-history-status";

                journalStatus.dataset.status = journal.status;

                journalStatus.textContent =
                    statusLabel(journal.status);

                information.append(
                    title,
                    details,
                    journalStatus
                );

                const reviewButton = document.createElement("button");

                reviewButton.type = "button";

                reviewButton.className = "voice-button";

                reviewButton.textContent = "View Journal";

                reviewButton.addEventListener("click", () => {

                    openJournal(journal.id);
                });

                item.append(information, reviewButton);

                historyList.appendChild(item);
            }

        } catch (error) {

            historyMessage.textContent =
                `Unable to load journals: ${error.message}`;

        } finally {

            historyBusy = false;
        }
    }


    // --------------------------------------------------
    // Unsaved transcript detection
    // --------------------------------------------------

    function hasUnsavedTranscript() {

        return activeJournal?.status === "transcribed"
            && transcriptEditor.value
                !== (activeJournal.transcript || "");
    }


    // --------------------------------------------------
    // Display journal details
    // --------------------------------------------------

    function renderJournal(journal) {

        activeJournal = journal;

        reviewPanel.hidden = false;

        reviewTitle.textContent = journal.title;

        reviewStatus.textContent = statusLabel(journal.status);

        reviewStatus.dataset.status = journal.status;

        const metadata = [
            formatDate(journal.created_utc),
        ];

        if (journal.duration_seconds != null) {

            metadata.push(
                formatTime(journal.duration_seconds * 1000)
            );
        }

        if (journal.transcription_model) {

            metadata.push(
                `Whisper ${journal.transcription_model}`
            );
        }

        if (journal.transcription_language) {

            metadata.push(
                journal.transcription_language.toUpperCase()
            );
        }

        reviewMetadata.textContent =
            metadata.filter(Boolean).join(" · ");

        if (reviewAudio.getAttribute("src") !== journal.audio_url) {

            reviewAudio.pause();

            reviewAudio.src = journal.audio_url;
        }

        const hasTranscript =
            typeof journal.transcript === "string";

        transcriptSection.hidden = !hasTranscript;

        transcriptEditor.value = journal.transcript || "";

        originalTranscript.textContent =
            journal.original_transcript || "";

        const editable = journal.status === "transcribed";

        transcriptEditor.readOnly = !editable;

        saveTranscriptButton.hidden = !editable;
        approveTranscriptButton.hidden = !editable;

        if (journal.status === "approved") {

            setReviewMessage(
                "Transcript approved. Knowledge indexing is not yet connected."
            );

        } else if (journal.status === "indexed") {

            setReviewMessage(
                "This journal is available to Legacy's knowledge system."
            );

        } else if (
            journal.status === "uploaded"
            || journal.status === "transcribing"
        ) {

            setReviewMessage(
                "Your transcript will appear when processing finishes."
            );

        } else if (journal.status === "failed") {

            setReviewMessage(
                "Processing failed. Your original recording remains saved.",
                true
            );

        } else {

            setReviewMessage("");
        }
    }


    // --------------------------------------------------
    // Open individual journal
    // --------------------------------------------------

    async function openJournal(journalId, automatic = false) {

        if (reviewBusy) return;

        if (!automatic && hasUnsavedTranscript()) {

            if (!confirm("Discard unsaved transcript changes?")) {
                return;
            }
        }

        const requestId = ++reviewRequestId;

        try {

            const result = await apiRequest(
                `/voice-journal/${encodeURIComponent(journalId)}`
            );

            if (requestId !== reviewRequestId) return;

            renderJournal(result.journal);

            if (!automatic) {

                reviewPanel.scrollIntoView({
                    behavior: "smooth",
                    block: "nearest",
                });
            }

        } catch (error) {

            if (requestId !== reviewRequestId) return;

            historyMessage.textContent =
                `Unable to open journal: ${error.message}`;
        }
    }


    // --------------------------------------------------
    // Close journal review
    // --------------------------------------------------

    function closeJournal() {

        if (reviewBusy) return;

        if (hasUnsavedTranscript() && !confirm(
            "Discard unsaved transcript changes?"
        )) {
            return;
        }

        reviewRequestId++;

        reviewAudio.pause();
        reviewAudio.removeAttribute("src");
        reviewAudio.load();

        activeJournal = null;

        transcriptEditor.value = "";
        originalTranscript.textContent = "";

        reviewPanel.hidden = true;
    }


    // --------------------------------------------------
    // Save transcript corrections
    // --------------------------------------------------

    async function saveTranscript() {

        if (
            reviewBusy
            || !activeJournal
            || activeJournal.status !== "transcribed"
        ) {
            return;
        }

        const transcript = transcriptEditor.value.trim();

        if (!transcript) {

            setReviewMessage(
                "Transcript cannot be empty.",
                true
            );

            return;
        }

        reviewBusy = true;

        reviewRequestId++;

        saveTranscriptButton.disabled = true;
        approveTranscriptButton.disabled = true;
        transcriptEditor.readOnly = true;

        try {

            const formData = new FormData();

            formData.append("_csrf_token", getCsrfToken());
            formData.append("transcript", transcript);

            const result = await apiRequest(
                `/voice-journal/${encodeURIComponent(activeJournal.id)}/transcript`,
                {
                    method: "POST",
                    body: formData,
                }
            );

            renderJournal(result.journal);

            setReviewMessage(
                "Transcript changes saved successfully."
            );

        } catch (error) {

            setReviewMessage(error.message, true);

        } finally {

            reviewBusy = false;

            saveTranscriptButton.disabled = false;
            approveTranscriptButton.disabled = false;

            transcriptEditor.readOnly =
                activeJournal?.status !== "transcribed";
        }
    }


    // --------------------------------------------------
    // Approve transcript
    // --------------------------------------------------

    async function approveTranscript() {

        if (
            reviewBusy
            || !activeJournal
            || activeJournal.status !== "transcribed"
        ) {
            return;
        }

        const transcript = transcriptEditor.value.trim();

        if (!transcript) {

            setReviewMessage(
                "Transcript cannot be empty.",
                true
            );

            return;
        }

        if (!confirm(
            "Approve this transcript for Legacy's knowledge system?"
        )) {
            return;
        }

        reviewBusy = true;

        reviewRequestId++;

        saveTranscriptButton.disabled = true;
        approveTranscriptButton.disabled = true;
        transcriptEditor.readOnly = true;

        try {

            const formData = new FormData();

            formData.append("_csrf_token", getCsrfToken());
            formData.append("transcript", transcript);

            const result = await apiRequest(
                `/voice-journal/${encodeURIComponent(activeJournal.id)}/approve`,
                {
                    method: "POST",
                    body: formData,
                }
            );

            renderJournal(result.journal);

            await loadJournalHistory();

        } catch (error) {

            setReviewMessage(error.message, true);

        } finally {

            reviewBusy = false;

            saveTranscriptButton.disabled = false;
            approveTranscriptButton.disabled = false;

            transcriptEditor.readOnly =
                activeJournal?.status !== "transcribed";
        }
    }


    // --------------------------------------------------
    // Automatic status refresh
    // --------------------------------------------------

    async function refreshJournalStatus() {

        if (document.hidden) return;

        await loadJournalHistory();

        if (
            activeJournal
            && !reviewBusy
            && ["uploaded", "transcribing", "indexing"]
                .includes(activeJournal.status)
        ) {

            await openJournal(activeJournal.id, true);
        }
    }


    // --------------------------------------------------
    // Event listeners
    // --------------------------------------------------

    recordButton.addEventListener("click", startRecording);

    pauseButton.addEventListener("click", togglePause);

    stopButton.addEventListener("click", stopRecording);

    saveButton.addEventListener("click", saveRecording);

    discardButton.addEventListener("click", discardRecording);

    fileInput.addEventListener("change", handleAudioUpload);

    refreshHistoryButton.addEventListener(
        "click",
        refreshJournalStatus
    );

    closeReviewButton.addEventListener("click", closeJournal);

    saveTranscriptButton.addEventListener(
        "click",
        saveTranscript
    );

    approveTranscriptButton.addEventListener(
        "click",
        approveTranscript
    );


    playback.addEventListener("loadedmetadata", () => {

        if (Number.isFinite(playback.duration)) {

            timer.textContent =
                formatTime(playback.duration * 1000);
        }
    });


    playback.addEventListener("error", () => {

        if (audioBlob) {

            setMessage(
                "This audio format may not support browser playback.",
                true
            );
        }
    });


    window.addEventListener("beforeunload", event => {

        if (
            busy
            || reviewBusy
            || audioBlob
            || hasUnsavedTranscript()
            || (recorder && recorder.state !== "inactive")
        ) {

            event.preventDefault();

            event.returnValue = "";
        }
    });


    window.addEventListener("pagehide", () => {

        stopTimer();

        releaseMicrophone();

        if (historyTimer !== null) {

            clearInterval(historyTimer);
        }

        if (audioURL) {

            URL.revokeObjectURL(audioURL);
        }
    });


    // --------------------------------------------------
    // Initialize Voice Journal
    // --------------------------------------------------

    drawIdleWaveform();

    loadJournalHistory();

    historyTimer = setInterval(
        refreshJournalStatus,
        5000
    );

});
