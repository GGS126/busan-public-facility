
function Header() {
  return (
    <header className="site-header">
      <div className="header-inner">
        <a className="logo" href="#home">
          <span className="logo-mark">B</span>
          부산 체육시설 비교
        </a>

        <nav className="nav-menu">
          <a href="#home">홈</a>
          <a href="#search">시설 검색</a>
          <a href="#guide">이용 안내</a>
        </nav>
      </div>
    </header>
  )
}

export default Header
