
const discounts = [
  ['none', '감면 없음'],
  ['disabled', '장애인'],
  ['multi_child', '다자녀 가정'],
  ['low_income', '기초생활수급자'],
  ['national_merit', '국가유공자'],
  ['independence_merit', '독립유공자'],
]

function SearchForm({
  sport,
  setSport,
  district,
  setDistrict,
  date,
  setDate,
  people,
  setPeople,
  discountType,
  setDiscountType,
  eligibleCount,
  setEligibleCount,
  onSearch,
  loading,
  error,
  clearResult,
}) {
  function update(setter, value) {
    setter(value)
    clearResult()
  }

  return (
    <section className="search-card" id="search">
      <div className="section-heading">
        <span className="section-number">01</span>
        <div>
          <h2>이용 조건 입력</h2>
          <p>종목, 지역, 날짜와 이용 인원을 입력하세요.</p>
          <p>이용시간은 시설을 선택한 뒤 지정합니다.</p>
        </div>
      </div>

      <div className="search-fields">
        <div className="field">
          <label htmlFor="sport">이용 종목</label>
          <select
            id="sport"
            value={sport}
            onChange={(e) => update(setSport, e.target.value)}
          >
            <option value="tennis">테니스</option>
          </select>
        </div>

        <div className="field">
          <label htmlFor="district">이용 지역</label>
          <select
            id="district"
            value={district}
            onChange={(e) => update(setDistrict, e.target.value)}
          >
            <option value="전체">부산 전체</option>
            <option value="해운대구">해운대구</option>
            <option value="사상구">사상구</option>
            <option value="서구">서구</option>
          </select>
        </div>

        <div className="field">
          <label htmlFor="date">이용 날짜</label>
          <input
            id="date"
            type="date"
            value={date}
            onChange={(e) => update(setDate, e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="people">전체 이용 인원</label>
          <input
            id="people"
            type="number"
            min="1"
            value={people}
            onChange={(e) => update(setPeople, e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="discount">감면 유형</label>
          <select
            id="discount"
            value={discountType}
            onChange={(e) => {
              setDiscountType(e.target.value)
              setEligibleCount('0')
              clearResult()
            }}
          >
            {discounts.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>

        {discountType !== 'none' && (
          <div className="field">
            <label htmlFor="eligible">감면 대상 인원</label>
            <input
              id="eligible"
              type="number"
              min="0"
              max={people}
              value={eligibleCount}
              onChange={(e) => update(setEligibleCount, e.target.value)}
            />
          </div>
        )}
      </div>

      {error && <p className="error-message">{error}</p>}

      <button
        className="search-button"
        onClick={onSearch}
        disabled={loading}
      >
        {loading ? '검색 중...' : '시설 검색하기'}
      </button>
    </section>
  )
}

export default SearchForm
