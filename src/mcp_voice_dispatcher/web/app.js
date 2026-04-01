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
const approvalState = document.getElementById("approvalState");
const approvalHint = document.getElementById("approvalHint");
const approvalPayload = document.getElementById("approvalPayload");
const approveAction = document.getElementById("approveAction");

let mediaRecorder = null;
let audioChunks = [];
let recordedBlob = null;
let pendingApproval = null;

function setStatus(text, isError = false) {
  requestStatus.textContent = text;
  requestStatus.style.color = isError ? "#9f2f21" : "";
}

function setApprovalState(text, isError = false) {
  approvalState.textContent = text;
  approvalState.style.color = isError ? "#9f2f21" : "";
}

function clearApproval() {
  pendingApproval = null;
  approvalPayload.value = "";
  approvalHint.textContent =
    "Preview a command to review the generated payload before any side effect is allowed.";
  setApprovalState("No pending approval");
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

  const approval = report.approval;
  if (!approval?.required) {
    clearApproval();
    return;
  }

  pendingApproval = approval;
  approvalPayload.value = JSON.stringify(approval.editable_payload ?? {}, null, 2);
  if (approval.confirmed) {
    approvalHint.textContent = "The reviewed payload was approved and executed.";
    setApprovalState("Confirmed");
    return;
  }

  if (approval.confidence_ok) {
    approvalHint.textContent = `Confidence ${Number(report.intent?.confidence ?? 0).toFixed(2)} meets the execution threshold ${Number(approval.confidence_threshold ?? 0).toFixed(2)}. Review and approve when ready.`;
    setApprovalState("Awaiting approval");
  } else {
    approvalHint.textContent = `Confidence ${Number(report.intent?.confidence ?? 0).toFixed(2)} is below the execution threshold ${Number(approval.confidence_threshold ?? 0).toFixed(2)}. Rephrase the command before executing.`;
    setApprovalState("Blocked by threshold", true);
  }
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

async function postAudio() {
  const file = audioFileInput.files[0];
  const blob = file || recordedBlob;
  if (!blob) {
    throw new Error("Record or upload audio first.");
  }
  const formData = new FormData();
  const filename = file?.name || "browser-recording.webm";
  formData.append("audio", blob, filename);
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
    setStatus("Preparing review...");
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
      approval: null,
    };
  });
});

document.getElementById("previewText").addEventListener("click", () => {
  handleRequest(() =>
    postJson("/api/dispatch/text", {
      command: commandText.value,
    }),
  );
});

document.getElementById("previewAudio").addEventListener("click", () => {
  handleRequest(() => postAudio());
});

approveAction.addEventListener("click", () => {
  handleRequest(async () => {
    if (!pendingApproval?.required || !pendingApproval.confirmation_id) {
      throw new Error("Preview an actionable command before approving.");
    }
    const payload = JSON.parse(approvalPayload.value || "{}");
    return postJson("/api/dispatch/confirm", {
      confirmation_id: pendingApproval.confirmation_id,
      confirm: true,
      payload,
    });
  });
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

clearApproval();
loadTools()
  .then(() => setStatus("Ready"))
  .catch((error) => setStatus(error.message, true));
