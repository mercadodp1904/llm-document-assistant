const MAX_FILE_SIZE = 20 * 1024 * 1024;
const TOKEN_KEY = "access_token";

const uploadedDocuments = [];
const conversationHistory = [];
const sessions = [];
const pendingRequestSessions = new Set();
let currentSessionId = null;
let conversationHistoryLoaded = false;
let documentsLoaded = false;
let sessionLoadFailed = false;
let composerState = "loading";
let openActionMenu = null;

const authScreen = document.querySelector("#auth-screen");
const shell = document.querySelector(".shell");
const loginForm = document.querySelector("#login-form");
const registerForm = document.querySelector("#register-form");
const authToggle = document.querySelector("#auth-toggle");
const authTitle = document.querySelector("#auth-title");
const authDescription = document.querySelector("#auth-description");
const loginError = document.querySelector("#login-error");
const registerError = document.querySelector("#register-error");
const logoutButton = document.querySelector("#logout-button");
const uploadForm = document.querySelector("#upload-form");
const fileInput = document.querySelector("#document-file");
const fileLabel = document.querySelector("#file-label");
const uploadButton = document.querySelector("#upload-button");
const uploadConfirmation = document.querySelector("#upload-confirmation");
const uploadedDocumentsElement = document.querySelector("#uploaded-documents");
const documentList = document.querySelector("#document-list");
const fileDrop = document.querySelector(".file-drop");
const askForm = document.querySelector("#ask-form");
const questionInput = document.querySelector("#question");
const askButton = document.querySelector("#ask-button");
const composerHelper = document.querySelector("#composer-helper");
const statusElement = document.querySelector("#status");
const exchangeElement = document.querySelector("#exchange");
const sessionListElement = document.querySelector("#session-list");
const newChatButton = document.querySelector("#new-chat-button");

function getToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

function setAuthMode(isRegistering) {
  loginForm.hidden = isRegistering;
  registerForm.hidden = !isRegistering;
  authTitle.textContent = isRegistering ? "Create your account" : "Welcome back";
  authDescription.textContent = isRegistering
    ? "Register to ask questions about your documents."
    : "Sign in to ask questions about your documents.";
  authToggle.textContent = isRegistering
    ? "Already have an account? Log in"
    : "Need an account? Register";
  loginError.hidden = true;
  registerError.hidden = true;
}

async function showMainApp() {
  authScreen.hidden = true;
  shell.hidden = false;
  try {
    await loadSessions();
    if (sessions.length === 0) {
      sessions.push(await createSession());
    }
    currentSessionId = sessions[0].session_id;
    renderSessionList();
    resetConversationView();
    await loadConversationHistory();
    await loadSessionDocuments();
  } catch (error) {
    showError(error.message || "Could not load your chats.");
  }
}

function showAuthScreen() {
  authScreen.hidden = false;
  shell.hidden = true;
  setAuthMode(false);
}

function resetConversationView() {
  uploadedDocuments.length = 0;
  conversationHistory.length = 0;
  conversationHistoryLoaded = false;
  documentsLoaded = false;
  sessionLoadFailed = false;
  renderUploadedDocuments();
  uploadConfirmation.hidden = true;
  exchangeElement.innerHTML = `<div class="empty-state"><span class="empty-icon" aria-hidden="true">?</span><h2>What would you like to know?</h2><p>Upload a PDF, then ask a question to start a conversation.</p></div>`;
  questionInput.value = "";
  setStatus("");
  setComposerState("loading");
}

function resetWorkspace() {
  resetConversationView();
  sessions.length = 0;
  currentSessionId = null;
  sessionListElement.replaceChildren();
  fileInput.value = "";
  updateFileLabel();
  setStatus("");
}

function logout() {
  sessionStorage.removeItem(TOKEN_KEY);
  resetWorkspace();
  showAuthScreen();
}

async function authenticatedFetch(url, options = {}) {
  const token = getToken();
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    logout();
    throw new Error("Your session has expired. Please log in again.");
  }
  return response;
}

function setStatus(message) {
  statusElement.textContent = message;
}

function showError(message) {
  setStatus(message);
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatInlineMarkdown(text) {
  return text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function renderMarkdown(markdown) {
  const lines = escapeHtml(markdown).split(/\r?\n/);
  const html = [];
  let paragraph = [];
  let listItems = [];
  let orderedListItems = [];

  function flushParagraph() {
    if (paragraph.length > 0) {
      html.push(`<p>${paragraph.join(" ")}</p>`);
      paragraph = [];
    }
  }

  function flushList() {
    if (listItems.length > 0) {
      html.push(`<ul>${listItems.map((item) => `<li>${item}</li>`).join("")}</ul>`);
      listItems = [];
    }
  }

  function flushOrderedList() {
    if (orderedListItems.length > 0) {
      html.push(
        `<ol>${orderedListItems.map((item) => `<li>${item}</li>`).join("")}</ol>`
      );
      orderedListItems = [];
    }
  }

  for (const line of lines) {
    const trimmedLine = line.trim();
    const heading = trimmedLine.match(/^(#{1,3})\s+(.+)$/);
    const listItem = trimmedLine.match(/^[*-]\s+(.+)$/);
    const orderedListItem = trimmedLine.match(/^\d+[.)]\s+(.+)$/);

    if (!trimmedLine) {
      flushParagraph();
      flushList();
      flushOrderedList();
    } else if (heading) {
      flushParagraph();
      flushList();
      flushOrderedList();
      const level = heading[1].length;
      html.push(`<h${level}>${formatInlineMarkdown(heading[2])}</h${level}>`);
    } else if (listItem) {
      flushParagraph();
      flushOrderedList();
      listItems.push(formatInlineMarkdown(listItem[1]));
    } else if (orderedListItem) {
      flushParagraph();
      flushList();
      orderedListItems.push(formatInlineMarkdown(orderedListItem[1]));
    } else {
      flushList();
      flushOrderedList();
      paragraph.push(formatInlineMarkdown(trimmedLine));
    }
  }

  flushParagraph();
  flushList();
  flushOrderedList();
  return html.join("");
}

function isPdf(file) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

function updateFileLabel() {
  const file = fileInput.files[0];
  fileLabel.textContent = file ? file.name : "Choose a PDF file";
}

async function readApiError(response, fallback) {
  try {
    const data = await response.json();
    return data.detail || fallback;
  } catch (error) {
    return fallback;
  }
}

async function loadSessions() {
  const response = await authenticatedFetch("/sessions");
  if (!response.ok) {
    throw new Error(await readApiError(response, "Could not load chat sessions."));
  }
  const data = await response.json();
  sessions.length = 0;
  sessions.push(...data.sessions);
}

async function createSession() {
  const response = await authenticatedFetch("/sessions", { method: "POST" });
  if (!response.ok) {
    throw new Error(await readApiError(response, "Could not start a new chat."));
  }
  return response.json();
}

function sessionLabel(session) {
  return session.title || `Chat from ${new Date(session.created_at).toLocaleString()}`;
}

function renderSessionList() {
  sessionListElement.replaceChildren();
  for (const session of sessions) {
    const item = document.createElement("li");
    item.className = session.session_id === currentSessionId ? "active" : "";
    item.addEventListener("click", () => selectSession(session.session_id));

    const title = document.createElement("span");
    title.className = "session-title";
    title.textContent = sessionLabel(session);
    title.title = title.textContent;

    const actionWrapper = document.createElement("div");
    actionWrapper.className = "session-action-wrapper";
    const { button, menu } = createActionMenu(
      [
        {
          label: "Rename",
          onClick: () => renameSession(session),
        },
        {
          label: "Delete",
          danger: true,
          onClick: () => deleteSession(session),
        },
      ],
      "Session actions"
    );
    actionWrapper.append(button, menu);
    item.append(title, actionWrapper);
    sessionListElement.append(item);
  }
}

function closeActionMenu() {
  if (!openActionMenu) {
    return;
  }
  const { button, menu } = openActionMenu;
  button.setAttribute("aria-expanded", "false");
  menu.hidden = true;
  openActionMenu = null;
}

function createActionMenu(items, label = "Actions") {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "action-menu-button";
  button.setAttribute("aria-label", label);
  button.setAttribute("aria-haspopup", "menu");
  button.setAttribute("aria-expanded", "false");
  button.textContent = "⋯";

  const menu = document.createElement("div");
  menu.className = "action-menu";
  menu.hidden = true;
  menu.setAttribute("role", "menu");

  for (const item of items) {
    const actionButton = document.createElement("button");
    actionButton.type = "button";
    actionButton.className = `action-menu-item${item.danger ? " danger" : ""}`;
    actionButton.textContent = item.label;
    actionButton.setAttribute("role", "menuitem");
    actionButton.addEventListener("click", (event) => {
      event.stopPropagation();
      closeActionMenu();
      item.onClick();
    });
    menu.append(actionButton);
  }

  button.addEventListener("click", (event) => {
    event.stopPropagation();
    if (openActionMenu && openActionMenu.button === button) {
      closeActionMenu();
      return;
    }
    closeActionMenu();
    button.setAttribute("aria-expanded", "true");
    menu.hidden = false;
    openActionMenu = { button, menu };
  });

  return { button, menu };
}

function setComposerState(state) {
  composerState = state;
  const isReady = state === "ready";
  const isSending = state === "sending";
  const hasQuestion = questionInput.value.trim().length > 0;

  questionInput.disabled = !isReady;
  askButton.disabled = !isReady || !hasQuestion;
  askButton.textContent = isSending ? "Sending..." : "Ask";
  askForm.setAttribute("aria-busy", String(isSending));

  if (state === "loading") {
    composerHelper.textContent = "Loading your documents...";
  } else if (state === "no-documents") {
    composerHelper.textContent = "Upload a document to start.";
  } else if (state === "sending") {
    composerHelper.textContent = "Preparing an answer from your documents...";
  } else {
    composerHelper.textContent = "Ask a question about your uploaded documents.";
  }
}

function updateAskAvailability() {
  if (sessionLoadFailed) {
    setComposerState("no-documents");
  } else if (!conversationHistoryLoaded || !documentsLoaded) {
    setComposerState("loading");
  } else if (pendingRequestSessions.has(currentSessionId)) {
    setComposerState("sending");
  } else if (uploadedDocuments.length > 0) {
    setComposerState("ready");
  } else {
    setComposerState("no-documents");
  }
}

function renderUploadedDocuments() {
  documentList.replaceChildren();
  for (const uploadedDocument of uploadedDocuments) {
    const item = document.createElement("li");
    item.className = "document-item";

    const fileName = document.createElement("span");
    fileName.className = "document-name";
    fileName.textContent = uploadedDocument.fileName;
    fileName.title = uploadedDocument.fileName;

    const actionWrapper = document.createElement("div");
    actionWrapper.className = "document-action-wrapper";
    const { button, menu } = createActionMenu([
      {
        label: "Delete",
        danger: true,
        onClick: () => deleteDocument(uploadedDocument.docId, uploadedDocument.fileName),
      },
    ], "Document actions");
    actionWrapper.append(button, menu);

    item.append(fileName, actionWrapper);
    documentList.append(item);
  }
  uploadedDocumentsElement.hidden = uploadedDocuments.length === 0;
}

async function onUploadSuccess(fileName, response) {
  await loadSessionDocuments();
  fileInput.value = "";
  updateFileLabel();
  const replaced = Boolean(response.replaced);
  uploadConfirmation.textContent = replaced
    ? `${fileName} was already in this chat, so the old version was replaced.`
    : `✓ ${fileName} uploaded — ready for questions`;
  uploadConfirmation.hidden = false;
  const shouldRestoreFocus =
    document.activeElement === document.body || document.activeElement === askButton;
  updateAskAvailability();
  if (shouldRestoreFocus) {
    questionInput.focus();
  }
  setStatus("");
}

async function deleteDocument(docId, fileName) {
  if (!confirm(`Delete "${fileName}" from this chat?`)) {
    return;
  }

  try {
    const response = await authenticatedFetch(
      `/sessions/${encodeURIComponent(currentSessionId)}/documents/${encodeURIComponent(docId)}`,
      { method: "DELETE" }
    );
    if (!response.ok) {
      throw new Error(await readApiError(response, "Could not delete that document."));
    }
    await loadSessionDocuments();
    setStatus("");
  } catch (error) {
    showError(error.message || "Could not delete that document.");
  }
}

async function renameSession(session) {
  const currentTitle = sessionLabel(session);
  const enteredTitle = window.prompt("Rename this chat", currentTitle);
  if (enteredTitle === null) {
    return;
  }
  const title = enteredTitle.trim();
  if (!title || title === currentTitle) {
    return;
  }

  try {
    const response = await authenticatedFetch(
      `/sessions/${encodeURIComponent(session.session_id)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      }
    );
    if (!response.ok) {
      throw new Error(await readApiError(response, "Could not rename this chat."));
    }
    const updatedSession = await response.json();
    session.title = updatedSession.title;
    renderSessionList();
    setStatus("");
  } catch (error) {
    showError(error.message || "Could not rename this chat.");
  }
}

async function deleteSession(session) {
  if (
    !confirm(
      "Delete this chat? Its conversation and uploaded documents will be permanently deleted."
    )
  ) {
    return;
  }

  const wasActive = session.session_id === currentSessionId;
  try {
    const response = await authenticatedFetch(
      `/sessions/${encodeURIComponent(session.session_id)}`,
      { method: "DELETE" }
    );
    if (!response.ok && response.status !== 404) {
      throw new Error(await readApiError(response, "Could not delete this chat."));
    }
    await loadSessions();
    if (!wasActive) {
      renderSessionList();
      setStatus("");
      return;
    }

    resetConversationView();
    currentSessionId = null;
    if (sessions.length === 0) {
      sessions.push(await createSession());
    }
    await selectSession(sessions[0].session_id);
    setStatus("");
  } catch (error) {
    showError(error.message || "Could not delete this chat.");
  }
}

async function uploadDocument() {
  const file = fileInput.files[0];
  if (!file) {
    showError("Choose a PDF before uploading.");
    return;
  }
  if (!currentSessionId) {
    showError("Select or start a chat first.");
    return;
  }
  if (!isPdf(file)) {
    showError("Only PDF files can be uploaded.");
    return;
  }
  if (file.size > MAX_FILE_SIZE) {
    showError("That file is larger than the 20 MB limit.");
    return;
  }
  const existingMatch = uploadedDocuments.some((doc) => doc.fileName === file.name);
  if (existingMatch) {
    const confirmed = confirm(`${file.name} is already in this chat. Replace it with the new upload?`);
    if (!confirmed) {
      return;
    }
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", currentSessionId);
  uploadButton.disabled = true;
  setStatus("Uploading and indexing your document...");
  try {
    const response = await authenticatedFetch("/upload", { method: "POST", body: formData });
    if (!response.ok) {
      throw new Error(await readApiError(response, "Upload failed. Try another PDF."));
    }
    await onUploadSuccess(file.name, await response.json());
  } catch (error) {
    showError(error.message || "Upload failed. Please try again.");
  } finally {
    uploadButton.disabled = false;
  }
}

function renderExchange(question, answer, sources) {
  exchangeElement.querySelector(".empty-state")?.remove();

  const exchange = document.createElement("article");
  exchange.className = "message-exchange";

  const questionLabel = document.createElement("div");
  questionLabel.className = "message user-message";
  const questionName = document.createElement("div");
  questionName.className = "message-label";
  questionName.textContent = "You";
  const questionMessage = document.createElement("p");
  questionMessage.className = "question-message";
  questionMessage.textContent = question;
  questionLabel.append(questionName, questionMessage);

  const answerLabel = document.createElement("div");
  answerLabel.className = "message assistant-message";
  const answerName = document.createElement("div");
  answerName.className = "message-label";
  answerName.textContent = "Assistant";
  const answerMessage = document.createElement("div");
  answerMessage.className = "answer-message";
  answerMessage.innerHTML = renderMarkdown(answer);
  answerLabel.append(answerName, answerMessage);

  exchange.append(questionLabel, answerLabel);
  if (sources && sources.length > 0) {
    const sourcesElement = document.createElement("section");
    sourcesElement.className = "sources";
    sourcesElement.setAttribute("aria-label", "Sources used for this answer");

    const sourcesHeading = document.createElement("h3");
    sourcesHeading.textContent = "Evidence used";
    sourcesElement.append(sourcesHeading);

    const sourceFilenames = document.createElement("p");
    sourceFilenames.className = "source-filenames";
    const filenames = [...new Set(sources.map((source) => source.filename))];
    sourceFilenames.textContent = filenames.join(", ");

    const sourceNote = document.createElement("p");
    sourceNote.className = "source-note";
    sourceNote.textContent =
      "Based on these documents. Check important details in the original file.";

    sourcesElement.append(sourceFilenames, sourceNote);
    answerLabel.append(sourcesElement);
  }

  exchangeElement.append(exchange);
  exchangeElement.scrollTop = exchangeElement.scrollHeight;
}

async function loadConversationHistory() {
  const sessionId = currentSessionId;
  let loadFailed = false;
  try {
    const response = await authenticatedFetch(`/history?session_id=${encodeURIComponent(sessionId)}`);
    if (!response.ok) {
      throw new Error(await readApiError(response, "Conversation history could not be loaded."));
    }
    const history = await response.json();
    if (sessionId !== currentSessionId) {
      return;
    }
    for (const turn of history) {
      renderExchange(turn.question, turn.answer, []);
    }
  } catch (error) {
    loadFailed = true;
    if (sessionId === currentSessionId) {
      sessionLoadFailed = true;
      showError(error.message || "Conversation history could not be loaded.");
    }
  } finally {
    if (sessionId !== currentSessionId) {
      return;
    }
    conversationHistoryLoaded = true;
    if (loadFailed) {
      sessionLoadFailed = true;
      setComposerState("no-documents");
    } else {
      updateAskAvailability();
    }
  }
}

async function loadSessionDocuments() {
  const sessionId = currentSessionId;
  let loadFailed = false;
  try {
    const response = await authenticatedFetch(
      `/sessions/${encodeURIComponent(sessionId)}/documents`
    );
    if (!response.ok) {
      throw new Error(
        await readApiError(response, "Could not load this session's documents.")
      );
    }
    const data = await response.json();
    if (sessionId !== currentSessionId) {
      return;
    }
    uploadedDocuments.length = 0;
    uploadedDocuments.push(
      ...data.documents.map((doc) => ({ docId: doc.doc_id, fileName: doc.filename }))
    );
    renderUploadedDocuments();
  } catch (error) {
    loadFailed = true;
    if (sessionId === currentSessionId) {
      sessionLoadFailed = true;
      showError(error.message || "Could not load this session's documents.");
    }
  } finally {
    if (sessionId !== currentSessionId) {
      return;
    }
    documentsLoaded = true;
    if (loadFailed) {
      sessionLoadFailed = true;
      setComposerState("no-documents");
    } else {
      updateAskAvailability();
    }
  }
}

async function selectSession(sessionId) {
  currentSessionId = sessionId;
  renderSessionList();
  resetConversationView();
  await loadConversationHistory();
  await loadSessionDocuments();
}

async function startNewChat() {
  newChatButton.disabled = true;
  try {
    const session = await createSession();
    sessions.unshift(session);
    await selectSession(session.session_id);
  } catch (error) {
    showError(error.message || "Could not start a new chat.");
  } finally {
    newChatButton.disabled = false;
  }
}

async function askQuestion() {
  const sessionId = currentSessionId;
  const question = questionInput.value.trim();
  if (!sessionId) {
    showError("Select or start a chat first.");
    return;
  }
  if (uploadedDocuments.length === 0) {
    showError("Upload a document before asking a question.");
    return;
  }
  if (!question) {
    showError("Enter a question first.");
    return;
  }

  if (pendingRequestSessions.has(sessionId)) {
    return;
  }

  pendingRequestSessions.add(sessionId);
  setComposerState("sending");
  setStatus("Searching the document and preparing an answer...");
  try {
    const historyPayload = conversationHistory.map(({ question, answer }) => ({
      question,
      answer,
    }));
    const response = await authenticatedFetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: historyPayload, session_id: sessionId }),
    });
    if (!response.ok) {
      throw new Error(await readApiError(response, "The question could not be answered."));
    }
    const data = await response.json();
    if (sessionId !== currentSessionId) {
      return;
    }
    conversationHistory.push({
      question,
      answer: data.answer,
      sources: data.sources,
      timestamp: new Date(),
    });
    renderExchange(question, data.answer, data.sources);
    if (questionInput.value.trim() === question) {
      questionInput.value = "";
    }
    setStatus("");
  } catch (error) {
    if (sessionId === currentSessionId) {
      showError(error.message || "The question could not be answered.");
    }
  } finally {
    pendingRequestSessions.delete(sessionId);
    if (sessionId !== currentSessionId) {
      return;
    }
    updateAskAvailability();
    if (document.activeElement === document.body || document.activeElement === askButton) {
      questionInput.focus();
    }
  }
}

async function submitAuthForm(form, errorElement, isRegistering) {
  errorElement.hidden = true;
  const formData = new FormData(form);
  const submitButton = form.querySelector("button[type=submit]");
  submitButton.disabled = true;
  try {
    const response = await fetch(isRegistering ? "/register" : "/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: formData.get("email"),
        password: formData.get("password"),
      }),
    });
    if (!response.ok) {
      throw new Error(await readApiError(response, "Authentication failed. Please try again."));
    }
    if (isRegistering) {
      form.reset();
      setAuthMode(false);
      loginError.textContent = "Account created. Log in to continue.";
      loginError.hidden = false;
      return;
    }
    const data = await response.json();
    sessionStorage.setItem(TOKEN_KEY, data.access_token);
    form.reset();
    await showMainApp();
  } catch (error) {
    errorElement.textContent = error.message || "Authentication failed. Please try again.";
    errorElement.hidden = false;
  } finally {
    submitButton.disabled = false;
  }
}

fileInput.addEventListener("change", updateFileLabel);
fileDrop.addEventListener("dragover", (event) => {
  event.preventDefault();
  fileDrop.classList.add("dragover");
});
fileDrop.addEventListener("dragleave", () => fileDrop.classList.remove("dragover"));
fileDrop.addEventListener("drop", (event) => {
  event.preventDefault();
  fileDrop.classList.remove("dragover");
  if (event.dataTransfer.files.length > 0) {
    fileInput.files = event.dataTransfer.files;
    updateFileLabel();
  }
});
uploadForm.addEventListener("submit", (event) => {
  event.preventDefault();
  uploadDocument();
});
askForm.addEventListener("submit", (event) => {
  event.preventDefault();
  askQuestion();
});
questionInput.addEventListener("input", () => {
  if (composerState === "ready") {
    setComposerState("ready");
  }
});
document.addEventListener("click", (event) => {
  if (!openActionMenu) {
    return;
  }
  const { button, menu } = openActionMenu;
  if (!button.contains(event.target) && !menu.contains(event.target)) {
    closeActionMenu();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && openActionMenu) {
    closeActionMenu();
  }
});

authToggle.addEventListener("click", () => setAuthMode(registerForm.hidden));
loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await submitAuthForm(loginForm, loginError, false);
});
registerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitAuthForm(registerForm, registerError, true);
});
logoutButton.addEventListener("click", logout);
newChatButton.addEventListener("click", startNewChat);

if (getToken()) {
  showMainApp();
} else {
  showAuthScreen();
}
