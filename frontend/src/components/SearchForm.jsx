// 30분 단위 이용시간 목록 생성
const timeOptions = Array.from({ length: 48 }, (_, index) => {
  const hour = String(Math.floor(index / 2)).padStart(2, '0')
  const minute = index % 2 === 0 ? '00' : '30'
  return `${hour}:${minute}`
})

function SearchForm({
  sport,
  setSport,
  district,
  setDistrict,
  date,
  setDate,
  startTime,
  setStartTime,
  endTime,
  setEndTime,
  people,
  setPeople,
  discountType,
  setDiscountType,
  eligibleCount,
  setEligibleCount,
  representativeEligible,
  setRepresentativeEligible,
  optionalLightingMinutes,
  setOptionalLightingMinutes,
  onSearch,
  loading,
  error,
  clearResult,
  options,
  optionsLoading,
  optionsError,
  onRetryOptions,
}) {
  function update(setter, value) {
    setter(value)
    clearResult()
  }

  const unavailable = optionsLoading || Boolean(optionsError)

  return (
    <section className="search-card" id="search">
      <div className="section-heading">
        <span className="section-number">01</span>
        <div>
          <h2>이용 조건 입력</h2>
          <p>종목, 지역, 날짜와 이용 인원을 입력하세요.</p>
          <p>
            희망 이용시간과 일치하는 시설 회차가 있으면
            자동으로 선택됩니다.
          </p>
        </div>
      </div>

      {optionsLoading && (
        <p role="status">
          이용 가능한 종목, 지역 및 감면 유형을 불러오는 중입니다.
        </p>
      )}

      {optionsError && (
        <div role="alert">
          <p className="error-message">
            이용조건 선택지를 불러오지 못했습니다.{' '}
            {optionsError}
          </p>

          <button
            type="button"
            onClick={onRetryOptions}
            disabled={optionsLoading}
          >
            다시 시도
          </button>
        </div>
      )}

      <div className="search-fields">
        <div className="field">
          <label htmlFor="sport">이용 종목</label>

          <select
            id="sport"
            value={sport}
            disabled={unavailable || options.sports.length === 0}
            onChange={(e) => update(setSport, e.target.value)}
          >
            {options.sports.length === 0 && (
              <option value="">선택 가능한 종목 없음</option>
            )}

            {options.sports.map((item) => (
              <option key={item.code} value={item.code}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="district">이용 지역</label>

          <select
            id="district"
            value={district}
            disabled={unavailable}
            onChange={(e) => update(setDistrict, e.target.value)}
          >
            <option value="전체">부산 전체</option>

            {options.districts.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
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
          <label htmlFor="start-time">희망 시작시간</label>

          <select
            id="start-time"
            value={startTime}
            onChange={(e) => update(setStartTime, e.target.value)}
          >
            <option value="">시작시간 선택</option>

            {timeOptions.map((time) => (
              <option key={time} value={time}>
                {time}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="end-time">희망 종료시간</label>

          <select
            id="end-time"
            value={endTime}
            onChange={(e) => update(setEndTime, e.target.value)}
          >
            <option value="">종료시간 선택</option>

            {timeOptions
              .filter((time) => !startTime || time > startTime)
              .concat('24:00')
              .map((time) => (
                <option key={time} value={time}>
                  {time}
                </option>
              ))}
          </select>
        </div>

        <div className="field">
          <label htmlFor="people">전체 이용 인원</label>

          <input
            id="people"
            type="number"
            min="1"
            step="1"
            value={people}
            onChange={(e) => update(setPeople, e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="discount">감면 유형</label>

          <select
            id="discount"
            value={discountType}
            disabled={unavailable}
            onChange={(e) => {
              setDiscountType(e.target.value)
              setEligibleCount(
                e.target.value === 'none' ? '0' : '1'
              )
              setRepresentativeEligible(false)
              clearResult()
            }}
          >
            <option value="none">감면 없음</option>

            {options.discount_types
              .filter((item) => item.code !== 'none')
              .map((item) => (
                <option key={item.code} value={item.code}>
                  {item.label}
                </option>
              ))}
          </select>
        </div>

        {discountType !== 'none' && (
          <>
            <div className="field">
              <label htmlFor="eligible">감면 대상 인원</label>

              <input
                id="eligible"
                type="number"
                min="1"
                step="1"
                max={people}
                value={eligibleCount}
                onChange={(e) =>
                  update(setEligibleCount, e.target.value)
                }
              />
            </div>

            <div className="field">
              <label htmlFor="representative-eligible">
                예약 대표자 감면 대상 여부
              </label>

              <select
                id="representative-eligible"
                value={representativeEligible ? 'yes' : 'no'}
                onChange={(e) =>
                  update(
                    setRepresentativeEligible,
                    e.target.value === 'yes'
                  )
                }
              >
                <option value="no">아니요</option>
                <option value="yes">
                  예 (대표자를 감면 대상 인원에 포함)
                </option>
              </select>
            </div>
          </>
        )}

        <div className="field">
          <label htmlFor="optional-lighting-minutes">
            선택 조명 사용 시간 (분)
          </label>

          <input
            id="optional-lighting-minutes"
            type="number"
            min="0"
            step="1"
            value={optionalLightingMinutes}
            onChange={(e) =>
              update(
                setOptionalLightingMinutes,
                e.target.value
              )
            }
          />

          <small>
            사용하지 않으면 0분을 입력하세요.
            시설별 조명 가능 시간은 다를 수 있습니다.
          </small>
        </div>
      </div>

      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      <button
        type="button"
        className="search-button"
        onClick={onSearch}
        disabled={
          loading ||
          unavailable ||
          options.sports.length === 0
        }
      >
        {loading
          ? '검색 중...'
          : optionsLoading
            ? '이용조건 불러오는 중...'
            : '시설 검색하기'}
      </button>
    </section>
  )
}

export default SearchForm