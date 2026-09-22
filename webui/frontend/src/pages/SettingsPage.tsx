import { LockKeyhole, Monitor, PackageOpen } from "lucide-react";

export function SettingsPage() {
  return (
    <section className="settings-page" aria-labelledby="settings-title">
      <header className="page-heading">
        <div>
          <h1 id="settings-title">设置</h1>
          <p>查看本地题目工作台的使用范围与材料处理方式。</p>
        </div>
      </header>
      <dl className="settings-register">
        <div>
          <dt>
            <Monitor aria-hidden="true" size={20} strokeWidth={1.7} />
            运行范围
          </dt>
          <dd>界面仅在当前电脑上提供访问。</dd>
        </div>
        <div>
          <dt>
            <PackageOpen aria-hidden="true" size={20} strokeWidth={1.7} />
            上传材料
          </dt>
          <dd>附件和源码只会被复制，不会自动解压或执行。</dd>
        </div>
        <div>
          <dt>
            <LockKeyhole aria-hidden="true" size={20} strokeWidth={1.7} />
            敏感信息
          </dt>
          <dd>常见凭据文件和敏感值会在导入前被拒绝。</dd>
        </div>
      </dl>
    </section>
  );
}
