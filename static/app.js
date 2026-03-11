/**
 * SPPU Result Ledger Extractor — Frontend Logic
 * Designed by Durgesh Mahajan
 */

(function () {
    "use strict";

    // ─── DOM Elements ───
    const dropzone = document.getElementById("dropzone");
    const dropzoneContent = document.getElementById("dropzone-content");
    const fileInput = document.getElementById("file-input");
    const filePreview = document.getElementById("file-preview");
    const fileName = document.getElementById("file-name");
    const fileSize = document.getElementById("file-size");
    const fileRemove = document.getElementById("file-remove");
    const extractBtn = document.getElementById("extract-btn");
    const btnText = document.getElementById("btn-text");
    const btnLoading = document.getElementById("btn-loading");
    const uploadSection = document.getElementById("upload-section");
    const progressSection = document.getElementById("progress-section");
    const progressBar = document.getElementById("progress-bar");
    const progressTitle = document.getElementById("progress-title");
    const progressSubtitle = document.getElementById("progress-subtitle");
    const successSection = document.getElementById("success-section");
    const successDesc = document.getElementById("success-desc");
    const resetBtn = document.getElementById("reset-btn");
    const errorSection = document.getElementById("error-section");
    const errorDesc = document.getElementById("error-desc");
    const errorResetBtn = document.getElementById("error-reset-btn");

    let selectedFile = null;

    // ─── Helpers ───
    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / 1048576).toFixed(1) + " MB";
    }

    function showSection(section) {
        // Hide all dynamic sections
        [uploadSection, progressSection, successSection, errorSection].forEach(
            (s) => (s.style.display = "none")
        );
        section.style.display = "block";
    }

    function setProgress(percent, title, subtitle, activeStep) {
        progressBar.style.width = percent + "%";
        if (title) progressTitle.textContent = title;
        if (subtitle) progressSubtitle.textContent = subtitle;

        // Update step indicators
        for (let i = 1; i <= 4; i++) {
            const stepEl = document.getElementById("step-" + i);
            stepEl.classList.remove("active", "done");
            if (i < activeStep) stepEl.classList.add("done");
            else if (i === activeStep) stepEl.classList.add("active");
        }
    }

    // ─── File Selection ───
    function handleFile(file) {
        if (!file) return;

        // Validate type
        if (!file.name.toLowerCase().endsWith(".pdf")) {
            showError("Please select a PDF file.");
            return;
        }

        // Validate size (50 MB)
        if (file.size > 50 * 1024 * 1024) {
            showError("File too large. Maximum size is 50 MB.");
            return;
        }

        selectedFile = file;

        // Show file preview
        dropzone.style.display = "none";
        filePreview.style.display = "flex";
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);
        extractBtn.disabled = false;
    }

    function removeFile() {
        selectedFile = null;
        fileInput.value = "";
        dropzone.style.display = "block";
        filePreview.style.display = "none";
        extractBtn.disabled = true;
    }

    function showError(message) {
        errorDesc.textContent = message;
        showSection(errorSection);
    }

    // ─── Drag & Drop ───
    dropzone.addEventListener("click", () => fileInput.click());

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("drag-over");
    });

    dropzone.addEventListener("dragleave", (e) => {
        e.preventDefault();
        dropzone.classList.remove("drag-over");
    });

    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("drag-over");
        const file = e.dataTransfer.files[0];
        handleFile(file);
    });

    fileInput.addEventListener("change", (e) => {
        handleFile(e.target.files[0]);
    });

    fileRemove.addEventListener("click", removeFile);

    // ─── Extract Flow ───
    extractBtn.addEventListener("click", async () => {
        if (!selectedFile) return;

        // Switch to loading state
        btnText.style.display = "none";
        btnLoading.style.display = "flex";
        extractBtn.disabled = true;

        // Show progress
        showSection(progressSection);
        // Also keep upload section visible briefly before hiding
        uploadSection.style.display = "none";

        // Simulate progress stages
        setProgress(10, "Uploading PDF...", "Sending file to server", 1);

        try {
            const formData = new FormData();
            formData.append("file", selectedFile);

            // Animate progress during upload
            setProgress(25, "Uploading PDF...", "Sending file to server", 1);

            const progressInterval = setInterval(() => {
                const current = parseFloat(progressBar.style.width) || 25;
                if (current < 60) {
                    setProgress(
                        current + Math.random() * 5,
                        "Parsing PDF...",
                        "Extracting student records",
                        2
                    );
                } else if (current < 80) {
                    setProgress(
                        current + Math.random() * 3,
                        "Building Excel...",
                        "Formatting output spreadsheet",
                        3
                    );
                }
            }, 400);

            const response = await fetch("/extract", {
                method: "POST",
                body: formData,
            });

            clearInterval(progressInterval);

            if (!response.ok) {
                let errorMsg = "An unexpected error occurred.";
                try {
                    const errData = await response.json();
                    errorMsg = errData.error || errorMsg;
                } catch {
                    errorMsg = `Server error (${response.status})`;
                }
                throw new Error(errorMsg);
            }

            // Progress: downloading
            setProgress(90, "Downloading...", "Preparing your file", 4);

            const blob = await response.blob();
            const contentDisposition = response.headers.get("Content-Disposition");
            let downloadName = selectedFile.name.replace(".pdf", ".xlsx").replace(".PDF", ".xlsx");

            if (contentDisposition) {
                const match = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
                if (match && match[1]) {
                    downloadName = match[1].replace(/['"]/g, "");
                }
            }

            // Trigger download
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = downloadName;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);

            // Show success
            setProgress(100, "Complete!", "File downloaded successfully", 4);
            await new Promise((r) => setTimeout(r, 600));

            successDesc.textContent = `"${downloadName}" has been downloaded successfully.`;
            showSection(successSection);
        } catch (err) {
            console.error("Extraction failed:", err);
            showError(err.message || "Failed to process the PDF. Please try again.");
        } finally {
            // Reset button state
            btnText.style.display = "flex";
            btnLoading.style.display = "none";
        }
    });

    // ─── Reset Handlers ───
    function resetAll() {
        selectedFile = null;
        fileInput.value = "";

        // Reset dropzone
        dropzone.style.display = "block";
        filePreview.style.display = "none";
        extractBtn.disabled = true;

        // Reset progress
        progressBar.style.width = "0%";
        for (let i = 1; i <= 4; i++) {
            const stepEl = document.getElementById("step-" + i);
            stepEl.classList.remove("active", "done");
        }

        // Show upload section
        showSection(uploadSection);
    }

    resetBtn.addEventListener("click", resetAll);
    errorResetBtn.addEventListener("click", resetAll);

    // ─── Prevent default drag behaviors on window ───
    ["dragenter", "dragover", "dragleave", "drop"].forEach((event) => {
        document.body.addEventListener(event, (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
    });
})();
