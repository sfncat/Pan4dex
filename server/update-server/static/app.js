(() => {
  "use strict";

  const csrf = document.querySelector('meta[name="csrf-token"]');
  const csrfToken = csrf ? csrf.content : "";

  // 复制 SHA-256 / 下载地址：优先 Clipboard API，失败退回临时 textarea
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const text = button.getAttribute("data-copy") || "";
      let ok = false;
      try {
        await navigator.clipboard.writeText(text);
        ok = true;
      } catch (_error) {
        const area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        try { ok = document.execCommand("copy"); } catch (_e) { ok = false; }
        document.body.removeChild(area);
      }
      const previous = button.getAttribute("aria-label") || "";
      button.setAttribute("aria-label", ok ? "已复制" : "复制失败");
      button.classList.add("copied");
      window.setTimeout(() => {
        button.setAttribute("aria-label", previous);
        button.classList.remove("copied");
      }, 1400);
    });
  });

  // 删除/撤下前的确认
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = form.getAttribute("data-confirm") || "确定执行该操作？";
      if (!window.confirm(message)) {
        event.preventDefault();
      }
    });
  });

  const form = document.getElementById("upload-form");
  if (!form) return;

  const fileInput = document.getElementById("artifact");
  const platformSelect = document.getElementById("platform");
  const versionInput = document.getElementById("version");
  const dropZone = document.getElementById("drop-zone");
  const submitButton = document.getElementById("upload-submit");
  const progress = document.getElementById("upload-progress");
  const status = document.getElementById("upload-status");

  const setStatus = (text) => {
    if (status) status.textContent = text;
  };

  const formatSize = (bytes) => `${(bytes / 1048576).toFixed(1)} MB`;

  const detectFromName = (name) => {
    const match = name.match(/pan4dex-(\d+\.\d+\.\d+)/);
    if (match) versionInput.value = match[1];
    if (name.endsWith("-linux")) {
      platformSelect.value = "linux";
    } else if (name.endsWith(".zip")) {
      platformSelect.value = "windows";
    }
  };

  const describeFile = () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      setStatus("");
      return;
    }
    detectFromName(file.name);
    setStatus(`${file.name} · ${formatSize(file.size)}`);
  };

  fileInput.addEventListener("change", describeFile);

  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("dragging");
    });
  });
  ["dragleave", "dragend", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove("dragging"));
  });
  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    if (event.dataTransfer && event.dataTransfer.files.length) {
      fileInput.files = event.dataTransfer.files;
      describeFile();
    }
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      setStatus("请选择产物文件");
      fileInput.focus();
      return;
    }
    if (!/^\d+\.\d+\.\d+$/.test(versionInput.value.trim())) {
      setStatus("版本号格式应为 x.y.z，例如 1.9.028");
      versionInput.focus();
      return;
    }

    const body = new FormData(form);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.action, true);
    xhr.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    if (csrfToken) xhr.setRequestHeader("X-CSRF-Token", csrfToken);

    submitButton.disabled = true;
    progress.hidden = false;
    progress.value = 0;
    setStatus("准备上传…");

    xhr.upload.addEventListener("progress", (progressEvent) => {
      if (!progressEvent.lengthComputable) return;
      const percent = Math.round((progressEvent.loaded / progressEvent.total) * 100);
      progress.value = percent;
      setStatus(`上传中 ${percent}%`);
    });

    xhr.addEventListener("load", () => {
      let payload = {};
      try { payload = JSON.parse(xhr.responseText); } catch (_error) { payload = {}; }
      if (xhr.status >= 200 && xhr.status < 300) {
        progress.value = 100;
        setStatus(payload.message || "上传成功，正在刷新…");
        window.setTimeout(() => window.location.reload(), 700);
      } else {
        submitButton.disabled = false;
        progress.hidden = true;
        setStatus(payload.message || `上传失败（HTTP ${xhr.status}）`);
      }
    });

    xhr.addEventListener("error", () => {
      submitButton.disabled = false;
      progress.hidden = true;
      setStatus("网络错误，上传失败；请确认服务器仍在运行");
    });

    xhr.send(body);
  });
})();
