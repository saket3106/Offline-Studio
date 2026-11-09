// Imported only by Vite DEV with ?mock. Never contacts native tools or the network.
const signal = () => {
  const listeners = new Set();
  return {
    connect: (f) => listeners.add(f),
    disconnect: (f) => listeners.delete(f),
    emit: (v) => listeners.forEach((f) => f(v)),
  };
};
const encode = (value) => JSON.stringify(value);
export function createMockAdapter({
  stress = new URLSearchParams(location.search).has("stress"),
} = {}) {
  const event = signal(),
    historyChanged = signal(),
    statusChanged = signal();
  const illustration =
    "data:image/svg+xml," +
    encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#26262b"/><circle cx="320" cy="180" r="85" fill="#a3a3ab"/><text x="30" y="330" fill="white" font-size="20">Synthetic preview · UI fixture</text></svg>',
    );
  const chats = Array.from({ length: stress ? 5000 : 48 }, (_, i) => ({
    id: "fixture-" + i,
    title: i % 7 ? "Local research " + i : "New chat",
    updated: Date.now() / 1000 - i * 18000,
    pinned: i === 2,
  }));
  const images = Array.from({ length: stress ? 5000 : 103 }, (_, i) => ({
    id: "image-" + i,
    path: illustration + "#" + i,
    thumbnail: illustration,
    displayName: "Synthetic landscape " + i,
    model: "UI fixture",
    finalDimensions: "640 × 360",
    created: Date.now() / 1000 - i,
    fileSize: 2048,
    fileExists: true,
  }));
  const status = {
    modelName: "Qwen3-4B-Q4_K_M",
    modelPath: "fixture://model.gguf",
    modelExists: true,
    runtimePresent: true,
    freeRamBytes: 6 * 1024 ** 3,
    freeGpuBytes: 5 * 1024 ** 3,
    totalRamBytes: 16 * 1024 ** 3,
    loaded: false,
    backend: "UI fixture — no inference",
  };
  let voice = { active: false, state: "idle" };
  let current = chats[0].id,
    sequence = 0,
    timer;
  const drafts = new Map(),
    messages = new Map(),
    settings = { theme: "dark", chat_backend: "bundled" };
  const prefs = {
    theme: "dark",
    ui_density: "comfortable",
    ui_chat_font_size: 15,
    ui_content_width: 860,
    ui_sidebar: "expanded",
    ui_motion: "system",
    ui_message_details: "minimal",
    ui_code_wrap: false,
  };
  messages.set(current, [
    {
      id: 1,
      role: "user",
      content: "Please interact with these documents a little.",
    },
    {
      id: 2,
      role: "assistant",
      content:
        "This is a **synthetic UI fixture**, not an inference result.\n\n| Check | State |\n|---|---|\n| Offline | Fixture only |\n\n```python\nprint(19 * 23)\n```",
      metrics: {
        model_identity: {
          outputSource: "ui_fixture",
          modelName: "Fixture model",
          headerMetadataSha256: "abcdef0123456789".repeat(4),
        },
        tokens_per_second: 23,
      },
      duration: 1.2,
    },
    { id: 3, role: "user", content: "gather all info about llm models" },
    {
      id: 4,
      role: "assistant",
      content:
        "**General Overview** Large language models have evolved into general-purpose foundation models K5379ff5a635b7b44.\n\n- **Grok:** a chatbot with a \"Think\" mode [K4760e53a0e72714d](https://en.wikipedia.org/wiki/Grok_(chatbot%29).\n- Unresolved id Kffffffffffffffff is dropped.",
      metrics: {
        intelligence: {
          id: "run-ok", state: "COMPLETED", mode: "hybrid",
          counts: { queries: 2, discovered: 8, fetched: 4, analyzed: 4, cited: 2 },
          sources: [
            { id: "K5379ff5a635b7b44", title: "Survey of LLMs (fixture)", url: "https://example.org/survey", domain: "example.org", fetchStatus: "FETCHED", excerpt: "Synthetic excerpt." },
            { id: "K4760e53a0e72714d", title: "Grok (chatbot) — fixture", url: "https://en.wikipedia.org/wiki/Grok_(chatbot%29", domain: "en.wikipedia.org", fetchStatus: "FETCHED", excerpt: "Synthetic excerpt." },
          ],
        },
        validation_status: "passed",
      },
      duration: 12,
    },
  ]);
  const intelligence = {
    settings: {
      intelligence_mode: "offline",
      research_provider: "public",
      research_permission: "ask",
      research_max_pages: 4,
      research_max_queries: 2,
      research_timeout: 75,
      embedding_model_path: "fixture://minilm.onnx",
      embedding_vocab_path: "fixture://vocab.txt",
    },
    providerConfigured: true,
    providerHealth: "CONFIGURED_NOT_PROBED",
    semantic: "LOCAL_ONNX_CONFIGURED",
    embeddingAvailable: true,
    embeddingModel: { modelExists: true, vocabExists: true, path: "fixture://minilm.onnx" },
    referenceConditioning: { referenceEditing: "AVAILABLE_REQUIRES_NATIVE_ACCEPTANCE" },
  };
  const researchRuns = [
    {
      id: "run-ok",
      query: "Compare Royal Enfield Hunter 350 variants (synthetic fixture)",
      state: "COMPLETED",
      packet: {
        state: "COMPLETED",
        mode: "web",
        counts: { queries: 2, discovered: 8, fetched: 3, analyzed: 3, cited: 2 },
        sources: [
          { id: "S1", title: "Fixture source one", domain: "example.org", fetchStatus: "FETCHED", excerpt: "Synthetic excerpt for UI verification only." },
        ],
      },
    },
    ...[1, 2, 3].map((i) => ({
      id: "run-failed-" + i,
      query: "gather every information from internet and explain what are llm models",
      state: "FAILED",
      packet: { state: "FAILED", counts: {}, sources: [], errors: ["Synthetic failure fixture " + i] },
    })),
  ];
  const reply = (callback, value) =>
    queueMicrotask(() =>
      callback?.(typeof value === "string" ? value : encode(value)),
    );
  const bridge = {
    event,
    historyChanged,
    statusChanged,
    filesDropped: signal(),
    fileDragState: signal(),
    getSettings: (cb) => reply(cb, settings),
    getChats: (cb) => reply(cb, chats),
    currentChat: (cb) => reply(cb, current),
    getModelStatus: (cb) => reply(cb, status),
    getModelLibraryVersion: (cb) => reply(cb, "1"),
    getModels: (cb) => reply(cb, []),
    getChatModel: (id, cb) =>
      reply(cb, { model: "", effectiveModel: "fixture", source: "default" }),
    getAppearancePreferences: (cb) =>
      reply(cb, { ok: true, preferences: prefs }),
    saveAppearancePreferences: (raw, cb) => {
      Object.assign(prefs, JSON.parse(raw));
      reply(cb, { ok: true, preferences: prefs });
      event.emit(encode({ type: "appearancePreferences", preferences: prefs }));
    },
    getLibraryImages: (cb) => reply(cb, images),
    getLibraryView: (view, cb) =>
      reply(cb, {
        ok: true,
        images: view === "hidden" ? [] : images,
        recovery: { operations: [], pendingCount: 0 },
      }),
    refreshLibrary: () => {},
    getPromptDraft: (id, cb) =>
      reply(cb, drafts.get(id) || { text: "", attachments: [] }),
    savePromptDraft: (id, raw, cb) => {
      drafts.set(id, JSON.parse(raw));
      reply(cb, { ok: true });
    },
    loadChat: (id, cb) => {
      current = id;
      reply(cb, messages.get(id) || []);
    },
    newChat: (cb) => {
      current = "draft-" + ++sequence;
      chats.unshift({
        id: current,
        title: "New chat",
        updated: Date.now() / 1000,
      });
      reply(cb, current);
      historyChanged.emit();
    },
    sendMessage: (text) => {
      clearInterval(timer);
      const words = (
        "This response is streamed by the development mock adapter. No model or tool is running. " +
        text +
        " "
      )
        .repeat(50)
        .split(" ");
      let i = 0;
      event.emit(
        encode({
          type: "chat",
          chatId: current,
          message: { id: 100, role: "assistant", content: "", streaming: true },
        }),
      );
      timer = setInterval(() => {
        event.emit(
          encode({
            type: "append",
            chatId: current,
            id: 100,
            text: words.slice(i, i + 5).join(" ") + " ",
          }),
        );
        i += 5;
        if (i >= words.length) {
          clearInterval(timer);
          event.emit(encode({ type: "busy", value: false }));
        }
      }, 30);
    },
    stop: () => {
      clearInterval(timer);
      event.emit(encode({ type: "busy", value: false }));
    },
    getIntelligenceState: (cb) => reply(cb, { ok: true, value: intelligence }),
    setIntelligenceSettings: (raw, cb) => {
      Object.assign(intelligence.settings, JSON.parse(raw));
      reply(cb, { ok: true, value: intelligence });
    },
    // Live Voice fixture: drive the composer voice bar through its states.
    // ?voice=thinking|speaking|transcribing|error picks the starting state.
    setLiveVoiceMode: (next, cb) => {
      const state = new URLSearchParams(location.search).get("voice") || "listening";
      voice = next ? { active: true, sessionId: "mock-voice", generation: 1, revision: 1, state, captureReady: true, prepared: true, muted: false } : { active: false, state: "idle", sessionId: "mock-voice", generation: 1, revision: 99 };
      reply(cb, { ok: true, active: next, session: voice });
    },
    liveVoiceControl: (sid, action, cb) => {
      voice = { ...voice, revision: (voice.revision || 1) + 1 };
      if (action === "exit") voice = { ...voice, active: false, state: "idle" };
      else if (action === "mute") voice = { ...voice, muted: true, state: "paused" };
      else if (action === "unmute") voice = { ...voice, muted: false, state: "listening" };
      else if (action === "interrupt") voice = { ...voice, state: "listening" };
      reply(cb, { ok: true, session: voice });
    },
    cancelVoiceInput: () => {},
    getAgentStatus: (cb) =>
      reply(cb, {
        ok: true,
        available: false,
        reason:
          "Mock preview never invokes tools. Use isolated native Qt checks for bridge verification.",
      }),
    workspaceRequest: (action, raw, cb) => {
      const id = "job-" + ++sequence;
      reply(cb, { ok: true, requestId: id });
      setTimeout(() => {
        let value;
        if (action === "modelLibrary")
          value = {
            models: Array.from({ length: stress ? 80 : 4 }, (_, i) => ({
              id: "model-" + i,
              name: i ? "Qwen3-4B-Q4_K_M" : "Openai_Gpt Oss 20b",
              path: "fixture://" + i,
              architecture: "qwen3",
              quantizationLabel: "Q4_K_M",
              fileBytes: 2500000000,
              contextMetadata: 4096,
              fileState: "present",
              selectable: false,
              selectionWarning: "UI fixture only",
            })),
            status,
          };
        else if (action === "projectsList")
          value = {
            projects: [
              {
                id: "project-1",
                name: "Synthetic research",
                updated: Date.now() / 1000,
                chatCount: 3,
              },
            ],
          };
        else if (action === "intelligence") {
          const op = JSON.parse(raw || "{}").operation;
          value =
            op === "list"
              ? { documents: [], chunks: 0, embeddedChunks: 0, databaseBytes: 0 }
              : op === "runs"
                ? { runs: researchRuns }
                : op === "memories"
                  ? { memories: [] }
                  : op === "savedReferences"
                    ? { references: [] }
                    : op === "references"
                      ? { references: [] }
                      : {};
        } else if (action === "remindersList") value = { reminders: [] };
        else if (action === "documentLibrary")
          value = { documents: [], collections: [] };
        else {
          event.emit(
            encode({
              type: "workspaceResult",
              requestId: id,
              ok: false,
              error: "Unavailable in the read-only UI fixture: " + action,
            }),
          );
          return;
        }
        event.emit(
          encode({ type: "workspaceResult", requestId: id, ok: true, value }),
        );
      }, 20);
    },
    cancelWorkspace: () => {},
  };
  return bridge;
}
