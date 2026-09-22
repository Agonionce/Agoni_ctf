import { ArrowUpRight, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listChallenges } from "../api";
import { StatusText } from "../components/StatusText";
import type { ChallengeSummary } from "../types";

const domainLabels: Record<string, string> = {
  auto: "自动",
  web: "Web",
  pwn: "Pwn",
  reverse: "Reverse",
  crypto: "Crypto",
  misc: "Misc",
};

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

export function ChallengeListPage() {
  const [items, setItems] = useState<ChallengeSummary[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    const controller = new AbortController();
    listChallenges(controller.signal)
      .then((result) => {
        setItems(result);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState("error");
      });
    return () => controller.abort();
  }, []);

  return (
    <section className="catalog" aria-labelledby="catalog-title">
      <header className="page-heading">
        <div>
          <h1 id="catalog-title">题目</h1>
          <p>管理本地 CTF 题目，选择一项继续。</p>
        </div>
      </header>

      <div className="catalog-register">
        <div className="catalog-head" aria-hidden="true">
          <span>登记</span>
          <span>题目名称</span>
          <span>领域</span>
          <span>状态</span>
          <span>创建日期</span>
        </div>

        {state === "loading" && <CatalogLoading />}
        {state === "error" && <CatalogError />}
        {state === "ready" && items.length === 0 && <CatalogEmpty />}
        {state === "ready" && items.length > 0 && (
          <ol className="catalog-list">
            {items.map((item, index) => (
              <li key={item.challenge_id}>
                <Link
                  className="catalog-row"
                  to={`/challenges/${encodeURIComponent(item.challenge_id)}`}
                >
                  <span className="catalog-index">{String(index + 1).padStart(2, "0")}</span>
                  <span className="catalog-title">
                    {item.name}
                    <ArrowUpRight aria-hidden="true" size={17} strokeWidth={1.8} />
                  </span>
                  <span className="catalog-domain">
                    {domainLabels[item.domain] ?? item.domain}
                  </span>
                  <StatusText status={item.status} label={item.status_label} />
                  <time dateTime={item.created_at}>
                    {dateFormatter.format(new Date(item.created_at))}
                  </time>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function CatalogLoading() {
  return (
    <div className="catalog-message" role="status">
      <span className="registration-marker registration-marker--loading" />
      <div>
        <strong>正在读取题目</strong>
        <p>本地题目准备好后会显示在这里。</p>
      </div>
    </div>
  );
}

function CatalogError() {
  return (
    <div className="catalog-message" role="alert">
      <span className="registration-marker registration-marker--error" />
      <div>
        <strong>暂时无法读取题目</strong>
        <p>请确认本地服务仍在运行，然后刷新页面。</p>
      </div>
    </div>
  );
}

function CatalogEmpty() {
  return (
    <div className="catalog-message catalog-message--empty">
      <span className="registration-marker">
        <Plus aria-hidden="true" size={20} strokeWidth={1.7} />
      </span>
      <div>
        <strong>还没有题目</strong>
        <p>添加题目描述和附件，开始建立你的本地题目库。</p>
        <Link className="text-action" to="/new">
          新建第一道题
        </Link>
      </div>
    </div>
  );
}
