import { Plus, Settings } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

export function AppLayout() {
  return (
    <>
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      <header className="site-header">
        <div className="site-header__inner">
          <NavLink className="wordmark" to="/" aria-label="Agonionce 题目库">
            Agonionce
          </NavLink>
          <nav className="primary-nav" aria-label="主要导航">
            <NavLink
              className={({ isActive }) =>
                `nav-link${isActive ? " nav-link--active" : ""}`
              }
              to="/"
              end
            >
              题目
            </NavLink>
            <NavLink
              className={({ isActive }) =>
                `nav-link${isActive ? " nav-link--active" : ""}`
              }
              to="/settings"
            >
              <Settings aria-hidden="true" size={17} strokeWidth={1.8} />
              设置
            </NavLink>
          </nav>
          <NavLink className="primary-action" to="/new">
            <Plus aria-hidden="true" size={18} strokeWidth={2} />
            新建题目
          </NavLink>
        </div>
      </header>
      <main id="main-content" className="page-shell" tabIndex={-1}>
        <Outlet />
      </main>
    </>
  );
}
