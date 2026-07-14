document.addEventListener("DOMContentLoaded", () => {
  const OK_EXT = [".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4", ".aac", ".txt", ".md", ".srt", ".vtt"];
  // Можно закинуть много папок/файлов — сервер ставит все в очередь и анализирует параллельно
  const MAX_FOLDERS = 50;

  function fileExt(name) {
    const i = name.lastIndexOf(".");
    return i >= 0 ? name.slice(i).toLowerCase() : "";
  }

  function isOkFile(file) {
    return OK_EXT.includes(fileExt(file.name));
  }

  function fileKey(file) {
    return `${file.name}|${file.size}|${file.lastModified}`;
  }

  const uploadZone = document.getElementById("upload-zone");
  const fileInput = document.getElementById("file-input");
  const folderInput = document.getElementById("folder-input");
  const fileCount = document.getElementById("file-count");
  const fileList = document.getElementById("file-list");
  const uploadForm = document.getElementById("upload-form");
  const btnPickFiles = document.getElementById("btn-pick-files");
  const btnPickFolder = document.getElementById("btn-pick-folder");
  const btnClear = document.getElementById("btn-clear-files");
  const btnUpload = document.getElementById("btn-upload");

  let selectedFiles = [];
  let foldersAdded = 0;

  function refreshFileUI() {
    const ok = selectedFiles;
    const total = ok.length;

    if (fileCount) {
      if (!total) {
        fileCount.textContent = "Добавьте до 7 папок подряд или выберите файлы mp3, wav, txt";
      } else {
        const folderPart = foldersAdded ? ` · папок: ${foldersAdded}/${MAX_FOLDERS}` : "";
        fileCount.textContent = `Готово к загрузке: ${total} файл(ов)${folderPart}`;
      }
    }

    if (fileList) {
      if (total && total <= 10) {
        fileList.innerHTML = ok.map((f) => `<span class="upload-tag">${f.name}</span>`).join("");
      } else if (total > 10) {
        fileList.innerHTML = ok.slice(0, 6).map((f) => `<span class="upload-tag">${f.name}</span>`).join("")
          + `<span class="upload-tag">+ ещё ${total - 6} файлов</span>`;
      } else {
        fileList.innerHTML = "";
      }
    }

    if (btnUpload) btnUpload.disabled = total === 0;
    if (btnClear) btnClear.disabled = total === 0;
    if (btnPickFolder) {
      btnPickFolder.disabled = foldersAdded >= MAX_FOLDERS;
      btnPickFolder.textContent = foldersAdded >= MAX_FOLDERS
        ? `📁 Папок уже ${MAX_FOLDERS}`
        : `📁 Добавить папку (${foldersAdded}/${MAX_FOLDERS})`;
    }
  }

  function appendFiles(fileListRaw, sourceLabel) {
    const all = Array.from(fileListRaw || []);
    const ok = all.filter(isOkFile);
    const bad = all.length - ok.length;

    if (sourceLabel === "из папки") {
      if (!ok.length) {
        alert("В папке нет mp3, wav или txt файлов.");
        return;
      }
      if (foldersAdded >= MAX_FOLDERS) {
        alert(`Можно добавить не больше ${MAX_FOLDERS} папок за раз. Сначала загрузите выбранное.`);
        return;
      }
      foldersAdded += 1;
    }

    const existing = new Set(selectedFiles.map(fileKey));
    let added = 0;
    for (const f of ok) {
      const key = fileKey(f);
      if (!existing.has(key)) {
        selectedFiles.push(f);
        existing.add(key);
        added += 1;
      }
    }

    if (!added && sourceLabel === "из папки") {
      foldersAdded = Math.max(0, foldersAdded - 1);
      alert("Файлы из этой папки уже добавлены.");
      return;
    }

    if (bad && !added && sourceLabel !== "из папки") {
      alert(`Найдено ${all.length} файлов, но ни один не mp3/wav/txt.`);
    }

    refreshFileUI();
  }

  function clearFiles() {
    selectedFiles = [];
    foldersAdded = 0;
    refreshFileUI();
  }

  if (btnPickFiles && fileInput) {
    btnPickFiles.addEventListener("click", (e) => {
      e.stopPropagation();
      fileInput.value = "";
      fileInput.click();
    });
    fileInput.addEventListener("change", () => {
      appendFiles(fileInput.files, "с компьютера");
    });
  }

  if (btnPickFolder && folderInput) {
    btnPickFolder.addEventListener("click", (e) => {
      e.stopPropagation();
      if (foldersAdded >= MAX_FOLDERS) return;
      folderInput.value = "";
      folderInput.click();
    });
    folderInput.addEventListener("change", () => {
      appendFiles(folderInput.files, "из папки");
    });
  }

  if (btnClear) {
    btnClear.addEventListener("click", (e) => {
      e.preventDefault();
      clearFiles();
    });
  }

  if (uploadZone) {
    uploadZone.addEventListener("click", () => {
      if (fileInput) {
        fileInput.value = "";
        fileInput.click();
      }
    });

    uploadZone.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.stopPropagation();
      uploadZone.classList.add("dragover");
    });

    uploadZone.addEventListener("dragleave", (e) => {
      e.preventDefault();
      uploadZone.classList.remove("dragover");
    });

    uploadZone.addEventListener("drop", (e) => {
      e.preventDefault();
      e.stopPropagation();
      uploadZone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files.length) {
        appendFiles(e.dataTransfer.files, "перетащили");
      }
    });
  }

  function uploadWithProgress(formData) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/upload");
      xhr.withCredentials = true;
      xhr.timeout = 900000;
      xhr.setRequestHeader("Accept", "application/json");
      xhr.upload.onprogress = (ev) => {
        if (btnUpload && ev.lengthComputable) {
          const pct = Math.round((ev.loaded / ev.total) * 100);
          btnUpload.textContent = `Загрузка ${pct}% (${selectedFiles.length} файлов)...`;
        }
      };
      xhr.onload = () => {
        if (xhr.status === 401) {
          resolve({ auth: true });
          return;
        }
        let data = null;
        try {
          data = JSON.parse(xhr.responseText || "{}");
        } catch (_) {
          data = null;
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve({ ok: true, data });
          return;
        }
        let detail = (data && data.detail) || xhr.responseText || `Ошибка ${xhr.status}`;
        // FastAPI иногда отдаёт detail массивом — не показываем «[object Object]» / «1»
        if (Array.isArray(detail)) {
          detail = detail.map((d) => (d && (d.msg || d.message)) || String(d)).join("; ");
        } else if (detail && typeof detail === "object") {
          detail = detail.msg || detail.message || JSON.stringify(detail);
        }
        if (!detail || detail === "1" || detail === "0") {
          detail = "Сервер не принял файлы. Попробуйте ещё раз или меньше файлов за раз.";
        }
        reject(new Error(String(detail)));
      };
      xhr.onerror = () => reject(new Error("Сеть недоступна. Проверьте интернет и обновите страницу."));
      xhr.ontimeout = () => reject(new Error("Загрузка слишком долгая. Попробуйте меньше папок за раз или повторите."));
      xhr.send(formData);
    });
  }

  if (uploadForm) {
    uploadForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      if (!selectedFiles.length) {
        alert("Сначала выберите mp3, wav или txt файлы.");
        return;
      }

      const fd = new FormData();
      selectedFiles.forEach((f) => fd.append("files", f, f.name));

      if (btnUpload) {
        btnUpload.disabled = true;
        btnUpload.textContent = `Загрузка ${selectedFiles.length} файлов и запуск ИИ...`;
      }

      try {
        const result = await uploadWithProgress(fd);
        if (result.auth) {
          window.location.href = "/login";
          return;
        }
        window.location.href = (result.data && result.data.redirect) || "/dashboard";
      } catch (err) {
        const msg = (err.message || "Ошибка загрузки").slice(0, 400);
        alert("Не удалось загрузить: " + msg);
        if (btnUpload) {
          btnUpload.disabled = selectedFiles.length > 0;
          btnUpload.textContent = `Загрузить и запустить ИИ-анализ (${selectedFiles.length})`;
        }
      }
    });
  }

  refreshFileUI();

  const processingCard = document.getElementById("processing-card");
  if (processingCard) {
    const timer = setInterval(() => window.location.reload(), 5000);
    window.addEventListener("beforeunload", () => clearInterval(timer));
  }

  const sidebarToggle = document.getElementById("sidebar-toggle");
  const sidebar = document.getElementById("sidebar");
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener("click", () => sidebar.classList.toggle("open"));
    document.addEventListener("click", (e) => {
      if (!sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
        sidebar.classList.remove("open");
      }
    });
  }

  const tabs = document.getElementById("analysis-tabs");
  if (tabs) {
    const buttons = tabs.querySelectorAll(".tab-btn");
    const panels = document.querySelectorAll(".tab-panel");
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = btn.dataset.tab;
        buttons.forEach((b) => b.classList.remove("active"));
        panels.forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        const panel = document.querySelector(`[data-panel="${target}"]`);
        if (panel) panel.classList.add("active");
      });
    });
  }

  const chatForm = document.getElementById("chat-form");
  const chatMessages = document.getElementById("chat-messages");
  const chatInput = document.getElementById("chat-question");
  const chatSubmit = document.getElementById("chat-submit");
  const aiChat = document.getElementById("ai-chat");

  if (chatForm && chatMessages && chatInput && aiChat) {
    const recordingId = aiChat.dataset.recordingId;
    chatForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const question = chatInput.value.trim();
      if (!question) return;
      appendMessage("user", question);
      chatInput.value = "";
      chatSubmit.disabled = true;
      const typing = appendMessage("ai", "Думаю...", true);
      try {
        const body = new FormData();
        body.append("question", question);
        const res = await fetch(`/recording/${recordingId}/ask`, { method: "POST", body });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Ошибка");
        typing.querySelector(".chat-bubble").textContent = data.answer;
        typing.classList.remove("chat-typing");
      } catch (err) {
        typing.querySelector(".chat-bubble").textContent = "Ошибка: " + err.message;
        typing.classList.remove("chat-typing");
      } finally {
        chatSubmit.disabled = false;
        chatMessages.scrollTop = chatMessages.scrollHeight;
      }
    });

    function appendMessage(role, text, isTyping = false) {
      const msg = document.createElement("div");
      msg.className = `chat-msg chat-msg-${role}${isTyping ? " chat-typing" : ""}`;
      msg.innerHTML = `<div class="chat-avatar">${role === "ai" ? "🤖" : "👤"}</div><div class="chat-bubble">${text}</div>`;
      chatMessages.appendChild(msg);
      chatMessages.scrollTop = chatMessages.scrollHeight;
      return msg;
    }
  }
});