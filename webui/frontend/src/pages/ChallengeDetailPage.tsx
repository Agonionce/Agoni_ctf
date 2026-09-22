import {
  ArrowLeft,
  FileCode2,
  FileText,
  Paperclip,
  Play,
  RotateCcw,
  Square,
} from "lucide-react";
import {
  KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  abortRun,
  getChallenge,
  getDocuments,
  getExperienceCandidates,
  getOutcomes,
  getRun,
  resumeRun,
  reviewExperienceCandidate,
  startRun,
} from "../api";
import { MarkdownPreview } from "../components/MarkdownPreview";
import { StatusText } from "../components/StatusText";
import type {
  ChallengeDetail,
  ChallengeDocuments,
  ChallengeOutcomes,
  ChallengeStatus,
  ExperienceCandidate,
  FlagOutcome,
  OutcomeRecord,
  RunView,
} from "../types";

const domainLabels: Record<string, string> = {
  auto: "自动识别",
  web: "Web",
  pwn: "Pwn",
  reverse: "Reverse",
  crypto: "Crypto",
  misc: "Misc",
};

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "long",
  day: "numeric",
});

const tabs = [
  { id: "overview", label: "概览" },
  { id: "outcomes", label: "成果" },
  { id: "documents", label: "报告" },
  { id: "experience", label: "经验" },
] as const;

type WorkspaceTab = (typeof tabs)[number]["id"];
type DocumentTab = "report" | "writeup" | "lessons";
type LoadState = "loading" | "ready" | "error";

export function ChallengeDetailPage() {
  const { challengeId = "" } = useParams();
  const [challenge, setChallenge] = useState<ChallengeDetail | null>(null);
  const [run, setRun] = useState<RunView | null>(null);
  const [outcomes, setOutcomes] = useState<ChallengeOutcomes | null>(null);
  const [documents, setDocuments] = useState<ChallengeDocuments | null>(null);
  const [candidates, setCandidates] = useState<ExperienceCandidate[]>([]);
  const [outcomesState, setOutcomesState] = useState<LoadState>("loading");
  const [documentsState, setDocumentsState] = useState<LoadState>("loading");
  const [candidatesState, setCandidatesState] = useState<LoadState>("loading");
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("overview");
  const [documentTab, setDocumentTab] = useState<DocumentTab>("report");
  const [loadError, setLoadError] = useState<"not_found" | "unavailable" | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [workspaceError, setWorkspaceError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const runCommandRef = useRef<HTMLDivElement>(null);
  const candidateRefs = useRef<Record<string, HTMLLIElement | null>>({});
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const loadSupporting = useCallback(
    async (signal?: AbortSignal) => {
      setOutcomesState("loading");
      setDocumentsState("loading");
      setCandidatesState("loading");
      const [outcomeResult, documentResult, candidateResult] = await Promise.allSettled([
        getOutcomes(challengeId, signal),
        getDocuments(challengeId, signal),
        getExperienceCandidates(challengeId, signal),
      ]);
      if (signal?.aborted) return;

      let partialFailure = false;
      if (outcomeResult.status === "fulfilled") {
        setOutcomes(outcomeResult.value);
        setOutcomesState("ready");
      } else {
        setOutcomesState("error");
        partialFailure = true;
      }
      if (documentResult.status === "fulfilled") {
        setDocuments(documentResult.value);
        setDocumentsState("ready");
      } else {
        setDocumentsState("error");
        partialFailure = true;
      }
      if (candidateResult.status === "fulfilled") {
        setCandidates(candidateResult.value);
        setCandidatesState("ready");
      } else {
        setCandidatesState("error");
        partialFailure = true;
      }
      if (partialFailure) {
        setWorkspaceError("部分阶段成果暂时无法读取，题目与其他可用内容不受影响。");
      } else {
        setWorkspaceError((current) =>
          current === "部分阶段成果暂时无法读取，题目与其他可用内容不受影响。"
            ? ""
            : current,
        );
      }
    },
    [challengeId],
  );

  useEffect(() => {
    const controller = new AbortController();
    setLoadError(null);
    setChallenge(null);
    setRun(null);
    setWorkspaceError("");
    setAnnouncement("");
    Promise.all([
      getChallenge(challengeId, controller.signal),
      getRun(challengeId, controller.signal),
    ])
      .then(([nextChallenge, nextRun]) => {
        setChallenge(nextChallenge);
        setRun(nextRun);
        void loadSupporting(controller.signal);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setLoadError(
          error instanceof ApiError && error.status === 404
            ? "not_found"
            : "unavailable",
        );
      });
    return () => controller.abort();
  }, [challengeId, loadAttempt, loadSupporting]);

  useEffect(() => {
    if (!run?.active) return;
    const interval = window.setInterval(() => {
      getRun(challengeId)
        .then((nextRun) => {
          setRun(nextRun);
          if (!nextRun.active) {
            void loadSupporting();
          }
        })
        .catch(() => setWorkspaceError("进度暂时无法刷新，分析仍会在本地继续。"));
    }, 1500);
    return () => window.clearInterval(interval);
  }, [challengeId, loadSupporting, run?.active]);

  async function performRunAction(
    name: string,
    action: () => Promise<RunView>,
    successMessage: string,
  ) {
    setBusyAction(name);
    setWorkspaceError("");
    setAnnouncement("");
    try {
      setRun(await action());
      setAnnouncement(successMessage);
      requestAnimationFrame(() => runCommandRef.current?.focus());
    } catch (error) {
      setWorkspaceError(
        error instanceof ApiError ? error.message : "操作没有完成，请稍后重试。",
      );
    } finally {
      setBusyAction(null);
    }
  }

  async function reviewCandidate(
    candidate: ExperienceCandidate,
    decision: "approve" | "reject",
  ) {
    setBusyAction(candidate.candidate_id);
    setWorkspaceError("");
    setAnnouncement("");
    try {
      const reviewed = await reviewExperienceCandidate(
        challengeId,
        candidate.candidate_id,
        decision,
      );
      setCandidates((current) =>
        current.map((item) =>
          item.candidate_id === reviewed.candidate_id ? reviewed : item,
        ),
      );
      setAnnouncement(
        decision === "approve" ? "该条经验已纳入通用参考。" : "该条经验已忽略。",
      );
      requestAnimationFrame(() => candidateRefs.current[candidate.candidate_id]?.focus());
    } catch (error) {
      setWorkspaceError(
        error instanceof ApiError ? error.message : "经验审核没有完成，请稍后重试。",
      );
    } finally {
      setBusyAction(null);
    }
  }

  function handleTabKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (!(["ArrowLeft", "ArrowRight", "Home", "End"] as string[]).includes(event.key)) {
      return;
    }
    event.preventDefault();
    let next = index;
    if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    setActiveTab(tabs[next]!.id);
    tabRefs.current[next]?.focus();
  }

  if (loadError) {
    const notFound = loadError === "not_found";
    return (
      <section className="detail-state" role="alert">
        <h1>{notFound ? "未找到该题目" : "题目暂时无法读取"}</h1>
        <p>
          {notFound
            ? "题目可能已经移动，返回题目库重新选择。"
            : "本地服务暂时没有返回题目，请重新读取或稍后再试。"}
        </p>
        {notFound ? (
          <Link className="text-action" to="/">
            返回题目
          </Link>
        ) : (
          <button
            className="text-action"
            onClick={() => setLoadAttempt((current) => current + 1)}
            type="button"
          >
            重新读取
          </button>
        )}
      </section>
    );
  }

  if (!challenge || !run) {
    return (
      <section className="detail-state" role="status">
        <h1>正在读取题目</h1>
        <p>题目与阶段成果准备好后会显示在这里。</p>
      </section>
    );
  }

  const attachments = challenge.materials.filter((item) => item.kind === "attachment");
  const sourceFiles = challenge.materials.filter((item) => item.kind === "source");
  const status = runStatus(run.status, challenge.status);
  const statusLabel = run.status_label || challenge.status_label;

  return (
    <article className="challenge-detail">
      <Link className="back-link" to="/">
        <ArrowLeft aria-hidden="true" size={17} />
        返回题目
      </Link>
      <header className="detail-header">
        <div className="detail-title-block">
          <h1>{challenge.name}</h1>
          <p>只看 Flag、关键证据与阶段成果。</p>
        </div>
        <StatusText status={status} label={statusLabel} />
      </header>

      <nav className="workspace-tabs" aria-label="题目工作台" role="tablist">
        {tabs.map((tab, index) => (
          <button
            aria-controls={`workspace-panel-${tab.id}`}
            aria-selected={activeTab === tab.id}
            className={activeTab === tab.id ? "is-active" : ""}
            id={`workspace-tab-${tab.id}`}
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={(event) => handleTabKey(event, index)}
            ref={(element) => {
              tabRefs.current[index] = element;
            }}
            role="tab"
            tabIndex={activeTab === tab.id ? 0 : -1}
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <p className="visually-hidden" aria-live="polite">
        {announcement || statusLabel}
      </p>
      {workspaceError && <div className="workspace-error" role="alert">{workspaceError}</div>}

      <section
        aria-labelledby="workspace-tab-overview"
        className="workspace-panel"
        hidden={activeTab !== "overview"}
        id="workspace-panel-overview"
        role="tabpanel"
      >
          <div className="run-command-bar" ref={runCommandRef} tabIndex={-1}>
            <div>
              <strong>{run.active ? "正在自动整理阶段成果" : "已授权自动分析"}</strong>
              <p>
                {run.active
                  ? "Agent 会在已授权范围内自动推进，阶段性成果会持续更新。"
                  : "本轮使用已授权自动运行，结果与证据已保留。"}
              </p>
            </div>
            <div className="run-actions">
              {run.can_resume && (
                <button
                  className="secondary-action"
                  disabled={busyAction !== null}
                  onClick={() =>
                    performRunAction(
                      "resume",
                      () => resumeRun(challengeId),
                      "已从安全存档继续分析。",
                    )
                  }
                  type="button"
                >
                  <RotateCcw aria-hidden="true" size={17} />
                  {busyAction === "resume" ? "正在恢复…" : "从存档继续"}
                </button>
              )}
              {run.can_start && !run.can_resume && (
                <button
                  className="primary-action"
                  disabled={busyAction !== null}
                  onClick={() =>
                    performRunAction(
                      "start",
                      () => startRun(challengeId),
                      "分析已开始。",
                    )
                  }
                  type="button"
                >
                  <Play aria-hidden="true" size={17} />
                  {busyAction === "start" ? "正在开始…" : "开始分析"}
                </button>
              )}
              {run.can_abort && (
                <button
                  className="stop-action"
                  disabled={busyAction !== null}
                  onClick={() =>
                    performRunAction(
                      "abort",
                      () => abortRun(challengeId),
                      "正在安全停止并保存当前进度。",
                    )
                  }
                  type="button"
                >
                  <Square aria-hidden="true" size={15} />
                  {busyAction === "abort" ? "正在停止…" : "安全停止"}
                </button>
              )}
            </div>
          </div>

          <section className="milestone-section" aria-labelledby="milestone-title">
            <h2 id="milestone-title">进度</h2>
            {run.milestones.length === 0 ? (
              <p className="empty-copy">开始分析后，关键阶段成果会出现在这里。</p>
            ) : (
              <ol className="milestone-ledger">
                {run.milestones.map((item, index) => (
                  <li className={`milestone-ledger__item milestone-ledger__item--${item.state}`} key={`${item.occurred_at}-${index}`}>
                    <div>
                      <strong>{item.title}</strong>
                      <p>{item.detail}</p>
                    </div>
                    <time dateTime={item.occurred_at}>{shortTime(item.occurred_at)}</time>
                  </li>
                ))}
              </ol>
            )}
          </section>

          <dl className="detail-register">
            <div>
              <dt>领域</dt>
              <dd>{domainLabels[challenge.domain] ?? challenge.domain}</dd>
            </div>
            <div>
              <dt>创建日期</dt>
              <dd>{dateFormatter.format(new Date(challenge.created_at))}</dd>
            </div>
            {challenge.target_url && (
              <div>
                <dt>授权目标</dt>
                <dd className="target-url">{challenge.target_url}</dd>
              </div>
            )}
          </dl>

          <section className="detail-section" aria-labelledby="description-title">
            <h2 id="description-title">题目描述</h2>
            <MarkdownPreview value={challenge.description} />
          </section>

          <section className="detail-section" aria-labelledby="materials-title">
            <h2 id="materials-title">题目材料</h2>
            {challenge.materials.length === 0 ? (
              <p className="empty-copy">这道题没有导入附件或源码文件。</p>
            ) : (
              <div className="material-groups">
                <MaterialGroup icon="attachment" items={attachments.map((item) => item.name)} title="附件" />
                <MaterialGroup icon="source" items={sourceFiles.map((item) => item.name)} title="源码" />
              </div>
            )}
          </section>
      </section>

      <section
        aria-labelledby="workspace-tab-outcomes"
        className="workspace-panel"
        hidden={activeTab !== "outcomes"}
        id="workspace-panel-outcomes"
        role="tabpanel"
      >
          {outcomesState === "loading" ? (
            <PanelEmpty title="正在读取成果" detail="将展示 Flag、证据、路径与阶段结论。" />
          ) : outcomesState === "error" ? (
            <PanelEmpty title="成果暂时无法读取" detail="可继续使用题目，稍后完成分析时会自动重试。" />
          ) : !outcomes ? (
            <PanelEmpty title="暂无阶段成果" detail="开始分析后，Flag、证据与完整路径会出现在这里。" />
          ) : (
            <div className="outcome-register">
              <FlagResult outcome={outcomes.flag} />
              <OutcomeGroup title="已确认事实" items={outcomes.facts} empty="还没有已确认事实。" />
              <OutcomeGroup title="重要发现" items={outcomes.findings} empty="还没有重要发现。" />
              <OutcomeGroup title="待验证假设" items={outcomes.hypotheses} empty="当前没有待验证假设。" />
              <OutcomeGroup title="实验结果" items={outcomes.experiments} empty="还没有实验结果。" />
              <OutcomeGroup title="证据记录" items={outcomes.evidence} empty="还没有可展示的证据记录。" />

              <section className="outcome-section" aria-labelledby="artifacts-heading">
                <div className="outcome-section__heading">
                  <h2 id="artifacts-heading">分析材料</h2>
                  <p>显示分析材料路径，便于你人工核对本地证据。</p>
                </div>
                {outcomes.artifacts.length === 0 ? (
                  <p className="empty-copy">还没有生成分析材料。</p>
                ) : (
                  <ul className="artifact-ledger">
                    {outcomes.artifacts.map((item) => (
                      <li key={`${item.kind_label}-${item.name}`}>
                        <FileText aria-hidden="true" size={18} />
                        <strong>{item.name}</strong>
                        <span>{item.kind_label}</span>
                        {item.path && <code>{item.path}</code>}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <WebOutcomeSection outcomes={outcomes} />
            </div>
          )}
      </section>

      <section
        aria-labelledby="workspace-tab-documents"
        className="workspace-panel"
        hidden={activeTab !== "documents"}
        id="workspace-panel-documents"
        role="tabpanel"
      >
          {documentsState === "loading" ? (
            <PanelEmpty title="正在读取报告" detail="将展示本轮最终答案、证据与相关文件路径。" />
          ) : documentsState === "error" ? (
            <PanelEmpty title="报告暂时无法读取" detail="题目仍可继续使用，稍后完成分析时会自动重试。" />
          ) : !documents?.available ? (
            <PanelEmpty title="报告尚未形成" detail="本轮分析结束后，报告、解题记录与经验总结会出现在这里。" />
          ) : (
            <div className="document-reader">
              <div className="document-switch" aria-label="报告类型">
                {([
                  ["report", "分析报告"],
                  ["writeup", "解题记录"],
                  ["lessons", "经验总结"],
                ] as const).map(([id, label]) => (
                  <button
                    aria-pressed={documentTab === id}
                    className={documentTab === id ? "is-active" : ""}
                    key={id}
                    onClick={() => setDocumentTab(id)}
                    type="button"
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="document-sheet">
                <MarkdownPreview
                  emptyText="这份文档还没有内容。"
                  value={documents[documentTab]}
                />
              </div>
            </div>
          )}
      </section>

      <section
        aria-labelledby="workspace-tab-experience"
        className="workspace-panel"
        hidden={activeTab !== "experience"}
        id="workspace-panel-experience"
        role="tabpanel"
      >
          <header className="experience-intro">
            <h2>可复用经验审核</h2>
            <p>只有你明确纳入的通用认识，才会进入后续题目的参考。</p>
          </header>
          {candidatesState === "loading" ? (
            <PanelEmpty title="正在读取候选经验" detail="这里展示可跨题复用的通用认识。" />
          ) : candidatesState === "error" ? (
            <PanelEmpty title="候选经验暂时无法读取" detail="其他题目内容不受影响，稍后会自动重试。" />
          ) : candidates.length === 0 ? (
            <PanelEmpty title="暂无候选经验" detail="完成分析并形成足够证据后，候选经验会出现在这里。" />
          ) : (
            <ol className="candidate-ledger">
              {candidates.map((candidate) => (
                <li
                  key={candidate.candidate_id}
                  ref={(element) => {
                    candidateRefs.current[candidate.candidate_id] = element;
                  }}
                  tabIndex={-1}
                >
                  <div className="candidate-ledger__meta">
                    <span>{candidate.category_label}</span>
                    <span>{candidate.kind_label}</span>
                    <strong className={`candidate-status candidate-status--${candidate.status.toLowerCase()}`}>
                      {candidate.status_label}
                    </strong>
                  </div>
                  <h3>{candidate.pattern}</h3>
                  <dl>
                    <div>
                      <dt>建议策略</dt>
                      <dd>{candidate.strategy}</dd>
                    </div>
                    <div>
                      <dt>可复用认识</dt>
                      <dd>{candidate.lesson}</dd>
                    </div>
                  </dl>
                  {candidate.status === "PENDING" && (
                    <div className="candidate-actions">
                      <button
                        className="secondary-action"
                        disabled={busyAction !== null}
                        onClick={() => reviewCandidate(candidate, "reject")}
                        type="button"
                      >
                        忽略
                      </button>
                      <button
                        className="primary-action"
                        disabled={busyAction !== null}
                        onClick={() => reviewCandidate(candidate, "approve")}
                        type="button"
                      >
                        纳入经验
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
      </section>
    </article>
  );
}

function FlagResult({ outcome }: { outcome: FlagOutcome }) {
  const found = outcome.status === "found";
  return (
    <section className={`flag-result flag-result--${outcome.status}`} aria-labelledby="flag-result-heading">
      <div className="flag-result__heading">
        <div>
          <span className="flag-result__eyebrow">本题唯一目标</span>
          <h2 id="flag-result-heading">Flag 结果</h2>
        </div>
        <strong>{outcome.status_label}</strong>
      </div>
      {found ? (
        <>
          <code className="flag-result__value">{outcome.value}</code>
          <dl className="flag-result__details">
            <div>
              <dt>支持证据</dt>
              <dd>{outcome.evidence}</dd>
            </div>
            <div>
              <dt>证据来源</dt>
              <dd>{outcome.source}</dd>
            </div>
          </dl>
          {outcome.evidence_paths.length > 0 && (
            <ul className="outcome-paths" aria-label="Flag 证据文件路径">
              {outcome.evidence_paths.map((path) => <li key={path}><code>{path}</code></li>)}
            </ul>
          )}
        </>
      ) : (
        <p className="flag-result__reason">{outcome.reason ?? "本轮未形成最终 Flag。"}</p>
      )}
    </section>
  );
}

function OutcomeGroup({ title, items, empty }: { title: string; items: OutcomeRecord[]; empty: string }) {
  const headingId = `outcome-${title}`;
  return (
    <section className="outcome-section" aria-labelledby={headingId}>
      <div className="outcome-section__heading">
        <h2 id={headingId}>{title}</h2>
        <p>{items.length > 0 ? `${items.length} 条阶段成果` : empty}</p>
      </div>
      {items.length > 0 && (
        <ol className="outcome-list">
          {items.map((item, index) => (
            <li key={`${item.occurred_at ?? "record"}-${index}`}>
              <div className="outcome-list__meta">
                <span>{item.status_label}</span>
                <span>{item.certainty_label}</span>
              </div>
              <h3>{item.title}</h3>
              <p>{item.detail}</p>
              {item.artifact_paths.length > 0 && (
                <ul className="outcome-paths" aria-label="相关证据文件路径">
                  {item.artifact_paths.map((path) => <li key={path}><code>{path}</code></li>)}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function WebOutcomeSection({ outcomes }: { outcomes: ChallengeOutcomes }) {
  const web = outcomes.web;
  return (
    <section className="outcome-section" aria-labelledby="web-observation-heading">
      <div className="outcome-section__heading">
        <h2 id="web-observation-heading">Web 观察</h2>
        <p>{web.available ? `${web.phase_label} · ${web.authentication_label}` : "尚未形成可展示的 Web 观察。"}</p>
      </div>
      {web.available && (
        <>
          {web.technologies.length > 0 && (
            <p className="technology-line">
              <strong>技术迹象</strong>
              {web.technologies.join(" · ")}
            </p>
          )}
          <div className="endpoint-ledger">
            {web.endpoints.map((endpoint) => (
              <div key={endpoint.path}>
                <strong>{endpoint.path}</strong>
                <span>{endpoint.methods.join(" / ") || "方法待确认"}</span>
                <span>{endpoint.parameters.length > 0 ? `参数：${endpoint.parameters.join("、")}` : "未记录参数"}</span>
                <span>{endpoint.access_label}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function PanelEmpty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="panel-empty">
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

interface MaterialGroupProps {
  title: string;
  items: string[];
  icon: "attachment" | "source";
}

function MaterialGroup({ title, items, icon }: MaterialGroupProps) {
  if (items.length === 0) return null;
  const Icon = icon === "attachment" ? Paperclip : FileCode2;
  return (
    <div className="material-group">
      <h3>
        <Icon aria-hidden="true" size={19} strokeWidth={1.7} />
        {title}
      </h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function runStatus(status: string, fallback: ChallengeStatus): ChallengeStatus {
  const mapping: Record<string, ChallengeStatus> = {
    CREATED: "not_started",
    RUNNING: "analyzing",
    WAITING: "waiting",
    SOLVED: "completed",
    BLOCKED: "needs_help",
    FAILED: "not_solved",
    BUDGET_EXHAUSTED: "not_solved",
    ABORTED: "paused",
    PAUSED: "paused",
  };
  return mapping[status] ?? fallback;
}

function shortTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
