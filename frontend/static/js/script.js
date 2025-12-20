(() => {
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
  const loadConvBtn = document.querySelector("#load-convo-btn-file") || document.querySelector("#load-convo-btn");
  const regenerateBtn = document.querySelector("#regenerate-btn");
  const speedRange = document.querySelector("#tts-speed");
  const accentSelect = document.querySelector("#tts-accent");
  const pauseTTSBtn = document.querySelector("#pause-tts-btn");
  const recordAudioBtn = document.querySelector("#record-audio-btn");
  const dragDropArea = document.querySelector("#drag-drop-area");
  const previewPanel = document.querySelector("#file-preview-panel");
  const charCounter = document.querySelector("#char-counter");

  const helpBtn = document.querySelector("#help-btn");
  const guideBtn = document.querySelector("#guide-btn");

  let recognizing = false;
  let recognition = null;
  let speaking = false;
  let currentController = null;
  let lastBotMessageId = null;
  let mediaRecorder = null;
  let recordedChunks = [];
  let conversationMemoryKey = "ai_assistant_conversation_v1";
  const LOCAL_SAVE_LIMIT = 200;

  function el(tag, className, html) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function scrollToBottom(smooth = true) {
    if (!chatBox) return;
    chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }

  function createId(prefix = "m") {
    return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
  }

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  // message rendering
  function renderMessage(msgObj, opts = {}) {
    const wrapper = el("div", "message " + (msgObj.role === "user" ? "user" : "bot"));
    wrapper.dataset.id = msgObj.id;
    // avatar column
    const avatar = el("div", "msg-avatar " + (msgObj.role === "user" ? "user" : "bot"),
      (msgObj.role === "user" ? "You" : "AI").charAt(0));
    wrapper.appendChild(avatar);

    const contentWrap = el("div", "msg-content");
    const textEl = el("div", "msg-text", escapeHtml(msgObj.text || ""));
    textEl.contentEditable = !!opts.editable;
    if (opts.editable) textEl.classList.add("editable");
    contentWrap.appendChild(textEl);

    // meta row
    const meta = el("div", "msg-meta");
    meta.innerText = new Date(msgObj.ts || Date.now()).toLocaleString();
    contentWrap.appendChild(meta);

    // actions
    const actions = el("div", "msg-actions");
    const copyBtn = el("button", "icon-btn small copy-btn", "Copy");
    copyBtn.title = "Copy message";
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(msgObj.text || "").then(() => {
        flashTemporary(copyBtn, "Copied!");
      }).catch(()=>flashTemporary(copyBtn,"Failed"));
    });
    actions.appendChild(copyBtn);

    if (msgObj.role === "bot") {
      const editBtn = el("button", "icon-btn small edit-btn", "Edit");
      editBtn.title = "Edit message";
      editBtn.addEventListener("click", () => {
        makeEditable(textEl, msgObj);
      });
      actions.appendChild(editBtn);

      const regenBtn = el("button", "icon-btn small regen-btn", "Regenerate");
      regenBtn.title = "Regenerate response using the same prompt";
      regenBtn.addEventListener("click", async () => {
        await regenerateFromMessage(msgObj);
      });
      actions.appendChild(regenBtn);

      const speakBtn = el("button", "icon-btn small speak-btn", "🔊");
      speakBtn.title = "Play this message";
      speakBtn.addEventListener("click", () => speakText(msgObj.text || ""));
      actions.appendChild(speakBtn);
    }

    contentWrap.appendChild(actions);

    // status
    const statusEl = el("div", "msg-status", msgObj.status || "");
    contentWrap.appendChild(statusEl);

    wrapper.appendChild(contentWrap);
    chatBox.appendChild(wrapper);

    // attach double click edit for bot messages
    if (msgObj.role === "bot") {
      const mt = wrapper.querySelector(".msg-text");
      if (mt) mt.addEventListener("dblclick", () => makeEditable(mt, msgObj));
    }

    scrollToBottom();
    return wrapper;
  }

  // render a file message bubble
  function renderFileMessage(fileInfo) {
    const msg = {
      id: createId("f"),
      role: "file",
      text: `📄 ${fileInfo.original_name}`,
      meta: `${(fileInfo.file_type||"").toUpperCase()} uploaded`,
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
    saveConversationToLocal();
    scrollToBottom();
    return wrapper;
  }

  function escapeHtml(s) {
    if (!s && s !== 0) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\n/g, "<br>");
  }

  function flashTemporary(elm, text, ms = 1200) {
    const orig = elm.innerText;
    elm.innerText = text;
    setTimeout(()=>elm.innerText = orig, ms);
  }

  function makeEditable(textEl, msgObj) {
    textEl.contentEditable = true;
    textEl.focus();
    // select all
    document.execCommand && document.execCommand("selectAll", false, null);
    // when focus out save it back (local only)
    const onBlur = () => {
      textEl.contentEditable = false;
      msgObj.text = textEl.innerText;
      saveConversationToLocal();
      textEl.removeEventListener("blur", onBlur);
      const copyBtn = textEl.parentElement && textEl.parentElement.querySelector(".copy-btn");
      if (copyBtn) flashTemporary(copyBtn, "Saved");
    };
    textEl.addEventListener("blur", onBlur);
  }

  // ---------- Loader / typing animation ----------
  function showTypingLoader() {
    const id = createId("loader");
    const msg = { id, role: "bot", text: "···", ts: nowIso(), status: "typing" };
    const elNode = renderMessage(msg, { editable: false });
    elNode.querySelector(".msg-text").classList.add("typing");
    lastBotMessageId = id;
    return elNode;
  }

  function removeNodeById(id) {
    const node = chatBox.querySelector(`[data-id="${id}"]`);
    if (node) node.remove();
  }

  // ---------- Persist & memory ----------
  function getConversationFromLocal() {
    try {
      const raw = localStorage.getItem(conversationMemoryKey);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.slice(-LOCAL_SAVE_LIMIT) : [];
    } catch {
      return [];
    }
  }

  function saveConversationToLocal() {
    try {
      const arr = [];
      chatBox.querySelectorAll(".message").forEach(n => {
        const id = n.dataset.id || createId("m");
        const ts = (n.querySelector(".msg-meta") || {}).innerText || nowIso();
        if (n.classList.contains("file")) {
          const text = (n.querySelector(".msg-text") || {}).innerText || "";
          arr.push({ id, role: "file", file_id: n.dataset.fileId || "", original_name: text, file_type: n.dataset.fileType || "", ts });
        } else {
          const role = n.classList.contains("user") ? "user" : "bot";
          const text = (n.querySelector(".msg-text") || {}).innerText || "";
          arr.push({ id, role, text, ts });
        }
      });
      localStorage.setItem(conversationMemoryKey, JSON.stringify(arr.slice(-LOCAL_SAVE_LIMIT)));
    } catch (e) {
      console.warn("save conv error", e);
    }
  }

  function loadConversationFromLocal() {
    const data = getConversationFromLocal();
    chatBox.innerHTML = "";
    data.forEach(m => {
      if (m.role === "file") {
        // original_name was saved as the display text (e.g. "📄 filename.pdf")
        const original = (m.original_name || "").replace(/^\u{1F4C4}\s*/u, "");
        renderFileMessage({ original_name: original, file_id: m.file_id || "", file_type: m.file_type || "" });
      } else {
        renderMessage(m);
      }
    });
    if (data.length === 0) {
      addBotMessage("Hi there! 👋 I’m your AI assistant. You can chat, upload files, or talk to me.");
    }
    scrollToBottom(false);
  }

  // ---------- Basic message helpers ----------
  function addUserMessage(text) {
    const id = createId("u");
    const msg = { id, role: "user", text, ts: nowIso(), status: "sent" };
    renderMessage(msg);
    saveConversationToLocal();
    return msg;
  }

  function addBotMessage(text, status = "") {
    const id = createId("b");
    const msg = { id, role: "bot", text, ts: nowIso(), status };
    renderMessage(msg);
    saveConversationToLocal();
    return msg;
  }

  // ---------- Abort controller helpers ----------
  function startController() {
    if (currentController) {
      try { currentController.abort(); } catch {}
    }
    currentController = new AbortController();
    return currentController;
  }

  function clearController() {
    if (currentController) {
      try { currentController.abort(); } catch {}
      currentController = null;
    }
  }

  // ---------- Server communication ----------
  async function postJson(path, body, options = {}) {
    const controller = (options.signal) ? options.signal : startController().signal;
    try {
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller
      });
      const json = await res.json().catch(()=>null);
      return { ok: res.ok, status: res.status, json };
    } catch (err) {
      if (err.name === "AbortError") return { ok: false, aborted: true, error: err };
      return { ok: false, error: err };
    }
  }

  async function postForm(path, formData, options = {}) {
    const controller = (options.signal) ? options.signal : startController().signal;
    try {
      const res = await fetch(path, {
        method: "POST",
        body: formData,
        signal: controller
      });
      const json = await res.json().catch(()=>null);
      return { ok: res.ok, status: res.status, json };
    } catch (err) {
      if (err.name === "AbortError") return { ok: false, aborted: true, error: err };
      return { ok: false, error: err };
    }
  }

  // ---------- Chat send flow ----------
  async function sendMessageFlow(text, opts = {}) {
    // opts: { silent:false, command:null }
    addUserMessage(text);
    const loaderNode = showTypingLoader();
    sendBtn.disabled = true;
    uploadBtn.disabled = true;
    try {
      // handle slash commands locally when possible
      if (text.startsWith("/")) {
        const cmdResp = await handleSlashCommand(text);
        removeNodeById(loaderNode.dataset.id);
        addBotMessage(cmdResp);
        saveConversationToLocal();
        return;
      }

      // normal chat -> /chat endpoint
      const history = getConversationFromLocal();
      const res = await postJson("/chat", { message: text, history: history });
      if (!res.ok) {
        if (res.aborted) {
          removeNodeById(loaderNode.dataset.id);
          addBotMessage("(info) Request aborted.");
        } else {
          removeNodeById(loaderNode.dataset.id);
          addBotMessage(`(error) ${res.error || JSON.stringify(res.json)}`);
        }
        return;
      }
      const reply = (res.json && res.json.response) ? res.json.response : "(error) No response.";
      // typing animation: reveal reply with typewriter
      removeNodeById(loaderNode.dataset.id);
      await typewriterBot(reply);
      saveConversationToLocal();
    } catch (err) {
      removeNodeById(loaderNode.dataset.id);
      addBotMessage(`(error) ${err.message}`);
    } finally {
      sendBtn.disabled = false;
      uploadBtn.disabled = false;
    }
  }

  // ---------- Typewriter for bot replies ----------
  async function typewriterBot(text) {
    const id = createId("b");
    const piece = { id, role: "bot", text: "", ts: nowIso(), status: "delivered" };
    const node = renderMessage(piece);
    const textNode = node.querySelector(".msg-text");
    // small content: letter reveal
    if (!textNode) return;
    if (text.length < 400) {
      for (let i = 1; i <= text.length; i++) {
        textNode.innerHTML = escapeHtml(text.slice(0, i));
        await sleep(8 + Math.random() * 12);
      }
    } else {
      const chunks = smartChunkForTyping(text, 200);
      for (const c of chunks) {
        textNode.innerHTML = escapeHtml((textNode.innerText + "\n" + c).trim());
        await sleep(120 + Math.random() * 140);
      }
    }
    if (autoTTS && autoTTS.checked) speakText(text);
    saveConversationToLocal();
    scrollToBottom();
  }

  function smartChunkForTyping(text, approxLen = 200) {
    const out = [];
    let start = 0;
    while (start < text.length) {
      let end = Math.min(text.length, start + approxLen);
      if (end < text.length) {
        const slice = text.slice(start, end);
        const lastPeriod = Math.max(slice.lastIndexOf(". "), slice.lastIndexOf("\n"));
        if (lastPeriod > approxLen * 0.5) end = start + lastPeriod + 1;
      }
      out.push(text.slice(start, end).trim());
      start = end;
    }
    return out;
  }

  // ---------- Slash command handling ----------
  async function handleSlashCommand(cmdText) {
    const parts = cmdText.trim().split(/\s+/);
    const cmd = parts[0].toLowerCase();
    const payload = cmdText.replace(cmd, "").trim();

    switch (cmd) {
      case "/summarize": {
        if (!payload) return "(usage) /summarize <text or filename>";
        if (payload.includes("_") && payload.includes(".")) {
          const resp = await postJson("/explain_file", { filename: payload, bullets: 4 });
          if (resp.ok && resp.json) return resp.json.final || "(info) No summary.";
          return `(error) ${resp.error || 'failed'}`;
        } else {
          const resp = await postJson("/api/summarize", { text: payload, bullets: 3 });
          if (resp.ok && resp.json) return resp.json.summary || "(info) No summary.";
          return `(error) ${resp.error || 'failed'}`;
        }
      }
      case "/keypoints": {
        if (!payload) return "(usage) /keypoints <text>";
        {
          const resp = await postJson("/api/summarize", { text: payload, bullets: 5 });
          if (resp.ok && resp.json) return resp.json.summary || "(info) No keypoints.";
          return `(error) ${resp.error || 'failed'}`;
        }
      }
      case "/explain": {
        if (!payload) return "(usage) /explain <uploaded_filename>";
        const resp = await postJson("/explain_file", { filename: payload, bullets: 4 });
        if (resp.ok && resp.json) return resp.json.final || "(info) No explanation.";
        return `(error) ${resp.error || 'failed'}`;
      }
      case "/translate": {
        if (!payload) return "(usage) /translate <text>";
        const res = await postJson("/chat", { message: `Translate to English: ${payload}` });
        if (res.ok && res.json) return res.json.response;
        return `(error) ${res.error || 'failed'}`;
      }
      case "/analyze": {
        if (!payload) return "(usage) /analyze <text>";
        const res = await postJson("/chat", { message: `Analyze the following text and list issues and suggestions:\n\n${payload}` });
        if (res.ok && res.json) return res.json.response;
        return `(error) ${res.error || 'failed'}`;
      }
      default:
        return `(info) Unknown command: ${cmd}`;
    }
  }

  // ---------- File upload (drag & drop + multi + preview) ----------
  function setupDragDrop() {
    if (!dragDropArea) return;
    ["dragenter", "dragover"].forEach(ev => dragDropArea.addEventListener(ev, (e) => {
      e.preventDefault(); e.stopPropagation();
      dragDropArea.classList.add("drag-over");
    }));
    ["dragleave", "drop"].forEach(ev => dragDropArea.addEventListener(ev, (e) => {
      e.preventDefault(); e.stopPropagation();
      dragDropArea.classList.remove("drag-over");
    }));
    dragDropArea.addEventListener("drop", async (e) => {
      const files = Array.from(e.dataTransfer.files || []);
      if (files.length === 0) return;
      await handleFilesUpload(files);
    });
  }

  async function handleFilesUpload(files) {
    for (const file of files) {
      await previewAndUploadFile(file);
    }
  }

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
    } catch (e) {
      removeNodeById(loader.dataset.id);
      addBotMessage("(error) Upload error.");
    }
  }

  function showFilePreview(file) {
    if (!previewPanel) return;
    previewPanel.innerHTML = "";
    const name = el("div", "preview-name", `<strong>${escapeHtml(file.name)}</strong> · ${(file.size/1024|0)} KB`);
    previewPanel.appendChild(name);
    if (/image\//.test(file.type)) {
      const img = el("img", "preview-image");
      const reader = new FileReader();
      reader.onload = (ev) => { img.src = ev.target.result; };
      reader.readAsDataURL(file);
      previewPanel.appendChild(img);
    } else if (file.name.toLowerCase().endsWith(".pdf")) {
      const url = URL.createObjectURL(file);
      const embed = el("embed", "preview-pdf");
      embed.type = "application/pdf";
      embed.src = url + "#page=1";
      embed.style.width = "220px";
      embed.style.height = "140px";
      previewPanel.appendChild(embed);
      previewPanel.appendChild(el("small", "small-muted", "PDF preview may be limited in some browsers."));
    } else if (/text\/|application\/(json|xml)/.test(file.type) || /\.(txt|py|js|md|json|html)$/i.test(file.name)) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const pre = el("pre", "preview-text", escapeHtml(String(e.target.result).slice(0, 1000)));
        pre.style.maxHeight = "140px"; pre.style.overflow = "auto";
        previewPanel.appendChild(pre);
      };
      reader.readAsText(file);
    } else {
      previewPanel.appendChild(el("div", "preview-generic", "File ready for upload."));
    }
  }

  // ---------- Recording audio + upload (MediaRecorder) ----------
  async function startAudioRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      addBotMessage("(error) Audio capture not supported in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      recordedChunks = [];
      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size) recordedChunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        const blob = new Blob(recordedChunks, { type: "audio/webm" });
        const f = new File([blob], `recording-${Date.now()}.webm`, { type: blob.type });
        await previewAndUploadFile(f);
      };
      mediaRecorder.start();
      recordAudioBtn && recordAudioBtn.classList.add("recording");
      addBotMessage("(recording) Speak now...");
    } catch (err) {
      addBotMessage(`(error) ${err.message}`);
    }
  }

  function stopAudioRecording() {
    try {
      if (mediaRecorder && mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
        recordAudioBtn && recordAudioBtn.classList.remove("recording");
        addBotMessage("(recording stopped)");
      }
    } catch (err) {
      console.warn(err);
    }
  }

  // ---------- Speech synthesis (TTS) ----------
  function speakText(text) {
    if (!("speechSynthesis" in window)) return;
    const utter = new SpeechSynthesisUtterance(text);
    const speed = speedRange ? parseFloat(speedRange.value) : 1.0;
    utter.rate = clamp(speed, 0.5, 2.0);
    const accent = accentSelect ? accentSelect.value : "en-US";
    utter.lang = accent;
    utter.onstart = () => { speaking = true; pauseTTSBtn && (pauseTTSBtn.disabled = false); };
    utter.onend = () => { speaking = false; pauseTTSBtn && (pauseTTSBtn.disabled = true); };
    utter.onerror = () => { speaking = false; pauseTTSBtn && (pauseTTSBtn.disabled = true); };
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utter);
  }

  function pauseTTS() {
    if (!("speechSynthesis" in window)) return;
    if (window.speechSynthesis.speaking) window.speechSynthesis.pause();
  }
  function resumeTTS() {
    if (!("speechSynthesis" in window)) return;
    if (window.speechSynthesis.paused) window.speechSynthesis.resume();
  }

  // ---------- Regenerate / abort ----------
  async function regenerateFromMessage(msgObj) {
    const lastUser = findLastUserMessageBefore(msgObj.id);
    if (!lastUser) {
      addBotMessage("(info) No user message available to regenerate from.");
      return;
    }
    const botNode = chatBox.querySelector(`[data-id="${msgObj.id}"]`);
    if (botNode) botNode.remove();
    await sendMessageFlow(lastUser.text);
  }

  function findLastUserMessageBefore(botId) {
    const nodes = Array.from(chatBox.querySelectorAll(".message"));
    let targetIndex = nodes.findIndex(n => n.dataset.id === botId);
    if (targetIndex > 0) {
      for (let i = targetIndex - 1; i >= 0; i--) {
        const n = nodes[i];
        if (n.classList.contains("user")) {
          return { id: n.dataset.id, text: (n.querySelector(".msg-text")||{}).innerText || "" };
        }
      }
    }
    // fallback: last user anywhere
    for (let i = nodes.length - 1; i >= 0; i--) {
      const n = nodes[i];
      if (n.classList.contains("user")) {
        return { id: n.dataset.id, text: (n.querySelector(".msg-text")||{}).innerText || "" };
      }
    }
    return null;
  }

  // ---------- Save / Load conversation ----------
  function downloadConversation() {
    const arr = [];
    chatBox.querySelectorAll(".message").forEach(n => {
      const role = n.classList.contains("user") ? "user" : "bot";
      const text = (n.querySelector(".msg-text") || {}).innerText || "";
      const ts = (n.querySelector(".msg-meta") || {}).innerText || "";
      arr.push({ role, text, ts });
    });
    const blob = new Blob([JSON.stringify(arr, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `conversation-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    downloadConvBtn && flashTemporary(downloadConvBtn, "Saved");
  }

  function loadConversationFromFile(file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const arr = JSON.parse(e.target.result || "[]");
        chatBox.innerHTML = "";
        arr.forEach(m => renderMessage({ id: createId("m"), role: m.role, text: m.text, ts: m.ts }));
        saveConversationToLocal();
      } catch (err) {
        addBotMessage("(error) Unable to load conversation file.");
      }
    };
    reader.readAsText(file);
  }

  // ---------- Character counter & input autosize ----------
  function updateCharCounter() {
    if (!charCounter || !userInput) return;
    const len = (userInput.value || "").length;
    charCounter.innerText = `${len} chars`;
    charCounter.style.color = (len > 1000) ? "red" : "";
  }
  function setupAutoResize() {
    if (!userInput) return;
    userInput.addEventListener("input", updateCharCounter);
    userInput.addEventListener("input", () => {
      userInput.style.height = "auto";
      userInput.style.height = Math.min(180, userInput.scrollHeight) + "px";
    });
  }

  // ---------- Keyboard shortcuts ----------
  function setupShortcuts() {
    window.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        userInput && userInput.focus();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        downloadConversation();
      }
      if (e.key === "Escape") {
        // abort any running request and stop TTS
        clearController();
        if ("speechSynthesis" in window) window.speechSynthesis.cancel();
        addBotMessage("(info) Aborted / stopped.");
      }
    });
  }

  // ---------- Help UI ----------
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

  

  // ---------- Initialization wiring ----------
  function init() {
    loadConversationFromLocal();
    setupDragDrop();
    setupAutoResize();
    setupShortcuts();

    // Help button wiring
    if (helpBtn) {
      helpBtn.addEventListener("click", () => {
        showHelp();
        localStorage.setItem("ai_help_last_open", new Date().toISOString());
      });
    }
    if (guideBtn) {
      guideBtn.addEventListener("click", () => showHelp());
    }

    // Auto-show help for first-time users
    try {
      if (!localStorage.getItem("ai_assistant_help_shown")) {
        setTimeout(() => {
          showHelp();
          localStorage.setItem("ai_assistant_help_shown", "1");
        }, 500);
      }
    } catch (e) {
      console.warn("help autoshow failed", e);
    }

    // send button
    sendBtn && sendBtn.addEventListener("click", async () => {
      const txt = (userInput.value || "").trim();
      if (!txt) return;
      userInput.value = "";
      userInput.style.height = "auto";
      updateCharCounter();
      await sendMessageFlow(txt);
    });

    // send on Enter (Enter = send, Shift+Enter = newline)
    if (userInput) {
      userInput.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          const txt = (userInput.value || '').trim();
          if (!txt) return;
          userInput.value = '';
          userInput.style.height = 'auto';
          updateCharCounter();
          await sendMessageFlow(txt);
        }
      });
    }

    // upload button
    uploadBtn && uploadBtn.addEventListener("click", () => {
      const input = document.createElement("input");
      input.type = "file";
      input.multiple = true;
      input.accept = ".pdf,.txt,.docx,.csv,.xlsx,.png,.jpg,.jpeg,.gif,.py,.js,.html,.webm";
      input.onchange = async (e) => {
        const files = Array.from(e.target.files || []);
        if (files.length) await handleFilesUpload(files);
      };
      input.click();
    });

    // voice STT
    if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
      const SpeechRec = window.webkitSpeechRecognition || window.SpeechRecognition;
      recognition = new SpeechRec();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = "en-US";
      recognition.onstart = () => { recognizing = true; voiceBtn && voiceBtn.classList.add("recording"); addBotMessage("(listening)"); };
      recognition.onresult = (event) => {
        const t = event.results[0][0].transcript;
        // place text and send once (do not duplicate)
        if (userInput) userInput.value = t;
        updateCharCounter();
        sendMessageFlow(t);
      };
      recognition.onerror = (e) => { recognizing = false; voiceBtn && voiceBtn.classList.remove("recording"); addBotMessage("(error) Speech recognition"); };
      recognition.onend = () => { recognizing = false; voiceBtn && voiceBtn.classList.remove("recording"); };
      voiceBtn && voiceBtn.addEventListener("click", () => {
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

    // TTS controls
    pauseTTSBtn && pauseTTSBtn.addEventListener("click", () => {
      if (window.speechSynthesis && window.speechSynthesis.speaking) {
        if (window.speechSynthesis.paused) resumeTTS();
        else pauseTTS();
      }
    });

    stopVoiceBtn && stopVoiceBtn.addEventListener("click", () => {
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      addBotMessage("(TTS stopped)");
    });

    // new chat
    newChatBtn && newChatBtn.addEventListener("click", () => {
      if (!confirm("Start a new chat? This will clear the current conversation in the UI (local copy stays in browser).")) return;
      chatBox.innerHTML = "";
      addBotMessage("👋 New chat started. How can I help you?");
      saveConversationToLocal();
    });

    // permanent stop (abort & stop TTS)
    if (permanentStopBtn) permanentStopBtn.addEventListener("click", () => {
      clearController();
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      addBotMessage("(info) Request cancelled by user.");
    });

    // regenerate global
    if (regenerateBtn) regenerateBtn.addEventListener("click", async () => {
      const nodes = Array.from(chatBox.querySelectorAll(".message"));
      const reversed = nodes.slice().reverse();
      const lastBotNode = reversed.find(n => n.classList.contains("bot"));
      if (!lastBotNode) { addBotMessage("(info) Nothing to regenerate."); return; }
      const botId = lastBotNode.dataset.id;
      const botObj = { id: botId, text: (lastBotNode.querySelector(".msg-text")||{}).innerText || "" };
      await regenerateFromMessage(botObj);
    });

    // download/load conv
    downloadConvBtn && downloadConvBtn.addEventListener("click", downloadConversation);
    loadConvBtn && loadConvBtn.addEventListener("change", (e) => {
      const f = e.target.files && e.target.files[0];
      if (f) loadConversationFromFile(f);
    });

    // record audio
    if (recordAudioBtn) {
      recordAudioBtn.addEventListener("click", () => {
        if (recordAudioBtn.classList.contains("recording")) stopAudioRecording();
        else startAudioRecording();
      });
    }

    // accent/speed defaults
    if (speedRange) speedRange.value = 1.0;
    if (accentSelect) accentSelect.value = "en-US";

    // char counter
    updateCharCounter();

    // initial welcome if empty
    if (!chatBox || chatBox.children.length === 0) {
      addBotMessage("Hi there! 👋 I’m your AI assistant. You can chat, upload files, or talk to me.");
    }
  }

  // ---------- Initialize ----------
  init();

  // Expose helpers for debugging
  window.aiAssistant = {
    saveConversationToLocal,
    loadConversationFromLocal,
    downloadConversation,
    clearController,
    speakText
  };

})(); 
