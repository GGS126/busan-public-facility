function getSportLabel(sport) {
  const labels = {
    tennis: '테니스',
    futsal: '풋살',
  }

  return labels[sport] || sport || '종목 확인 필요'
}

function getSportIcon(sport) {
  const icons = {
    tennis: '🎾',
    futsal: '⚽',
  }

  return icons[sport] || '🏟️'
}

function toMinutes(time) {
  if (!time || !/^\d{2}:\d{2}$/.test(time)) {
    return null
  }

  const [hour, minute] = time.split(':').map(Number)
  return hour * 60 + minute
}

function fromMinutes(minutes) {
  const hour = String(Math.floor(minutes / 60)).padStart(2, '0')
  const minute = String(minutes % 60).padStart(2, '0')
  return `${hour}:${minute}`
}

function buildFlexibleSlots(option) {
  const open = toMinutes(option.open_time)
  const close = toMinutes(option.close_time)

  if (open === null || close === null || close <= open) {
    return []
  }

  const allowed = Array.isArray(option.allowed_minutes)
    ? option.allowed_minutes.filter(
        (minutes) =>
          Number.isInteger(minutes) && minutes > 0
      )
    : []

  const maxMinutes =
    Number.isInteger(option.max_minutes) &&
    option.max_minutes > 0
      ? option.max_minutes
      : null

  // 허용 시간이 명시되면 해당 길이만 사용한다.
  // 최대 시간만 명시되면 30분 단위로 생성한다.
  const durations = allowed.length > 0
    ? allowed.filter(
        (minutes) =>
          maxMinutes === null || minutes <= maxMinutes
      )
    : maxMinutes !== null
      ? Array.from(
          { length: Math.floor(maxMinutes / 30) },
          (_, index) => (index + 1) * 30
        )
      : []

  const slots = []

  for (let start = open; start < close; start += 30) {
    for (const duration of durations) {
      const end = start + duration

      if (end <= close) {
        slots.push([
          fromMinutes(start),
          fromMinutes(end),
        ])
      }
    }
  }

  return slots
}

function getDetailSlots(detail, sport) {
  if (!detail || !Array.isArray(detail.time_options)) {
    return []
  }

  const options = detail.time_options.filter(
    (option) => option.sport === sport
  )

  const slots = options.flatMap((option) => {
    if (option.selection === 'fixed_slot') {
      return Array.isArray(option.slots)
        ? option.slots
            .filter(
              (slot) =>
                slot?.start_time &&
                slot?.end_time
            )
            .map((slot) => [
              slot.start_time,
              slot.end_time,
            ])
        : []
    }

    if (option.selection === 'flexible') {
      return buildFlexibleSlots(option)
    }

    return []
  })

  return Array.from(
    new Map(
      slots.map((slot) => [
        `${slot[0]}|${slot[1]}`,
        slot,
      ])
    ).values()
  ).sort((a, b) =>
    `${a[0]}|${a[1]}`.localeCompare(
      `${b[0]}|${b[1]}`
    )
  )
}

function formatOperatingHours(hours) {
  if (!hours) {
    return '확인 필요'
  }

  const start = hours.open_time
  const end = hours.close_time

  if (start && end) {
    return `${start} ~ ${end}`
  }

  return hours.note || '확인 필요'
}

function FacilityList({
  facilities,
  selectedIds,
  onToggle,
  searched,
  onCompare,
  loading,
  facilityTimes,
  onTimeChange,
  error,
  facilityDetails = {},
  detailLoading = {},
  detailErrors = {},
}) {
  return (
    <section className="facility-section" id="facilities">
      <div className="section-heading">
        <span className="section-number">02</span>

        <div>
          <h2>시설 검색 결과</h2>
          <p>
            비교할 시설을 선택하고 이용시간을 지정하세요.
          </p>
        </div>
      </div>

      {!searched ? (
        <div className="result-empty">
          <h3>아직 시설을 검색하지 않았습니다</h3>
          <p>
            이용 조건을 입력한 뒤 시설 검색하기를
            눌러주세요.
          </p>
        </div>
      ) : facilities.length === 0 ? (
        <div className="facility-no-results">
          <h3>검색 결과가 없습니다</h3>
          <p>
            현재 등록된 시설 중 조건에 맞는 시설이 없습니다.
          </p>
          <p>
            시설 검색 API 연동 전에는 일부 시설만
            표시됩니다.
          </p>
        </div>
      ) : (
        <>
          <div className="facility-list-info">
            <span>검색 결과 {facilities.length}곳</span>
            <span>
              비교 대상 {selectedIds.length}곳 선택됨
            </span>
          </div>

          <div className="facility-grid">
            {facilities.map((facility) => {
              const selected = selectedIds.includes(
                facility.id
              )

              const detail = facilityDetails[facility.id]
              const isLoading = Boolean(
                detailLoading[facility.id]
              )
              const detailError = detailErrors[facility.id]
              const slots = getDetailSlots(
                detail,
                facility.sport
              )

              const selectedTime =
                facilityTimes[facility.id] || ''

              const isTestData =
                facility.isTestData === true

              const bookingUrl =
                detail?.booking_url ??
                facility.bookingUrl

              return (
                <article
                  className={
                    selected
                      ? 'facility-card selected'
                      : 'facility-card'
                  }
                  key={facility.id}
                >
                  <div className="facility-card-top">
                    <span className="facility-category">
                      {getSportLabel(facility.sport)}
                    </span>

                    <span className="facility-district">
                      {detail?.district ||
                        facility.district ||
                        '지역 확인 필요'}
                    </span>
                  </div>

                  <div className="facility-symbol">
                    {getSportIcon(facility.sport)}
                  </div>

                  <h3>{detail?.name || facility.name}</h3>

                  <p>
                    {detail?.address ||
                      facility.address ||
                      '주소 확인 필요'}
                  </p>

                  {isTestData && (
                    <div
                      className="review-box"
                      style={{ marginTop: '12px' }}
                    >
                      <strong>
                        백엔드 연동 테스트용 가상 시설
                      </strong>
                      <p>
                        실제 부산 공공체육시설이 아닙니다.
                        표시된 정보는 기능 검증용입니다.
                      </p>
                    </div>
                  )}

                  {detail && (
                    <div className="facility-detail-info">
                      <p>
                        <strong>연락처: </strong>
                        {detail.phone || '확인 필요'}
                      </p>

                      <p>
                        <strong>운영시간: </strong>
                        {formatOperatingHours(
                          detail.operating_hours
                        )}
                      </p>

                      {detail.operating_hours?.note && (
                        <p>
                          {detail.operating_hours.note}
                        </p>
                      )}

                      <p>
                        <strong>휴장 안내: </strong>
                        {detail.closure_note ||
                          '확인 필요'}
                      </p>
                    </div>
                  )}

                  <label className="facility-check">
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() =>
                        onToggle(facility.id)
                      }
                    />
                    비교 대상에 포함
                  </label>

                  {selected && (
                    <div className="field">
                      <label
                        htmlFor={`time-${facility.id}`}
                      >
                        이용시간 선택
                      </label>

                      {isLoading ? (
                        <p role="status">
                          시설 이용시간을 불러오는 중입니다.
                        </p>
                      ) : detailError ? (
                        <p className="error-message">
                          {detailError}
                        </p>
                      ) : slots.length > 0 ? (
                        <>
                          <select
                            id={`time-${facility.id}`}
                            value={selectedTime}
                            onChange={(e) =>
                              onTimeChange(
                                facility.id,
                                e.target.value
                              )
                            }
                          >
                            <option value="">
                              이용시간을 선택하세요
                            </option>

                            {slots.map(([start, end]) => {
                              const value =
                                `${start}|${end}`

                              return (
                                <option
                                  key={value}
                                  value={value}
                                >
                                  {start} ~ {end}
                                </option>
                              )
                            })}
                          </select>

                          <small>
                            실제 예약 가능 여부는
                            공식 예약 사이트에서 확인하세요.
                          </small>
                        </>
                      ) : (
                        <p className="error-message">
                          {detail
                            ? '선택한 날짜에 확인된 이용시간 규정이 없습니다.'
                            : '시설 상세정보를 불러오지 못했습니다.'}
                        </p>
                      )}
                    </div>
                  )}

                  {bookingUrl && !isTestData ? (
                    <a
                      className="facility-booking-link"
                      href={bookingUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      공식 예약 사이트 이동 ↗
                    </a>
                  ) : isTestData ? (
                    <p>
                      테스트용 시설로 공식 예약
                      링크가 없습니다.
                    </p>
                  ) : (
                    <p>공식 예약 링크 확인 필요</p>
                  )}
                </article>
              )
            })}
          </div>

          {error && (
            <p className="error-message" role="alert">
              {error}
            </p>
          )}

          <button
            type="button"
            className="search-button"
            onClick={onCompare}
            disabled={
              loading ||
              selectedIds.length === 0
            }
          >
            {loading
              ? '비교 중...'
              : `선택한 시설 ${selectedIds.length}곳 비교하기`}
          </button>
        </>
      )}
    </section>
  )
}

export default FacilityList