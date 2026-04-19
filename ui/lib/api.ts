import { API_BASE } from "@/lib/content";
import type {
  Answer,
  QueryMode,
  ServiceCatalog,
  TraceEvent,
  UploadResponse,
} from "@/lib/types";

type StreamQueryParams = {
  question: string;
  matterScope: string | null;
  mode: QueryMode;
  signal?: AbortSignal;
  onEvent?: (event: TraceEvent) => void;
};

async function parseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const message = await response.text().catch(() => response.statusText);
    throw new Error(`${response.status}: ${message}`);
  }
  return (await response.json()) as T;
}

export async function fetchServiceCatalog(): Promise<ServiceCatalog> {
  return parseJson<ServiceCatalog>(await fetch(`${API_BASE}/system/services`, { cache: "no-store" }));
}

export async function uploadMatterDocument(params: {
  file: File;
  matterId: string;
  kind: string;
}): Promise<UploadResponse> {
  const formData = new FormData();
  formData.set("file", params.file);
  formData.set("matter_id", params.matterId);
  formData.set("kind", params.kind);

  return parseJson<UploadResponse>(
    await fetch(`${API_BASE}/ingest/private`, {
      method: "POST",
      body: formData,
    }),
  );
}

export async function streamQuery(params: StreamQueryParams): Promise<Answer> {
  const response = await fetch(`${API_BASE}/query/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      question: params.question,
      matter_scope: params.matterScope,
      mode: params.mode,
    }),
    signal: params.signal,
  });

  if (!response.ok || !response.body) {
    const message = await response.text().catch(() => response.statusText);
    throw new Error(`${response.status}: ${message}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  let finalAnswer: Answer | null = null;
  let finalError: string | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    let frameEnd = buffer.indexOf("\n\n");

    while (frameEnd !== -1) {
      const frame = buffer.slice(0, frameEnd);
      buffer = buffer.slice(frameEnd + 2);

      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) {
          continue;
        }

        const payload = line.slice(5).trimStart();
        if (!payload) {
          continue;
        }

        try {
          const event = JSON.parse(payload) as TraceEvent;
          params.onEvent?.(event);
          if (event.status === "end") {
            finalAnswer = event.answer ?? null;
            finalError = event.error ?? null;
          }
        } catch {
          // Ignore malformed SSE frames from intermediaries.
        }
      }

      frameEnd = buffer.indexOf("\n\n");
    }
  }

  if (finalError) {
    throw new Error(finalError);
  }

  if (!finalAnswer) {
    throw new Error("Query completed without a terminal answer payload.");
  }

  return finalAnswer;
}
