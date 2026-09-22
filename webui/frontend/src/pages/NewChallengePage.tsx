import { ArrowLeft, FileCode2, FileText, Paperclip, X } from "lucide-react";
import { FormEvent, useId, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, createChallenge } from "../api";
import { MarkdownPreview } from "../components/MarkdownPreview";
import type { ChallengeDraft } from "../types";

const initialDraft: ChallengeDraft = {
  name: "",
  description: "",
  domain: "auto",
  targetUrl: "",
  authorizationConfirmed: false,
  attachments: [],
  sourceFiles: [],
};

interface FormErrors {
  name?: string;
  description?: string;
  authorization?: string;
}

export function NewChallengePage() {
  const navigate = useNavigate();
  const [draft, setDraft] = useState<ChallengeDraft>(initialDraft);
  const [descriptionMode, setDescriptionMode] = useState<"edit" | "preview">("edit");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [formErrors, setFormErrors] = useState<FormErrors>({});
  const formId = useId();
  const nameRef = useRef<HTMLInputElement>(null);
  const descriptionRef = useRef<HTMLTextAreaElement>(null);
  const authorizationRef = useRef<HTMLInputElement>(null);
  const serverErrorRef = useRef<HTMLDivElement>(null);

  function clearFormError(field: keyof FormErrors) {
    setFormErrors((current) => ({ ...current, [field]: undefined }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors: FormErrors = {};
    if (!draft.name.trim()) nextErrors.name = "请填写题目名称";
    if (!draft.description.trim()) nextErrors.description = "请填写题目描述";
    if (!draft.authorizationConfirmed) {
      nextErrors.authorization = "请确认题目属于已授权范围";
    }
    if (Object.keys(nextErrors).length > 0) {
      setFormErrors(nextErrors);
      if (nextErrors.description) setDescriptionMode("edit");
      requestAnimationFrame(() => {
        if (nextErrors.name) nameRef.current?.focus();
        else if (nextErrors.description) descriptionRef.current?.focus();
        else authorizationRef.current?.focus();
      });
      return;
    }
    setFormErrors({});
    setSubmitting(true);
    setError(null);
    try {
      const result = await createChallenge(draft);
      navigate(`/challenges/${encodeURIComponent(result.challenge_id)}`);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught
          : new ApiError(0, {
              code: "request_failed",
              message: "题目没有创建成功，请稍后重试",
          }),
      );
      requestAnimationFrame(() => serverErrorRef.current?.focus());
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="form-page" aria-labelledby={`${formId}-title`}>
      <Link className="back-link" to="/">
        <ArrowLeft aria-hidden="true" size={17} />
        返回题目
      </Link>
      <header className="page-heading page-heading--form">
        <div>
          <h1 id={`${formId}-title`}>新建题目</h1>
          <p>填写题目内容，材料只会被安全复制，不会自动执行。</p>
        </div>
      </header>

      <form className="challenge-form" onSubmit={handleSubmit} noValidate>
        {error && (
          <div className="form-error" ref={serverErrorRef} role="alert" tabIndex={-1}>
            <strong>{error.message}</strong>
            {error.payload.existing_challenge_id && (
              <Link
                to={`/challenges/${encodeURIComponent(error.payload.existing_challenge_id)}`}
              >
                进入已有题目
              </Link>
            )}
          </div>
        )}

        <div className="field-row field-row--split">
          <label className="field" htmlFor={`${formId}-name`}>
            <span>
              题目名称 <span className="required-mark" aria-hidden="true">*</span>
            </span>
            <input
              aria-describedby={formErrors.name ? `${formId}-name-error` : undefined}
              aria-invalid={Boolean(formErrors.name)}
              autoFocus
              id={`${formId}-name`}
              maxLength={200}
              name="name"
              onChange={(event) => {
                setDraft({ ...draft, name: event.target.value });
                clearFormError("name");
              }}
              placeholder="例如：旧站备份"
              ref={nameRef}
              required
              value={draft.name}
            />
            {formErrors.name && (
              <small className="field-error" id={`${formId}-name-error`}>
                {formErrors.name}
              </small>
            )}
          </label>
          <label className="field">
            <span>领域</span>
            <select
              name="domain"
              onChange={(event) => setDraft({ ...draft, domain: event.target.value })}
              value={draft.domain}
            >
              <option value="auto">自动识别</option>
              <option value="web">Web</option>
              <option value="pwn">Pwn</option>
              <option value="reverse">Reverse</option>
              <option value="crypto">Crypto</option>
              <option value="misc">Misc</option>
            </select>
          </label>
        </div>

        <div className="field description-field">
          <div className="field-label-row">
            <span id={`${formId}-description-label`}>
              题目描述 <span className="required-mark" aria-hidden="true">*</span>
            </span>
            <div className="mode-switch" aria-label="题目描述显示方式">
              <button
                aria-pressed={descriptionMode === "edit"}
                className={descriptionMode === "edit" ? "is-active" : ""}
                onClick={() => setDescriptionMode("edit")}
                type="button"
              >
                编辑
              </button>
              <button
                aria-pressed={descriptionMode === "preview"}
                className={descriptionMode === "preview" ? "is-active" : ""}
                onClick={() => setDescriptionMode("preview")}
                type="button"
              >
                预览
              </button>
            </div>
          </div>
          {descriptionMode === "edit" ? (
            <>
              <textarea
                aria-describedby={
                  formErrors.description ? `${formId}-description-error` : undefined
                }
                aria-invalid={Boolean(formErrors.description)}
                aria-labelledby={`${formId}-description-label`}
                maxLength={100000}
                name="description"
                onChange={(event) => {
                  setDraft({ ...draft, description: event.target.value });
                  clearFormError("description");
                }}
                placeholder={"支持 Markdown。\n\n请粘贴题目说明、提示和已知条件。"}
                ref={descriptionRef}
                required
                rows={13}
                value={draft.description}
              />
              {formErrors.description && (
                <small className="field-error" id={`${formId}-description-error`}>
                  {formErrors.description}
                </small>
              )}
            </>
          ) : (
            <div className="description-preview" aria-label="题目描述预览">
              <MarkdownPreview value={draft.description} emptyText="填写描述后在这里预览" />
            </div>
          )}
        </div>

        <div className="upload-grid">
          <FileCollection
            accept={undefined}
            files={draft.attachments}
            icon="attachment"
            label="题目附件"
            onChange={(files) => setDraft({ ...draft, attachments: files })}
            onRemove={(index) =>
              setDraft({
                ...draft,
                attachments: draft.attachments.filter((_, itemIndex) => itemIndex !== index),
              })
            }
          />
          <FileCollection
            accept={undefined}
            files={draft.sourceFiles}
            icon="source"
            label="源码文件"
            onChange={(files) => setDraft({ ...draft, sourceFiles: files })}
            onRemove={(index) =>
              setDraft({
                ...draft,
                sourceFiles: draft.sourceFiles.filter((_, itemIndex) => itemIndex !== index),
              })
            }
          />
        </div>

        <details className="optional-fields">
          <summary>添加目标地址</summary>
          <label className="field">
            <span>授权目标 URL</span>
            <input
              inputMode="url"
              name="target_url"
              onChange={(event) => setDraft({ ...draft, targetUrl: event.target.value })}
              placeholder="http://127.0.0.1:5000"
              type="url"
              value={draft.targetUrl}
            />
            <small>记录地址不代表自动执行，后续请求仍受授权策略限制。</small>
          </label>
        </details>

        <label
          className={`authorization-check${formErrors.authorization ? " authorization-check--invalid" : ""}`}
        >
          <input
            aria-describedby={
              formErrors.authorization ? `${formId}-authorization-error` : undefined
            }
            aria-invalid={Boolean(formErrors.authorization)}
            checked={draft.authorizationConfirmed}
            name="authorization_confirmed"
            onChange={(event) => {
              setDraft({ ...draft, authorizationConfirmed: event.target.checked });
              clearFormError("authorization");
            }}
            ref={authorizationRef}
            required
            type="checkbox"
          />
          <span>
            我确认该题目属于已授权的 CTF、课程或本地研究范围。
            {formErrors.authorization && (
              <small className="field-error" id={`${formId}-authorization-error`}>
                {formErrors.authorization}
              </small>
            )}
          </span>
        </label>

        <div className="form-actions">
          <Link className="secondary-action" to="/">
            取消
          </Link>
          <button className="primary-action primary-action--submit" disabled={submitting}>
            {submitting ? "正在创建…" : "创建题目"}
          </button>
        </div>
      </form>
    </section>
  );
}

interface FileCollectionProps {
  label: string;
  files: File[];
  icon: "attachment" | "source";
  accept: string | undefined;
  onChange: (files: File[]) => void;
  onRemove: (index: number) => void;
}

function FileCollection({
  label,
  files,
  icon,
  accept,
  onChange,
  onRemove,
}: FileCollectionProps) {
  const inputId = useId();
  const CollectionIcon = icon === "attachment" ? Paperclip : FileCode2;
  return (
    <section className="file-collection" aria-labelledby={`${inputId}-label`}>
      <div className="file-collection__head">
        <div>
          <CollectionIcon aria-hidden="true" size={20} strokeWidth={1.7} />
          <span id={`${inputId}-label`}>{label}</span>
        </div>
        <input
          accept={accept}
          className="visually-hidden"
          id={inputId}
          multiple
          onChange={(event) => onChange(Array.from(event.target.files ?? []))}
          type="file"
        />
        <label className="file-picker" htmlFor={inputId}>
          选择文件
        </label>
      </div>
      {files.length === 0 ? (
        <p className="file-empty">可选，可一次选择多个文件。</p>
      ) : (
        <ul className="file-list">
          {files.map((file, index) => (
            <li key={`${file.name}-${file.lastModified}`}>
              <FileText aria-hidden="true" size={17} strokeWidth={1.6} />
              <span title={file.name}>{file.name}</span>
              <small>{formatBytes(file.size)}</small>
              <button
                aria-label={`移除 ${file.name}`}
                onClick={() => onRemove(index)}
                type="button"
              >
                <X aria-hidden="true" size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
