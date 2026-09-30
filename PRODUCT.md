# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Plain HTML, CSS, and JavaScript with no framework or build step; FastAPI; Google Gemini behind a swappable wrapper; local embeddings with in-memory cosine retrieval over vectors stored in SQLite; JWT authentication; pytest. AWS is a future deployment target and the product is not currently deployed.

## Users

Individual learners and researchers who upload PDFs and ask questions while studying or researching.

## Product Purpose

The product lets a user upload PDF documents and ask questions answered from those documents. It extracts text, chunks and embeds the content, retrieves relevant context, and generates answers grounded in the user's files. Success means the user can understand a document faster while checking where each answer came from.

## Positioning

Trust and verifiability: answers are grounded in the user's own PDFs, and the product makes sources, citations, and the documents included in the current session clear and easy to check.

## Operating Context

Users authenticate, create chat sessions, upload one or more PDFs, and ask questions about the documents in the active session. They may use the product for study or research and should be able to inspect the source document associated with an answer. The project is also demonstrated as a portfolio project, so its behavior and architecture should remain easy to explain and demo.

## Capabilities and Constraints

- Users can register and log in with JWT-based authentication.
- Users can create, rename, list, and delete chat sessions.
- Users can upload PDF files, extract text, create overlapping chunks, generate embeddings, and replace or delete session documents.
- Users can ask questions across the documents in a session and receive generated answers with source references.
- Keep the existing plain frontend and FastAPI architecture easy to explain. Do not add a framework or build step.
- Keep the LLM provider behind its wrapper so it can be swapped without changing business logic.
- Keep retrieval local and avoid a hosted vector database.
- Do not imply certainty beyond the source material.
- Design work is limited to the frontend files in static/. Do not change API routes, response shapes, or backend code.
- Do not add CDN scripts or other external runtime dependencies. Prefer system fonts or self-hosted font files.
- Users can see which documents each answer was based on.

## Brand Commitments

There is no existing brand. Use a simple text wordmark, one accent color, one typeface family, and a light theme first. The product should feel calm, professional, and simple, without decorative excess.

## Evidence on Hand

The repository contains the working application, API, tests, and [README.md](README.md) describing the RAG pipeline and setup. The real app and its README are the source for screenshots and demos. There are no confirmed testimonials, performance metrics, deployment claims, or other marketing evidence; future work must not invent them.

## Product Principles

- Make every answer checkable against the user's documents.
- Keep document and session state visible and understandable.
- Prefer explainable, replaceable components over opaque infrastructure.
- Keep the experience focused on reading, asking, and verifying.
- Preserve a simple, credible demo path for portfolio evaluation.

## Accessibility & Inclusion

Meet WCAG 2.1 AA contrast. Keep all functionality keyboard-usable with visible focus states. Use appropriate labels and ARIA state attributes for menus, close menus with Escape, announce new chat answers to screen readers, respect `prefers-reduced-motion`, and never rely on color alone. The sidebar must not scroll horizontally, and the layout must work at narrow widths.