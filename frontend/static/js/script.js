(() => {
  // Cache frequently used DOM elements
  const chatBox = document.querySelector(".chat-box");
  const userInput = document.querySelector("#user-input");
  const sendBtn = document.querySelector("#send-btn");
  const uploadBtn = document.querySelector("#upload-btn");
  const voiceBtn = document.querySelector("#voice-btn");
  const stopVoiceBtn = document.querySelector("#stop-voice-btn");
  const newChatBtn = document.querySelector("#new-chat-btn");
  const autoTTS = document.querySelector("#auto-tts");
  const permanentStopBtn = document.querySelector("#permanent-stop-btn");

  const darkModeToggle = document.querySelector("#dark-mode-toggle");
  const downloadConvBtn = document.querySelector("#download-convo-btn");
  const loadConvBtn =
    document.querySelector("#load-convo-btn-file") ||
    document.querySelector("#load-convo-btn");
  const regenerateBtn = document.querySelector("#regenerate-btn");
  const speedRange = document.querySelector("#tts-speed");
  const accentSelect = document.querySelector("#tts-accent");
  const pauseTTSBtn = document.querySelector("#pause-tts-btn");
  const recordAudioBtn = document.querySelector("#record-audio-btn");
  const dragDropArea = document.querySelector("#drag-drop-area");
  // previewPanel removed — no corresponding element in templates
  const charCounter = document.querySelector("#char-counter");

  const helpBtn = document.querySelector("#help-btn");
  const guideBtn = document.querySelector("#guide-btn");

  // Runtime state flags and shared references
  let recognizing = false;
  let recognition = null;
  let speaking = false;
  let currentController = null;
  let lastBotMessageId = null;
  let mediaRecorder = null;
  let recordedChunks = [];

  // Utility for creating DOM elements
  function el(tag, className, html) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  // Return current timestamp in ISO format
  function nowIso() {
    return new Date().toISOString();
  }

  // Scroll chat view to the latest message
  function scrollToBottom(smooth = true) {
    if (!chatBox) return;
    chatBox.scrollTo({
      top: chatBox.scrollHeight,
      behavior: smooth ? "smooth" : "auto"
    });
  }

  // Generate a short random ID for messages
  function createId(prefix = "m") {
    return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
  }

  // Clamp numeric values within a range
  function clamp(v, a, b) {
    return Math.max(a, Math.min(b, v));
  }

  // Async delay helper
  function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
  }

  // Render a chat message bubble
  function renderMessage(msgObj, opts = {}) {
    // Explicitly handle 'file' role in renderMessage
    const wrapper = el(
      "div",
      "message " + (msgObj.role === "user" ? "user" : msgObj.role === "file" ? "file" : "bot")
    );
    wrapper.dataset.id = msgObj.id;

    const avatar = el(
      "div",
      "msg-avatar " + (msgObj.role === "user" ? "user" : "bot"),
      (msgObj.role === "user" ? "You" : "AI").charAt(0)
    );
    wrapper.appendChild(avatar);

    const contentWrap = el("div", "msg-content");
    const textEl = el(
      "div",
      "msg-text",
      escapeHtml(msgObj.text || "")
    );
    textEl.contentEditable = !!opts.editable;
    if (opts.editable) textEl.classList.add("editable");
    contentWrap.appendChild(textEl);

    const meta = el("div", "msg-meta");
    meta.innerText = new Date(msgObj.ts || Date.now()).toLocaleString();
    contentWrap.appendChild(meta);

    const actions = el("div", "msg-actions");
    const copyBtn = el("button", "icon-btn small copy-btn", "Copy");
    copyBtn.title = "Copy message";
    copyBtn.addEventListener("click", () => {
      navigator.clipboard
        .writeText(msgObj.text || "")
        .then(() => flashTemporary(copyBtn, "Copied!"))
        .catch(() => flashTemporary(copyBtn, "Failed"));
    });
    actions.appendChild(copyBtn);

    if (msgObj.role === "bot") {
      const editBtn = el("button", "icon-btn small edit-btn", "Edit");
      editBtn.addEventListener("click", () => makeEditable(textEl, msgObj));
      actions.appendChild(editBtn);

      const regenBtn = el(
        "button",
        "icon-btn small regen-btn",
        "Regenerate"
      );
      regenBtn.addEventListener("click", async () => {
        await regenerateFromMessage(msgObj);
      });
      actions.appendChild(regenBtn);

      const speakBtn = el("button", "icon-btn small speak-btn", "🔊");
      speakBtn.addEventListener("click", () =>
        speakText(msgObj.text || "")
      );
      actions.appendChild(speakBtn);
    }

    contentWrap.appendChild(actions);

    const statusEl = el("div", "msg-status", msgObj.status || "");
    contentWrap.appendChild(statusEl);

    wrapper.appendChild(contentWrap);
    chatBox.appendChild(wrapper);

    if (msgObj.role === "bot") {
      const mt = wrapper.querySelector(".msg-text");
      if (mt)
        mt.addEventListener("dblclick", () =>
          makeEditable(mt, msgObj)
        );
    }

    scrollToBottom();
    return wrapper;
  }

  // Render a file upload message bubble
  function renderFileMessage(fileInfo) {
    const msg = {
      id: createId("f"),
      role: "file",
      text: `📄 ${fileInfo.original_name}`,
      meta: `${(fileInfo.file_type || "").toUpperCase()} uploaded`,
      file_id: fileInfo.file_id,
      ts: nowIso()
    };

    const wrapper = document.createElement("div");
    wrapper.className = "message file";
    wrapper.dataset.id = msg.id;
    wrapper.dataset.fileId = msg.file_id || "";
    wrapper.dataset.fileType = fileInfo.file_type || "";

    wrapper.innerHTML = `
      <div class="msg-avatar">📎</div>
      <div class="msg-content">
        <div class="msg-text"><strong>${escapeHtml(msg.text)}</strong></div>
        <div class="file-meta">${escapeHtml(msg.meta)}</div>
      </div>
    `;

    chatBox.appendChild(wrapper);
    scrollToBottom();
    return wrapper;
  }

  // Escape HTML to prevent injection
  function escapeHtml(s) {
    if (!s && s !== 0) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\n/g, "<br>");
  }

  // Temporarily replace button text for feedback
  function flashTemporary(elm, text, ms = 1200) {
    const orig = elm.innerText;
    elm.innerText = text;
    setTimeout(() => (elm.innerText = orig), ms);
  }

  // Enable inline editing for bot messages
  function makeEditable(textEl, msgObj) {
    textEl.contentEditable = true;
    textEl.focus();

    // Replace deprecated document.execCommand with Range/Selection API
    const range = document.createRange();
    range.selectNodeContents(textEl);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);

    const onBlur = () => {
      textEl.contentEditable = false;
      msgObj.text = textEl.innerText;
      textEl.removeEventListener("blur", onBlur);
      const copyBtn =
        textEl.parentElement &&
        textEl.parentElement.querySelector(".copy-btn");
      if (copyBtn) flashTemporary(copyBtn, "Saved");
    };
    textEl.addEventListener("blur", onBlur);
  }

  // Display typing placeholder while waiting for response
  function showTypingLoader() {
    const id = createId("loader");
    const msg = {
      id,
      role: "bot",
      text: "···",
      ts: nowIso(),
      status: "typing"
    };
    const elNode = renderMessage(msg, { editable: false });
    elNode.querySelector(".msg-text").classList.add("typing");
    lastBotMessageId = id;
    return elNode;
  }

  // Remove message DOM node by ID
  function removeNodeById(id) {
    const node = chatBox.querySelector(`[data-id="${id}"]`);
    if (node) node.remove();
  }

  // Replace localStorage-based history with server-backed history.
  // Fetch history from server and return an array compatible with chat logic.
  async function getConversationFromLocal() {
    try {
      const res = await fetch("/api/history");
      if (!res.ok) return [];
      const history = await res.json();
      return Array.isArray(history)
        ? history.map(m => ({
            id: m.id || Math.random().toString(36),
            role: m.role || "bot",
            text: m.content || m.text || "",
            ts: m.timestamp || nowIso()
          }))
        : [];
    } catch (e) {
      console.error("getConversationFromServer error", e);
      return [];
    }
  }

  // Server-backed persistence hook (no-op on client)
  function persistConversation() {
    // intentionally empty — server owns persistence
  }

  // Add a user message to the UI
  function addUserMessage(text) {
    const id = createId("u");
    const msg = { id, role: "user", text, ts: nowIso(), status: "sent" };
    renderMessage(msg);
    return msg;
  }

  // Add a bot message to the UI
  function addBotMessage(text, status = "") {
    const id = createId("b");
    const msg = { id, role: "bot", text, ts: nowIso(), status };
    renderMessage(msg);
    return msg;
  }

  // AbortController helpers for canceling requests
  function startController() {
    if (currentController) {
      try {
        currentController.abort();
      } catch {}
    }
    currentController = new AbortController();
    return currentController;
  }

  function clearController() {
    if (currentController) {
      try {
        currentController.abort();
      } catch {}
      currentController = null;
    }
  }

  // Send JSON request to backend
  async function postJson(path, body, options = {}) {
    const controller = options.signal
      ? options.signal
      : startController().signal;
    try {
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller
      });
      const json = await res.json().catch(() => null);
      return { ok: res.ok, status: res.status, json };
    } catch (err) {
      if (err.name === "AbortError")
        return { ok: false, aborted: true, error: err };
      return { ok: false, error: err };
    }
  }

  // Send multipart/form-data request
  async function postForm(path, formData, options = {}) {
    const controller = options.signal
      ? options.signal
      : startController().signal;
    try {
      const res = await fetch(path, {
        method: "POST",
        body: formData,
        signal: controller
      });
      const json = await res.json().catch(() => null);
      return { ok: res.ok, status: res.status, json };
    } catch (err) {
      if (err.name === "AbortError")
        return { ok: false, aborted: true, error: err };
      return { ok: false, error: err };
    }
  }

  // Orchestrate full message send lifecycle
  async function sendMessageFlow(text, opts = {}) {
    addUserMessage(text);
    const loaderNode = showTypingLoader();
    sendBtn.disabled = true;
    uploadBtn.disabled = true;

    try {
      if (text.startsWith("/")) {
        const cmdResp = await handleSlashCommand(text);
        removeNodeById(loaderNode.dataset.id);
        addBotMessage(cmdResp);
        return;
      }

      const history = await getConversationFromLocal();
      const res = await postJson("/chat", {
        message: text,
        history: history
      });

      if (!res.ok) {
        removeNodeById(loaderNode.dataset.id);
        addBotMessage(
          res.aborted
            ? "(info) Request aborted."
            : `(error) ${res.error || JSON.stringify(res.json)}`
        );
        return;
      }

      const reply =
        res.json && res.json.response
          ? res.json.response
          : "(error) No response.";

      removeNodeById(loaderNode.dataset.id);
      await typewriterBot(reply);
    } catch (err) {
      removeNodeById(loaderNode.dataset.id);
      addBotMessage(`(error) ${err.message}`);
    } finally {
      sendBtn.disabled = false;
      uploadBtn.disabled = false;
    }
  }

  // Animate bot response typing effect
  async function typewriterBot(text) {
    const id = createId("b");
    const piece = {
      id,
      role: "bot",
      text: "",
      ts: nowIso(),
      status: "delivered"
    };
    const node = renderMessage(piece);
    const textNode = node.querySelector(".msg-text");
    if (!textNode) return;

    if (text.length < 400) {
      for (let i = 1; i <= text.length; i++) {
        textNode.innerHTML = escapeHtml(text.slice(0, i));
        await sleep(8 + Math.random() * 12);
      }
    } else {
      const chunks = smartChunkForTyping(text, 200);
      for (const c of chunks) {
        textNode.innerHTML = escapeHtml(
          (textNode.innerText + "\n" + c).trim()
        );
        await sleep(120 + Math.random() * 140);
      }
    }

    if (autoTTS && autoTTS.checked) speakText(text);
    scrollToBottom();
  }

  // Split long replies into natural typing chunks
  function smartChunkForTyping(text, approxLen = 200) {
    const out = [];
    let start = 0;
    while (start < text.length) {
      let end = Math.min(text.length, start + approxLen);
      if (end < text.length) {
        const slice = text.slice(start, end);
        const lastPeriod = Math.max(
          slice.lastIndexOf(". "),
          slice.lastIndexOf("\n")
        );
        if (lastPeriod > approxLen * 0.5)
          end = start + lastPeriod + 1;
      }
      out.push(text.slice(start, end).trim());
      start = end;
    }
    return out;
  }

  // Handle slash commands typed by the user
  async function handleSlashCommand(cmdText) {
    const parts = cmdText.trim().split(/\s+/);
    const cmd = parts[0].toLowerCase();
    const payload = cmdText.replace(cmd, "").trim();

    switch (cmd) {
      case "/summarize":
        if (!payload)
          return "(usage) /summarize <text or filename>";
        if (payload.includes("_") && payload.includes(".")) {
          const resp = await postJson("/explain_file", {
            filename: payload,
            bullets: 4
          });
          if (resp.ok && resp.json)
            return resp.json.final || "(info) No summary.";
          return `(error) ${resp.error || "failed"}`;
        } else {
          const resp = await postJson("/api/summarize", {
            text: payload,
            bullets: 3
          });
          if (resp.ok && resp.json)
            return resp.json.summary || "(info) No summary.";
          return `(error) ${resp.error || "failed"}`;
        }

      case "/keypoints":
        if (!payload) return "(usage) /keypoints <text>";
        {
          const resp = await postJson("/api/summarize", {
            text: payload,
            bullets: 5
          });
          if (resp.ok && resp.json)
            return resp.json.summary || "(info) No keypoints.";
          return `(error) ${resp.error || "failed"}`;
        }

      case "/explain":
        if (!payload)
          return "(usage) /explain <uploaded_filename>";
        {
          const resp = await postJson("/explain_file", {
            filename: payload,
            bullets: 4
          });
          if (resp.ok && resp.json)
            return resp.json.final || "(info) No explanation.";
          return `(error) ${resp.error || "failed"}`;
        }

      case "/translate":
        if (!payload) return "(usage) /translate <text>";
        {
          const res = await postJson("/chat", {
            message: `Translate to English: ${payload}`
          });
          if (res.ok && res.json) return res.json.response;
          return `(error) ${res.error || "failed"}`;
        }

      case "/analyze":
        if (!payload) return "(usage) /analyze <text>";
        {
          const res = await postJson("/chat", {
            message:
              "Analyze the following text and list issues and suggestions:\n\n" +
              payload
          });
          if (res.ok && res.json) return res.json.response;
          return `(error) ${res.error || "failed"}`;
        }

      default:
        return `(info) Unknown command: ${cmd}`;
    }
  }

  // Initialize drag-and-drop file upload behavior
  function setupDragDrop() {
    if (!dragDropArea) return;
    ["dragenter", "dragover"].forEach(ev =>
      dragDropArea.addEventListener(ev, e => {
        e.preventDefault();
        e.stopPropagation();
        dragDropArea.classList.add("drag-over");
      })
    );
    ["dragleave", "drop"].forEach(ev =>
      dragDropArea.addEventListener(ev, e => {
        e.preventDefault();
        e.stopPropagation();
        dragDropArea.classList.remove("drag-over");
      })
    );
    dragDropArea.addEventListener("drop", async e => {
      const files = Array.from(e.dataTransfer.files || []);
      if (files.length === 0) return;
      await handleFilesUpload(files);
    });
  }

  // Upload a list of files sequentially
  async function handleFilesUpload(files) {
    for (const file of files) {
      await previewAndUploadFile(file);
    }
  }

  // Upload a single file to the backend
  async function previewAndUploadFile(file) {
    const formData = new FormData();
    formData.append("file", file);

    const loader = showTypingLoader();
    try {
      const res = await postForm("/upload", formData);
      removeNodeById(loader.dataset.id);

      if (!res.ok || !res.json) {
        addBotMessage("(error) Upload failed.");
        return;
      }

      renderFileMessage(res.json);
    } catch {
      removeNodeById(loader.dataset.id);
      addBotMessage("(error) Upload error.");
    }
  }

  // Start capturing audio using MediaRecorder
  async function startAudioRecording() {
    if (
      !navigator.mediaDevices ||
      !navigator.mediaDevices.getUserMedia
    ) {
      addBotMessage(
        "(error) Audio capture not supported in this browser."
      );
      return;
    }
    try {
      const stream =
        await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      recordedChunks = [];
      mediaRecorder.ondataavailable = e => {
        if (e.data && e.data.size) recordedChunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        const blob = new Blob(recordedChunks, { type: "audio/webm" });
        const f = new File(
          [blob],
          `recording-${Date.now()}.webm`,
          { type: blob.type }
        );
        await previewAndUploadFile(f);
      };
      mediaRecorder.start();
      recordAudioBtn &&
        recordAudioBtn.classList.add("recording");
      addBotMessage("(recording) Speak now...");
    } catch (err) {
      addBotMessage(`(error) ${err.message}`);
    }
  }

  // Stop audio recording and upload the result
  function stopAudioRecording() {
    try {
      if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
        recordAudioBtn &&
          recordAudioBtn.classList.remove("recording");
        addBotMessage("(recording stopped)");
      }
    } catch (err) {
      console.warn(err);
    }
  }

  // Speak text aloud using Web Speech API
  function speakText(text) {
    if (!("speechSynthesis" in window)) return;
    const utter = new SpeechSynthesisUtterance(text);
    const speed = speedRange
      ? parseFloat(speedRange.value)
      : 1.0;
    utter.rate = clamp(speed, 0.5, 2.0);
    const accent = accentSelect ? accentSelect.value : "en-US";
    utter.lang = accent;
    utter.onstart = () => {
      speaking = true;
      pauseTTSBtn && (pauseTTSBtn.disabled = false);
    };
    utter.onend = () => {
      speaking = false;
      pauseTTSBtn && (pauseTTSBtn.disabled = true);
    };
    utter.onerror = () => {
      speaking = false;
      pauseTTSBtn && (pauseTTSBtn.disabled = true);
    };
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
  }

  function pauseTTS() {
    if (!("speechSynthesis" in window)) return;
    if (window.speechSynthesis.speaking)
      window.speechSynthesis.pause();
  }

  function resumeTTS() {
    if (!("speechSynthesis" in window)) return;
    if (window.speechSynthesis.paused)
      window.speechSynthesis.resume();
  }

  // Re-run a bot response using the preceding user prompt
  async function regenerateFromMessage(msgObj) {
    const lastUser = findLastUserMessageBefore(msgObj.id);
    if (!lastUser) {
      addBotMessage(
        "(info) No user message available to regenerate from."
      );
      return;
    }
    const botNode = chatBox.querySelector(
      `[data-id="${msgObj.id}"]`
    );
    if (botNode) botNode.remove();
    await sendMessageFlow(lastUser.text);
  }

  // Find the nearest user message before a given bot message
  function findLastUserMessageBefore(botId) {
    const nodes = Array.from(
      chatBox.querySelectorAll(".message")
    );
    let targetIndex = nodes.findIndex(
      n => n.dataset.id === botId
    );

    if (targetIndex > 0) {
      for (let i = targetIndex - 1; i >= 0; i--) {
        const n = nodes[i];
        if (n.classList.contains("user")) {
          return {
            id: n.dataset.id,
            text:
              (n.querySelector(".msg-text") || {}).innerText ||
              ""
          };
        }
      }
    }

    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if (n.classList.contains("user")) {
        return {
          id: n.dataset.id,
          text:
            (n.querySelector(".msg-text") || {}).innerText ||
            ""
        };
      }
    }
    return null;
  }

  // Export conversation as downloadable JSON file
  function downloadConversation() {
    const arr = [];
    chatBox.querySelectorAll(".message").forEach(n => {
      const role = n.classList.contains("user") ? "user" : "bot";
      const text =
        (n.querySelector(".msg-text") || {}).innerText || "";
      const ts =
        (n.querySelector(".msg-meta") || {}).innerText || "";
      arr.push({ role, text, ts });
    });
    const blob = new Blob(
      [JSON.stringify(arr, null, 2)],
      { type: "application/json" }
    );
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `conversation-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    downloadConvBtn && flashTemporary(downloadConvBtn, "Saved");
  }

  // Import a conversation JSON file
  function loadConversationFromFile(file) {
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const arr = JSON.parse(e.target.result || "[]");
        chatBox.innerHTML = "";
        arr.forEach(m =>
          renderMessage({
            id: createId("m"),
            role: m.role,
            text: m.text,
            ts: m.ts
          })
        );
      } catch {
        addBotMessage(
          "(error) Unable to load conversation file."
        );
      }
    };
    reader.readAsText(file);
  }
  async function loadHistoryFromServer() {
    try {
      const res = await fetch("/api/history");
      if (!res.ok) return;

      const history = await res.json();
      chatBox.innerHTML = "";

      history.forEach(m => {
        renderMessage({
          id: Math.random().toString(36),
          role: m.role,
          text: m.content,
          ts: m.timestamp
        });
      });
    } catch (e) {
      console.error(e);
    }
  } // Closing brace added to fix syntax error

  // Update live character counter and textarea height
  function updateCharCounter() {
    if (!charCounter || !userInput) return;
    const len = (userInput.value || "").length;
    charCounter.innerText = `${len} chars`;
    charCounter.style.color = len > 1000 ? "red" : "";
  }

  function setupAutoResize() {
    if (!userInput) return;
    userInput.addEventListener("input", updateCharCounter);
    userInput.addEventListener("input", () => {
      userInput.style.height = "auto";
      userInput.style.height =
        Math.min(180, userInput.scrollHeight) + "px";
    });
  }

  // Register keyboard shortcuts
  function setupShortcuts() {
    window.addEventListener("keydown", e => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        userInput && userInput.focus();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        downloadConversation();
      }
      if (e.key === "Escape") {
        clearController();
        if ("speechSynthesis" in window)
          window.speechSynthesis.cancel();
        addBotMessage("(info) Aborted / stopped.");
      }
    });
  }

  // Display interactive help instructions
  function showHelp() {
    const helpText = `👋 Welcome to AI Learning Assistant!

Here’s what I can do:

💬 Chat
• Ask any question — AI replies in chat.
• Enable "Auto TTS" to hear answers.
• Click 🎤 to speak (speech-to-text).

📁 Files & Upload
• Drag & drop or Upload PDF, DOCX, XLSX, CSV, TXT, images, code, audio.
• After upload AI extracts text and explains it.
• For PDFs the AI shows partial progress and then a final summary.

⚡ Slash Commands
• /summarize <text or uploaded_filename>
• /explain <uploaded_filename>
• /keypoints <text>
• /translate <text>
• /analyze <text>

🎛 Useful Controls
• New Chat — starts fresh conversation.
• Regenerate — re-run last reply.
• Save/Load — export or import conversation JSON.
• Record — record audio and upload it.
• Stop — abort any running request and stop voice.

Pro tip: the help will auto-open for first-time users. You can always re-open this panel with the ❓ Help button.`;
    addBotMessage(helpText);
  }

  // Wire UI events and initialize application
  function init() {
    loadHistoryFromServer();
    setupDragDrop();
    setupAutoResize();
    setupShortcuts();

    if (helpBtn) {
      helpBtn.addEventListener("click", () => showHelp());
    }

    if (guideBtn) {
      guideBtn.addEventListener("click", () => showHelp());
    }

    sendBtn &&
      sendBtn.addEventListener("click", async () => {
        const txt = (userInput.value || "").trim();
        if (!txt) return;
        userInput.value = "";
        userInput.style.height = "auto";
        updateCharCounter();
        await sendMessageFlow(txt);
      });

    if (userInput) {
      userInput.addEventListener("keydown", async e => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          const txt = (userInput.value || "").trim();
          if (!txt) return;
          userInput.value = "";
          userInput.style.height = "auto";
          updateCharCounter();
          await sendMessageFlow(txt);
        }
      });
    }

    uploadBtn &&
      uploadBtn.addEventListener("click", () => {
        const input = document.createElement("input");
        input.type = "file";
        input.multiple = true;
        input.accept =
          ".pdf,.txt,.docx,.csv,.xlsx,.png,.jpg,.jpeg,.gif,.py,.js,.html,.webm";
        input.onchange = async e => {
          const files = Array.from(e.target.files || []);
          if (files.length) await handleFilesUpload(files);
        };
        input.click();
      });

    if (
      "webkitSpeechRecognition" in window ||
      "SpeechRecognition" in window
    ) {
      const SpeechRec =
        window.webkitSpeechRecognition ||
        window.SpeechRecognition;
      recognition = new SpeechRec();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = "en-US";
      recognition.onstart = () => {
        recognizing = true;
        voiceBtn && voiceBtn.classList.add("recording");
        addBotMessage("(listening)");
      };
      recognition.onresult = event => {
        const t = event.results[0][0].transcript;
        if (userInput) userInput.value = t;
        updateCharCounter();
        sendMessageFlow(t);
      };
      recognition.onerror = () => {
        recognizing = false;
        voiceBtn &&
          voiceBtn.classList.remove("recording");
        addBotMessage("(error) Speech recognition");
      };
      recognition.onend = () => {
        recognizing = false;
        voiceBtn &&
          voiceBtn.classList.remove("recording");
      };
      voiceBtn &&
        voiceBtn.addEventListener("click", () => {
          if (recognizing) {
            recognition.stop();
            recognizing = false;
            voiceBtn.classList.remove("recording");
          } else {
            recognition.start();
          }
        });
    } else {
      voiceBtn && (voiceBtn.disabled = true);
    }

    pauseTTSBtn &&
      pauseTTSBtn.addEventListener("click", () => {
        if (
          window.speechSynthesis &&
          window.speechSynthesis.speaking
        ) {
          if (window.speechSynthesis.paused) resumeTTS();
          else pauseTTS();
        }
      });

    stopVoiceBtn &&
      stopVoiceBtn.addEventListener("click", () => {
        if (window.speechSynthesis)
          window.speechSynthesis.cancel();
        addBotMessage("(TTS stopped)");
      });

    newChatBtn &&
      newChatBtn.addEventListener("click", () => {
        if (
          !confirm(
            "Start a new chat? This will clear the current conversation in the UI (local copy stays in browser)."
          )
        )
          return;
        chatBox.innerHTML = "";
        addBotMessage(
          "👋 New chat started. How can I help you?"
        );
      });

    permanentStopBtn &&
      permanentStopBtn.addEventListener("click", () => {
        clearController();
        if (window.speechSynthesis)
          window.speechSynthesis.cancel();
        addBotMessage("(info) Request cancelled by user.");
      });

    regenerateBtn &&
      regenerateBtn.addEventListener("click", async () => {
        const nodes = Array.from(
          chatBox.querySelectorAll(".message")
        );
        const reversed = nodes.slice().reverse();
        const lastBotNode = reversed.find(n =>
          n.classList.contains("bot")
        );
        if (!lastBotNode) {
          addBotMessage("(info) Nothing to regenerate.");
          return;
        }
        const botId = lastBotNode.dataset.id;
        const botObj = {
          id: botId,
          text:
            (lastBotNode.querySelector(".msg-text") || {})
              .innerText || ""
        };
        await regenerateFromMessage(botObj);
      });

    downloadConvBtn &&
      downloadConvBtn.addEventListener(
        "click",
        downloadConversation
      );

    loadConvBtn &&
      loadConvBtn.addEventListener("change", e => {
        const f = e.target.files && e.target.files[0];
        if (f) loadConversationFromFile(f);
      });

    if (recordAudioBtn) {
      recordAudioBtn.addEventListener("click", () => {
        if (recordAudioBtn.classList.contains("recording"))
          stopAudioRecording();
        else startAudioRecording();
      });
    }

    if (speedRange) speedRange.value = 1.0;
    if (accentSelect) accentSelect.value = "en-US";

    updateCharCounter();

    if (!chatBox || chatBox.children.length === 0) {
      addBotMessage(
        "Hi there! 👋 I’m your AI assistant. You can chat, upload files, or talk to me."
      );
    }
  }

  // Bootstraps the application
  init();

  // Expose limited helpers for debugging
  window.aiAssistant = {
    persistConversation,
    loadHistoryFromServer,
    downloadConversation,
    clearController,
    speakText
  };

  // Ensure History button functionality remains unchanged
  const historyBtn = document.querySelector("#history-btn");

  historyBtn.addEventListener("click", () => {
    chatBox.innerHTML = "";
    loadHistoryFromServer();
  });

  // Add functionality for the logout option
  const logoutLink = document.querySelector(".menu-item");

  logoutLink.addEventListener("click", (event) => {
    event.preventDefault();
    window.location.href = "/logout";
  });

  // Add functionality for the History option in the menu
  const historyMenuItem = document.querySelector("#history-menu-item");

  historyMenuItem.addEventListener("click", (event) => {
    event.preventDefault();
    chatBox.innerHTML = "";
    loadHistoryFromServer();
  });

  // Prevent text area from automatically writing space bars
  const textArea = document.querySelector("#text-area");

  textArea.addEventListener("input", (event) => {
    const value = event.target.value;
    event.target.value = value.replace(/\s+$/, ""); // Remove trailing spaces
  });
})();
