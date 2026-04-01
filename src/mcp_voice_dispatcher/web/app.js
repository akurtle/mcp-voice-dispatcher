const toolList = document.getElementById("toolList");
const requestStatus = document.getElementById("requestStatus");
const routeValue = document.getElementById("routeValue");
const confidenceValue = document.getElementById("confidenceValue");
const templateValue = document.getElementById("templateValue");
const sourceValue = document.getElementById("sourceValue");
const transcriptValue = document.getElementById("transcriptValue");
const intentJson = document.getElementById("intentJson");
const toolJson = document.getElementById("toolJson");
const toolResponseText = document.getElementById("toolResponseText");
const recordToggle = document.getElementById("recordToggle");
const recordState = document.getElementById("recordState");
const audioFileInput = document.getElementById("audioFile");
const commandText = document.getElementById("commandText");
const dryRun = document.getElementById("dryRun");

let mediaRecorder = null;
let audioChunks = [];
let recordedBlob = null;

function setStatus(text, isError = false) {
  requestStatus.textContent = text;
  requestStatus.style.color = isError ? "#9f2f21" : "";
}

function renderResult(report) {
  routeValue.textContent = report.intent?.route ?? "noop";
  confidenceValue.textContent = Number(report.intent?.confidence ?? 0).toFixed(2);
  templateValue.textContent = report.prompt_template ?? "general";
  sourceValue.textContent = report.source ?? "unknown";
  transcriptValue.textContent = report.transcript || "No transcript returned.";
  intentJson.textContent = JSON.stringify(report.intent ?? {}, null, 2);
  toolJson.textContent = JSON.stringify(report.tool_result ?? {}, null, 2);
  toolResponseText.textContent = report.tool_result_text || "No tool executed yet.";
}

function renderTools(tools) {
  toolList.innerHTML = "";
  for (const tool of tools) {
    const card = document.createElement("article");
    card.className = "tool-card";
    const title = document.createElement("h3");
    title.textContent = tool.name;
    const description = document.createElement("p");
    description.textContent = tool.description || "No description";
    const schemaWrap = document.createElement("div");
    for (const key of Object.keys(tool.inputSchema?.properties || {})) {
      const tag = document.createElement("span");
      tag.className = "schema-tag";
      tag.textContent = key;
      schemaWrap.appendChild(tag);
    }
    card.append(title, description, schemaWrap);
    toolList.appendChild(card);
  }
}

async function loadTools() {
  const response = await fetch("/api/tools");
  if (!response.ok) {
    throw new Error(await response.text());
  }
  renderTools(await response.json());
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || "Request failed");
  }
  return body;
}

async function postAudio(dryRunValue) {
  const file = audioFileInput.files[0];
  const blob = file || recordedBlob;
  if (!blob) {
    throw new Error("Record or upload audio first.");
  }
  const formData = new FormData();
  const filename = file?.name || "browser-recording.webm";
  formData.append("audio", blob, filename);
  formData.append("dry_run", String(dryRunValue));
  const response = await fetch("/api/dispatch/audio", {
    method: "POST",
    body: formData,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(body.detail || "Audio request failed");
  }
  return body;
}

async function handleRequest(action) {
  try {
    setStatus("Dispatching...");
    setButtonsDisabled(true);
    const report = await action();
    renderResult(report);
    setStatus(report.tool_result ? "Tool executed" : "Intent preview ready");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setButtonsDisabled(false);
  }
}

function setButtonsDisabled(disabled) {
  for (const button of document.querySelectorAll("button")) {
    button.disabled = disabled;
  }
}

async function toggleRecording() {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    return;
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioChunks = [];
  mediaRecorder = new MediaRecorder(stream);
  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) {
      audioChunks.push(event.data);
    }
  };
  mediaRecorder.onstop = () => {
    recordedBlob = new Blob(audioChunks, { type: "audio/webm" });
    recordState.textContent = "Recording captured";
    recordToggle.textContent = "Record Again";
    for (const track of stream.getTracks()) {
      track.stop();
    }
  };
  mediaRecorder.start();
  recordedBlob = null;
  audioFileInput.value = "";
  recordState.textContent = "Recording in progress";
  recordToggle.textContent = "Stop Recording";
}

document.getElementById("refreshTools").addEventListener("click", () => {
  handleRequest(async () => {
    await loadTools();
    return {
      intent: {},
      transcript: "Tool catalog refreshed.",
      prompt_template: "n/a",
      source: "dashboard",
      tool_result: null,
      tool_result_text: null,
    };
  });
});

document.getElementById("previewText").addEventListener("click", () => {
  handleRequest(() =>
    postJson("/api/dispatch/text", {
      command: commandText.value,
      dry_run: true,
    }),
  );
});

document.getElementById("executeText").addEventListener("click", () => {
  handleRequest(() =>
    postJson("/api/dispatch/text", {
      command: commandText.value,
      dry_run: dryRun.checked ? true : false,
    }),
  );
});

document.getElementById("previewAudio").addEventListener("click", () => {
  handleRequest(() => postAudio(true));
});

document.getElementById("executeAudio").addEventListener("click", () => {
  handleRequest(() => postAudio(dryRun.checked ? true : false));
});

recordToggle.addEventListener("click", async () => {
  try {
    await toggleRecording();
  } catch (error) {
    setStatus(error.message, true);
  }
});

audioFileInput.addEventListener("change", () => {
  recordedBlob = null;
  if (audioFileInput.files[0]) {
    recordState.textContent = `Loaded ${audioFileInput.files[0].name}`;
    recordToggle.textContent = "Start Recording";
  }
});

loadTools()
  .then(() => setStatus("Ready"))
  .catch((error) => setStatus(error.message, true));
