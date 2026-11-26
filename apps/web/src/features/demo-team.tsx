import { ArrowRight, LogIn, LogOut, UserRound, UsersRound } from 'lucide-react'
import { Link, Navigate, useNavigate, useOutletContext } from 'react-router-dom'

export type DemoSession = {
  signedIn: boolean
  setSignedIn: (value: boolean) => void
}

export function DemoLogin() {
  const { signedIn, setSignedIn } = useOutletContext<DemoSession>()
  const navigate = useNavigate()
  if (signedIn) return <Navigate to="/team" replace />

  return (
    <>
      <header className="page-heading"><h1>演示登录</h1></header>
      <section className="panel identity-panel">
        <div className="panel-heading">
          <span className="section-icon"><LogIn size={20} /></span>
          <div><h2>以演示选手进入</h2><p>使用浏览器中的示例身份体验队伍页面。</p></div>
        </div>
        <p className="muted">演示提交与验证由当前 API 共享。正式身份验证和队伍隔离待赛务服务接入。</p>
        <div className="identity-actions">
          <button type="button" className="button primary" onClick={() => {
            setSignedIn(true)
            navigate('/team', { replace: true })
          }}>进入演示队伍 <ArrowRight size={16} aria-hidden="true" /></button>
        </div>
      </section>
    </>
  )
}

export function DemoTeam() {
  const { signedIn, setSignedIn } = useOutletContext<DemoSession>()

  return (
    <>
      <header className="page-heading"><h1>我的队伍</h1><p>查看当前演示身份的队伍信息。</p></header>
      <section className="panel identity-panel">
        <div className="panel-heading">
          <span className="section-icon blue"><UsersRound size={20} /></span>
          <h2>{signedIn ? 'AgentQuant 示例队伍' : '请先登录演示身份'}</h2>
        </div>
        {signedIn ? (
          <>
            <div className="team-member">
              <UserRound size={20} aria-hidden="true" />
              <div><strong>演示选手</strong><p className="muted">示例成员</p></div>
            </div>
            <div className="identity-actions">
              <Link className="button primary" to="/">进入策略验证 <ArrowRight size={16} aria-hidden="true" /></Link>
              <button type="button" className="button secondary" onClick={() => setSignedIn(false)}>
                <LogOut size={16} aria-hidden="true" />退出演示身份
              </button>
            </div>
          </>
        ) : <Link className="button primary" to="/login">前往演示登录 <ArrowRight size={16} aria-hidden="true" /></Link>}
      </section>
    </>
  )
}
