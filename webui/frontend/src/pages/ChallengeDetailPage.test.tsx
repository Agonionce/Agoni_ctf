import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import * as api from "../api";
import type {
  ChallengeDetail,
  ChallengeDocuments,
  ChallengeOutcomes,
  ExperienceCandidate,
  RunView,
} from "../types";
import { ChallengeDetailPage } from "./ChallengeDetailPage";


vi.mock("../api", () => ({
  ApiError: class ApiError extends Error {
    readonly status: number;
    readonly payload: { code: string; message: string };

    constructor(status: number, payload: { code: string; message: string }) {
      super(payload.message);
      this.status = status;
      this.payload = payload;
    }
  },
  abortRun: vi.fn(),
  decideRun: vi.fn(),
  getChallenge: vi.fn(),
  getDocuments: vi.fn(),
  getExperienceCandidates: vi.fn(),
  getOutcomes: vi.fn(),
  getRun: vi.fn(),
  resumeRun: vi.fn(),
  reviewExperienceCandidate: vi.fn(),
  startRun: vi.fn(),
}));

const challenge: ChallengeDetail = {
  challenge_id: "challenge-test",
  name: "本地交互测试",
  domain: "web",
  status: "not_started",
  status_label: "未开始",
  created_at: "2026-08-25T10:00:00Z",
  description: "# 已授权题目",
  target_url: "http://127.0.0.1:5000",
  materials: [],
};

const idleRun: RunView = {
  status: "CREATED",
  status_label: "未开始",
  active: false,
  milestones: [],
  pending_decision: null,
  can_start: true,
  can_abort: false,
  can_resume: false,
  completion_available: false,
};

const emptyOutcomes: ChallengeOutcomes = {
  flag: {
    status: "not_found",
    status_label: "尚未找到 Flag",
    value: null,
    source: null,
    evidence: null,
    evidence_paths: [],
    reason: "题目尚未开始分析。",
  },
  facts: [],
  findings: [],
  hypotheses: [],
  experiments: [],
  evidence: [],
  artifacts: [],
  web: {
    available: false,
    phase_label: "尚未形成 Web 观察",
    authentication_label: "认证状态未知",
    technologies: [],
    endpoints: [],
  },
};

const emptyDocuments: ChallengeDocuments = {
  available: false,
  report: "",
  writeup: "",
  lessons: "",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/challenges/challenge-test"]}>
      <Routes>
        <Route path="/challenges/:challengeId" element={<ChallengeDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(api.getChallenge).mockResolvedValue(challenge);
  vi.mocked(api.getRun).mockResolvedValue(idleRun);
  vi.mocked(api.getOutcomes).mockResolvedValue(emptyOutcomes);
  vi.mocked(api.getDocuments).mockResolvedValue(emptyDocuments);
  vi.mocked(api.getExperienceCandidates).mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ChallengeDetailPage", () => {
  it("keeps every ARIA tab target mounted and switches the visible panel", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByRole("heading", { name: "本地交互测试" });
    const panels = screen.getAllByRole("tabpanel", { hidden: true });
    expect(panels).toHaveLength(4);
    for (const tab of screen.getAllByRole("tab")) {
      expect(document.getElementById(tab.getAttribute("aria-controls")!)).not.toBeNull();
    }

    const overviewTab = screen.getByRole("tab", { name: "概览" });
    const outcomesTab = screen.getByRole("tab", { name: "成果" });
    overviewTab.focus();
    await user.keyboard("{ArrowRight}");
    expect(outcomesTab).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "经验" })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(overviewTab).toHaveFocus();
    await user.click(outcomesTab);
    expect(document.getElementById("workspace-panel-outcomes")).not.toHaveAttribute("hidden");
    expect(document.getElementById("workspace-panel-overview")).toHaveAttribute("hidden");
  });

  it("shows an honest per-section failure without hiding successful sections", async () => {
    const user = userEvent.setup();
    vi.mocked(api.getOutcomes).mockRejectedValue(new Error("fixture failure"));
    renderPage();

    await screen.findByRole("alert");
    await user.click(screen.getByRole("tab", { name: "成果" }));
    expect(screen.getByText("成果暂时无法读取")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "报告" }));
    expect(screen.getByText("报告尚未形成")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "经验" }));
    expect(screen.getByText("暂无候选经验")).toBeInTheDocument();
  });

  it("distinguishes a missing challenge from a temporary first-load failure", async () => {
    const user = userEvent.setup();
    vi.mocked(api.getChallenge).mockRejectedValueOnce(
      new api.ApiError(503, { code: "unavailable", message: "temporary" }),
    );
    const first = renderPage();
    expect(
      await screen.findByRole("heading", { name: "题目暂时无法读取" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重新读取" }));
    expect(
      await screen.findByRole("heading", { name: "本地交互测试" }),
    ).toBeInTheDocument();
    first.unmount();

    vi.mocked(api.getChallenge).mockRejectedValueOnce(
      new api.ApiError(404, { code: "missing", message: "missing" }),
    );
    renderPage();
    expect(
      await screen.findByRole("heading", { name: "未找到该题目" }),
    ).toBeInTheDocument();
  });

  it("announces automatic authorization and Experience decisions", async () => {
    const user = userEvent.setup();
    const completedRun: RunView = {
      ...idleRun,
      status: "SOLVED",
      status_label: "已完成",
      completion_available: true,
      can_start: false,
      can_abort: false,
    };
    const candidate: ExperienceCandidate = {
      candidate_id: "opaque-candidate",
      category_label: "参数行为",
      kind_label: "通用认识",
      pattern: "稳定基线有助于比较结果。",
      strategy: "一次只比较一个受控变量。",
      lesson: "证据与解释保持分离。",
      confidence_label: "高置信度",
      status: "PENDING",
      status_label: "待审核",
    };
    vi.mocked(api.getRun).mockResolvedValue(completedRun);
    vi.mocked(api.getExperienceCandidates).mockResolvedValue([candidate]);
    vi.mocked(api.reviewExperienceCandidate).mockResolvedValue({
      ...candidate,
      status: "APPROVED",
      status_label: "已纳入经验",
    });
    renderPage();

    expect(await screen.findByText("已授权自动分析")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "允许并继续" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "经验" }));
    await user.click(screen.getByRole("button", { name: "纳入经验" }));
    const reviewed = screen.getByText("稳定基线有助于比较结果。").closest("li");
    await waitFor(() => expect(reviewed).toHaveFocus());
    expect(screen.getByText("该条经验已纳入通用参考。")).toBeInTheDocument();
  });
});
