const MAX_FILE_SIZE = 20 * 1024 * 1024;
const TOKEN_KEY = "access_token";

const uploadedDocuments = [];
const conversationHistory = [];
let conversationHistoryLoaded = false;

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
const statusElement = document.querySelector("#status");
const exchangeElement = document.querySelector("#exchange");

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

function showMainApp() {
  authScreen.hidden = true;
  shell.hidden = false;
  conversationHistoryLoaded = false;
  loadConversationHistory();
}

function showAuthScreen() {
  authScreen.hidden = false;
  shell.hidden = true;
  setAuthMode(false);
}

function resetWorkspace() {
  uploadedDocuments.length = 0;
  conversationHistory.length = 0;
  conversationHistoryLoaded = false;
  documentList.replaceChildren();
  uploadedDocumentsElement.hidden = true;
  uploadConfirmation.hidden = true;
  exchangeElement.innerHTML = `<div class="empty-state"><span class="empty-icon" aria-hidden="true">?</span><h2>What would you like to know?</h2><p>Upload a PDF, then ask a question to start a conversation.</p></div>`;
  questionInput.value = "";
  questionInput.disabled = true;
  askButton.disabled = true;
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

  for (const line of lines) {
    const trimmedLine = line.trim();
    const heading = trimmedLine.match(/^(#{1,3})\s+(.+)$/);
    const listItem = trimmedLine.match(/^[*-]\s+(.+)$/);

    if (!trimmedLine) {
      flushParagraph();
      flushList();
    } else if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      html.push(`<h${level}>${formatInlineMarkdown(heading[2])}</h${level}>`);
    } else if (listItem) {
      flushParagraph();
      listItems.push(formatInlineMarkdown(listItem[1]));
    } else {
      flushList();
      paragraph.push(formatInlineMarkdown(trimmedLine));
    }
  }

  flushParagraph();
  flushList();
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

function renderUploadedDocuments() {
  documentList.replaceChildren();
  for (const uploadedDocument of uploadedDocuments) {
    const item = document.createElement("li");
    item.textContent = uploadedDocument.fileName;
    documentList.append(item);
  }
  uploadedDocumentsElement.hidden = uploadedDocuments.length === 0;
}

function onUploadSuccess(fileName, response) {
  uploadedDocuments.push({ docId: response.doc_id, fileName });
  fileLabel.textContent = fileName;
  uploadConfirmation.textContent = `✓ ${fileName} uploaded — ready for questions`;
  uploadConfirmation.hidden = false;
  renderUploadedDocuments();
  questionInput.disabled = !conversationHistoryLoaded;
  askButton.disabled = !conversationHistoryLoaded;
  setStatus("");
}

async function uploadDocument() {
  const file = fileInput.files[0];
  if (!file) {
    showError("Choose a PDF before uploading.");
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

  const formData = new FormData();
  formData.append("file", file);
  uploadButton.disabled = true;
  setStatus("Uploading and indexing your document...");
  try {
    const response = await authenticatedFetch("/upload", { method: "POST", body: formData });
    if (!response.ok) {
      throw new Error(await readApiError(response, "Upload failed. Try another PDF."));
    }
    onUploadSuccess(file.name, await response.json());
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
    const sourcesElement = document.createElement("p");
    sourcesElement.className = "sources";
    const filenames = [...new Set(sources.map((source) => source.filename))];
    sourcesElement.textContent = `Sources: ${filenames.join(", ")}`;
    answerLabel.append(sourcesElement);
  }

  exchangeElement.append(exchange);
  exchangeElement.scrollTop = exchangeElement.scrollHeight;
}

async function loadConversationHistory() {
  try {
    const response = await authenticatedFetch("/history");
    if (!response.ok) {
      throw new Error(await readApiError(response, "Conversation history could not be loaded."));
    }
    const history = await response.json();
    for (const turn of history) {
      renderExchange(turn.question, turn.answer, []);
    }
  } catch (error) {
    showError(error.message || "Conversation history could not be loaded.");
  } finally {
    conversationHistoryLoaded = true;
    if (uploadedDocuments.length > 0) {
      questionInput.disabled = false;
      askButton.disabled = false;
    }
  }
}

async function askQuestion() {
  const question = questionInput.value.trim();
  if (uploadedDocuments.length === 0) {
    showError("Upload a document before asking a question.");
    return;
  }
  if (!question) {
    showError("Enter a question first.");
    return;
  }

  askButton.disabled = true;
  setStatus("Searching the document and preparing an answer...");
  try {
    const historyPayload = conversationHistory.map(({ question, answer }) => ({
      question,
      answer,
    }));
    const response = await authenticatedFetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: historyPayload }),
    });
    if (!response.ok) {
      throw new Error(await readApiError(response, "The question could not be answered."));
    }
    const data = await response.json();
    conversationHistory.push({
      question,
      answer: data.answer,
      sources: data.sources,
      timestamp: new Date(),
    });
    renderExchange(question, data.answer, data.sources);
    setStatus("");
  } catch (error) {
    showError(error.message || "The question could not be answered.");
  } finally {
    askButton.disabled = false;
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
    showMainApp();
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
authToggle.addEventListener("click", () => setAuthMode(registerForm.hidden));
loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitAuthForm(loginForm, loginError, false);
});
registerForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitAuthForm(registerForm, registerError, true);
});
logoutButton.addEventListener("click", logout);

if (getToken()) {
  showMainApp();
} else {
  showAuthScreen();
}
