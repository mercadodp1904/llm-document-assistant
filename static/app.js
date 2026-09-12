const MAX_FILE_SIZE = 20 * 1024 * 1024;
const CONVERSATION_HISTORY_KEY = "llm-doc-assistant-history";

function loadConversationHistory() {
  try {
    const savedHistory = localStorage.getItem(CONVERSATION_HISTORY_KEY);
    const parsedHistory = savedHistory ? JSON.parse(savedHistory) : [];
    return Array.isArray(parsedHistory) ? parsedHistory : [];
  } catch (error) {
    return [];
  }
}

function saveConversationHistory() {
  try {
    localStorage.setItem(
      CONVERSATION_HISTORY_KEY,
      JSON.stringify(conversationHistory),
    );
  } catch (error) {
    // Continue without persistence when browser storage is unavailable.
  }
}

const uploadedDocuments = [];
const conversationHistory = loadConversationHistory();

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
  questionInput.disabled = false;
  askButton.disabled = false;
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
    const response = await fetch("/upload", { method: "POST", body: formData });
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
  if (conversationHistory.length === 0) {
    exchangeElement.replaceChildren();
  }

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

function restoreConversationHistory() {
  if (conversationHistory.length === 0) {
    return;
  }
  exchangeElement.replaceChildren();
  for (const exchange of conversationHistory) {
    renderExchange(exchange.question, exchange.answer, exchange.sources || []);
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
    const response = await fetch("/ask", {
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
    saveConversationHistory();
    renderExchange(question, data.answer, data.sources);
    setStatus("");
  } catch (error) {
    showError(error.message || "The question could not be answered.");
  } finally {
    askButton.disabled = false;
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

restoreConversationHistory();