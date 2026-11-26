import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Activity, Database, LayoutDashboard, UsersRound } from 'lucide-react'
import { lazy, Suspense, useLayoutEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Link, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { ApiError } from './api'
import { CatalogPage } from './features/catalog'
import { DemoLogin, DemoTeam } from './features/demo-team'
import type { DemoSession } from './features/demo-team'
import { Workspace } from './features/workspace'
import { readLocal, writeLocal } from './storage'
import { Loading } from './ui'
import './styles.css'

const RunPage = lazy(() => import('./features/run'))
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) => count < 1 && !(error instanceof ApiError && error.status < 500),
      retryDelay: 1_000,
    },
  },
})

function Layout() {
  const { pathname } = useLocation()
  const [signedIn, setSignedIn] = useState(() => readLocal('demo-participant') === '1')

  function setDemoSession(value: boolean) {
    writeLocal('demo-participant', value ? '1' : null)
    setSignedIn(value)
  }

  const session: DemoSession = { signedIn, setSignedIn: setDemoSession }
  const previousPath = useRef(pathname)
  const main = useRef<HTMLElement>(null)
  useLayoutEffect(() => {
    if (previousPath.current === pathname) return
    previousPath.current = pathname
    window.scrollTo(0, 0)
    main.current?.focus({ preventScroll: true })
  }, [pathname])

  return (
    <div className="app">
      <a className="skip-link" href="#main-content">跳至主要内容</a>
      <aside className="sidebar">
        <Link className="brand" to="/" aria-label="AgentQuant 工作台">
          <span className="brand-icon"><Activity size={22} aria-hidden="true" /></span>
          <strong>AgentQuant</strong>
        </Link>
        <nav className="navigation" aria-label="主导航">
          <NavLink to="/" end><LayoutDashboard size={18} aria-hidden="true" />策略验证</NavLink>
          <NavLink to="/data"><Database size={18} aria-hidden="true" />数据目录</NavLink>
          <NavLink to="/team"><UsersRound size={18} aria-hidden="true" />我的队伍</NavLink>
        </nav>
      </aside>
      <div className="content">
        <header className="topbar">
          <span>参赛工作台</span>
          <div className="topbar-actions">
            <span className="badge demo-badge"><span />演示环境</span>
            <Link className="text-link" to={signedIn ? '/team' : '/login'}>{signedIn ? '演示选手' : '演示登录'}</Link>
          </div>
        </header>
        <main id="main-content" ref={main} tabIndex={-1}><Outlet context={session} /></main>
      </div>
    </div>
  )
}

function NotFound() {
  return (
    <div className="panel">
      <h1>页面不存在</h1>
      <Link className="text-link" to="/">返回策略验证</Link>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Workspace />} />
          <Route path="data" element={<CatalogPage />} />
          <Route path="login" element={<DemoLogin />} />
          <Route path="team" element={<DemoTeam />} />
          <Route path="runs/:runId" element={<Suspense fallback={<Loading>正在打开验证任务…</Loading>}><RunPage /></Suspense>} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </QueryClientProvider>,
)
