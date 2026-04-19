"use client";

import {
  startTransition,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { AnswerView } from "@/components/answer-view";
import { HeroPoster } from "@/components/hero-poster";
import { TraceTimeline } from "@/components/trace-timeline";
import {
  ArchitecturePanel,
  QueryConsole,
  RuntimePanel,
  UploadPanel,
} from "@/components/workspace-panels";
import { API_BASE } from "@/lib/content";
import { fetchServiceCatalog, streamQuery, uploadMatterDocument } from "@/lib/api";
import { deriveQuerySignals, serviceSearchText } from "@/lib/format";
import type { Answer, QueryMode, ServiceInfo, TraceEvent, UploadResponse } from "@/lib/types";

export function WorkspaceShell() {
  const [question, setQuestion] = useState(
    "What are the ingredients of theft under Section 378 IPC?",
  );
  const [matterScope, setMatterScope] = useState("");
  const [mode, setMode] = useState<QueryMode>("graph_plus_semantic");
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceEvent[]>([]);
  const [streamStart, setStreamStart] = useState<number | null>(null);

  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [runtimeLoading, setRuntimeLoading] = useState(false);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);
  const [serviceFilter, setServiceFilter] = useState("");

  const [uploadMatterId, setUploadMatterId] = useState("matter-001");
  const [uploadKind, setUploadKind] = useState("generic");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const deferredQuestion = useDeferredValue(question);
  const deferredServiceFilter = useDeferredValue(serviceFilter);

  const signals = useMemo(
    () => deriveQuerySignals(deferredQuestion, matterScope),
    [deferredQuestion, matterScope],
  );

  const visibleServices = useMemo(() => {
    const filter = deferredServiceFilter.trim().toLowerCase();
    if (!filter) {
      return services;
    }
    return services.filter((service) => serviceSearchText(service).includes(filter));
  }, [deferredServiceFilter, services]);

  const refreshRuntime = useCallback(async () => {
    setRuntimeLoading(true);
    setRuntimeError(null);

    try {
      const catalog = await fetchServiceCatalog();
      startTransition(() => {
        setServices(catalog.services);
      });
    } catch (caughtError) {
      setRuntimeError(
        caughtError instanceof Error ? caughtError.message : String(caughtError),
      );
    } finally {
      setRuntimeLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshRuntime();
  }, [refreshRuntime]);

  async function handleAsk() {
    setLoading(true);
    setError(null);
    setAnswer(null);
    setTrace([]);
    setStreamStart(Date.now());

    const controller = new AbortController();
    abortRef.current?.abort();
    abortRef.current = controller;

    try {
      const result = await streamQuery({
        question,
        matterScope: matterScope.trim() || null,
        mode,
        signal: controller.signal,
        onEvent: (event) => {
          startTransition(() => {
            setTrace((current) => [...current, event]);
          });
        },
      });

      startTransition(() => {
        setAnswer(result);
      });
    } catch (caughtError) {
      if ((caughtError as { name?: string }).name !== "AbortError") {
        setError(caughtError instanceof Error ? caughtError.message : String(caughtError));
      }
    } finally {
      setLoading(false);
    }
  }

  function handleCancel() {
    abortRef.current?.abort();
    setLoading(false);
  }

  async function handleUpload() {
    if (!uploadFile || !uploadMatterId.trim()) {
      return;
    }

    setUploadLoading(true);
    setUploadError(null);

    try {
      const result = await uploadMatterDocument({
        file: uploadFile,
        matterId: uploadMatterId.trim(),
        kind: uploadKind,
      });
      setUploadResult(result);
      setUploadFile(null);
    } catch (caughtError) {
      setUploadError(
        caughtError instanceof Error ? caughtError.message : String(caughtError),
      );
    } finally {
      setUploadLoading(false);
    }
  }

  return (
    <div className="page-shell">
      <HeroPoster />

      <main className="workspace">
        <section className="workspace-grid">
          <div className="workspace-primary">
            <QueryConsole
              question={question}
              matterScope={matterScope}
              mode={mode}
              loading={loading}
              signals={signals}
              onQuestionChange={setQuestion}
              onMatterScopeChange={setMatterScope}
              onModeChange={setMode}
              onAsk={handleAsk}
              onCancel={handleCancel}
            />

            <TraceTimeline events={trace} streaming={loading} startedAt={streamStart} />
            <AnswerView answer={answer} error={error} />
          </div>

          <aside className="workspace-sidebar">
            <ArchitecturePanel />
            <UploadPanel
              matterId={uploadMatterId}
              kind={uploadKind}
              fileName={uploadFile?.name ?? ""}
              uploadResult={uploadResult}
              loading={uploadLoading}
              error={uploadError}
              onMatterIdChange={setUploadMatterId}
              onKindChange={setUploadKind}
              onFileChange={setUploadFile}
              onSubmit={handleUpload}
            />
            <RuntimePanel
              services={visibleServices}
              loading={runtimeLoading}
              error={runtimeError}
              filter={serviceFilter}
              apiBase={API_BASE}
              onFilterChange={setServiceFilter}
              onRefresh={refreshRuntime}
            />
          </aside>
        </section>
      </main>
    </div>
  );
}
