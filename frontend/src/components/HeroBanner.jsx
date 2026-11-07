
function HeroBanner() {
  return (
    <section className="hero" id="home">
      <div className="hero-content">
        <span className="hero-tag">BUSAN SPORTS FACILITY GUIDE</span>
        <h1>
          부산 공공체육시설,
          <br />
          이용 조건부터 요금까지 한눈에
        </h1>
        <p>
          원하는 시설과 이용 조건을 선택하면
          예상요금과 예약 정보를 편리하게 확인할 수 있습니다.
        </p>
        <a href="#search" className="hero-button">
          시설 찾아보기
        </a>
      </div>
      <div className="hero-decoration">🏸</div>
    </section>
  )
}

export default HeroBanner
