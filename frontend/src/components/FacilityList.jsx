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

// 시설 상세조회 및 검색 API의 이용시간 규정 통합
function getTimeOptions(detail, facility, sport) {
  if (Array.isArray(detail?.time_options)) {
    return detail.time_options.filter(
      (option) => !option.sport || option.sport === sport
    )
  }

  if (
    detail?.time_options &&
    typeof detail.time_options === 'object'
  ) {
    return [detail.time_options]
  }

  if (Array.isArray(facility.time_options)) {
    return facility.time_options.filter(
      (option) => !option.sport || option.sport === sport
    )
  }

  if (
    facility.time_options &&
    typeof facility.time_options === 'object'
  ) {
    return [facility.time_options]
  }

  return []
}

// 고정 예약 회차 목록 반환
function getFixedSlots(options) {
  const slots = options.flatMap((option) => {
    if (
      option.selection !== 'fixed_slot' ||
      !Array.isArray(option.slots)
    ) {
      return []
    }

    return option.slots
      .filter(
        (slot) =>
          slot?.start_time &&
          slot?.end_time
      )
      .map((slot) => [
        slot.start_time,
        slot.end_time,
      ])
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

// 시설 운영시간 표시
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

// 이용시간 규정 안내
function getSlotMessage(facility, detail) {
  if (facility.slot_status === 'rule_conflict') {
    return '적용 기간이 겹치는 규정이 있습니다. 공식 안내를 확인해 주세요.'
  }

  if (
    [
      'no_slots',
      'rule_missing',
      'rule_not_in_effect',
    ].includes(facility.slot_status)
  ) {
    return '선택한 날짜에 적용되는 예약 회차 정보가 없습니다.'
  }

  if (detail) {
    return '선택한 날짜에 확인된 이용시간 규정이 없습니다.'
  }

  return '예약 회차 정보 확인이 필요합니다.'
}

function FacilityList({
  facilities = [],
  alternatives = [],
  selectedIds = [],
  onToggle,
  searched,
  onCompare,
  loading,
  facilityTimes = {},
  onTimeChange,
  error,
  facilityDetails = {},
  detailLoading = {},
  detailErrors = {},
}) {
  const alternativeDistricts = Array.isArray(alternatives)
    ? alternatives
    : Array.isArray(alternatives?.districts)
      ? alternatives.districts
      : []

  const hasBlockedSelection = facilities.some(
    (facility) => {
      const id = facility.id ?? facility.facility_id

      return (
        selectedIds.includes(id) &&
        (
          facility.closure?.is_closed === true ||
          facilityDetails[id]?.closure?.is_closed === true ||
          facility.slot_status === 'rule_conflict' ||
          facilityDetails[id]?.slot_status === 'rule_conflict'
        )
      )
    }
  )

  const hasPendingDetails = selectedIds.some(
    (id) => Boolean(detailLoading[id])
  )

  const hasDetailErrors = selectedIds.some(
    (id) => Boolean(detailErrors[id])
  )

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
            다른 지역이나 이용 조건으로 다시 검색해 주세요.
          </p>

          {alternativeDistricts.length > 0 && (
            <p>
              검색 가능한 다른 지역은{' '}
              {alternativeDistricts.join(', ')}
              입니다.
            </p>
          )}
        </div>
      ) : (
        <>
          <div className="facility-list-info">
            <span>
              검색 결과 {facilities.length}곳
            </span>

            <span>
              비교 대상 {selectedIds.length}곳 선택됨
            </span>
          </div>

          <div className="facility-grid">
            {facilities.map((facility) => {
              const facilityId =
                facility.id ?? facility.facility_id

              const selected =
                selectedIds.includes(facilityId)

              const detail =
                facilityDetails[facilityId]

              const isLoading = Boolean(
                detailLoading[facilityId]
              )

              const detailError =
                detailErrors[facilityId]

              const sport =
                facility.sport ||
                detail?.sport ||
                facility.sports?.[0] ||
                detail?.sports?.[0]

              const timeOptions = getTimeOptions(
                detail,
                facility,
                sport
              )

              const slots =
                getFixedSlots(timeOptions)

              const flexibleOptions =
                timeOptions.filter(
                  (option) =>
                    option.selection === 'flexible'
                )

              const selectedTime =
                facilityTimes[facilityId] || ''

              const [selectedStart = '', selectedEnd = ''] =
                selectedTime.split('|')

              const isTestData =
                facility.isTestData === true ||
                facilityId === 'F001'

              const bookingUrl =
                detail?.booking_url ??
                facility.bookingUrl ??
                facility.booking_url

              const closure =
                detail?.closure ??
                facility.closure

              const isClosed =
                facility.closure?.is_closed === true ||
                detail?.closure?.is_closed === true

              const closureRules =
                Array.isArray(closure?.matched_rules)
                  ? closure.matched_rules
                      .map((rule) => rule?.note)
                      .filter(Boolean)
                  : []

              const hasRuleConflict =
                facility.slot_status === 'rule_conflict' ||
                detail?.slot_status === 'rule_conflict'

              const blocked =
                isClosed || hasRuleConflict

              const operatingHours =
                detail?.operating_hours ??
                facility.operating_hours

              const phone =
                detail?.phone ??
                facility.phone

              const closureNote =
                detail?.closure_note ??
                facility.closure_note

              return (
                <article
                  className={
                    selected
                      ? 'facility-card selected'
                      : 'facility-card'
                  }
                  key={facilityId}
                >
                  <div className="facility-card-top">
                    <span className="facility-category">
                      {getSportLabel(sport)}
                    </span>

                    <span className="facility-district">
                      {detail?.district ||
                        facility.district ||
                        '지역 확인 필요'}
                    </span>
                  </div>

                  <div className="facility-symbol">
                    {getSportIcon(sport)}
                  </div>

                  <h3>
                    {detail?.name ||
                      facility.name ||
                      '시설명 확인 필요'}
                  </h3>

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

                  {(detail ||
                    phone ||
                    operatingHours ||
                    closureNote) && (
                    <div className="facility-detail-info">
                      <p>
                        <strong>연락처: </strong>

                        {phone || '확인 필요'}
                      </p>

                      <p>
                        <strong>운영시간: </strong>

                        {formatOperatingHours(
                          operatingHours
                        )}
                      </p>

                      {operatingHours?.note &&
                        operatingHours.open_time &&
                        operatingHours.close_time && (
                          <p>
                            {operatingHours.note}
                          </p>
                        )}

                      <p>
                        <strong>휴장 안내: </strong>

                        {closureNote || '확인 필요'}
                      </p>
                    </div>
                  )}

                  {isClosed && (
                    <div
                      className="review-box"
                      style={{ marginTop: '12px' }}
                    >
                      <strong>
                        정기 휴장일입니다.
                      </strong>

                      {closureRules.length > 0 && (
                        <p>
                          {closureRules.join(' / ')}
                        </p>
                      )}

                      {closure?.source_url && (
                        <a
                          href={closure.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          휴장 규정 출처
                        </a>
                      )}
                    </div>
                  )}

                  {closure?.status ===
                    'needs_calendar_resolution' && (
                    <p className="result-disclaimer">
                      명절 휴장 여부는 공식 예약 안내에서
                      확인해 주세요.
                    </p>
                  )}

                  {!isClosed &&
                    facility.time_check?.status ===
                      'not_eligible' && (
                      <p className="result-disclaimer">
                        희망 시간이 시설의 이용시간 규정과
                        맞지 않습니다. 시간을 다시 확인해 주세요.
                      </p>
                    )}

                  {hasRuleConflict && (
                    <p className="error-message">
                      적용 기간이 겹치는 규정이 있습니다.
                      공식 안내를 확인해 주세요.
                    </p>
                  )}

                  <label className="facility-check">
                    <input
                      type="checkbox"
                      checked={selected}
                      disabled={blocked && !selected}
                      onChange={() =>
                        onToggle(facilityId)
                      }
                    />

                    비교 대상에 포함
                  </label>

                  {selected && (
                    <div className="field">
                      <label
                        htmlFor={`time-${facilityId}`}
                      >
                        이용시간 선택
                      </label>

                      {blocked ? (
                        <p className="error-message">
                          휴장 또는 이용시간 규정 충돌로
                          비교할 수 없는 시설입니다.
                          비교 대상에서 제외해 주세요.
                        </p>
                      ) : isLoading ? (
                        <p role="status">
                          시설 이용시간을 불러오는 중입니다.
                        </p>
                      ) : detailError ? (
                        <p
                          className="error-message"
                          role="alert"
                        >
                          {detailError}
                        </p>
                      ) : flexibleOptions.length > 0 ? (
                        <>
                          <div className="field">
                            <label
                              htmlFor={`time-${facilityId}`}
                            >
                              시작시간
                            </label>

                            <input
                              id={`time-${facilityId}`}
                              type="time"
                              value={selectedStart}
                              onChange={(event) =>
                                onTimeChange(
                                  facilityId,
                                  `${event.target.value}|${selectedEnd}`
                                )
                              }
                            />
                          </div>

                          <div className="field">
                            <label
                              htmlFor={`end-${facilityId}`}
                            >
                              종료시간
                            </label>

                            <input
                              id={`end-${facilityId}`}
                              type="text"
                              placeholder="HH:MM"
                              maxLength={5}
                              value={selectedEnd}
                              onChange={(event) =>
                                onTimeChange(
                                  facilityId,
                                  `${selectedStart}|${event.target.value}`
                                )
                              }
                            />
                          </div>

                          {flexibleOptions.map(
                            (option, index) => (
                              <div
                                key={index}
                                className="facility-detail-info"
                              >
                                {option.open_time &&
                                  option.close_time && (
                                    <p>
                                      이용 가능 시간:{' '}
                                      {option.open_time}
                                      {' ~ '}
                                      {option.close_time}
                                    </p>
                                  )}

                                {Array.isArray(
                                  option.allowed_minutes
                                ) &&
                                  option.allowed_minutes
                                    .length > 0 && (
                                    <p>
                                      허용 이용시간:{' '}
                                      {option.allowed_minutes
                                        .map(
                                          (minutes) =>
                                            `${minutes}분`
                                        )
                                        .join(', ')}
                                    </p>
                                  )}

                                {Number.isInteger(
                                  option.max_minutes
                                ) &&
                                  option.max_minutes > 0 && (
                                    <p>
                                      최대 이용시간:{' '}
                                      {option.max_minutes}분
                                    </p>
                                  )}
                              </div>
                            )
                          )}

                          {slots.length > 0 && (
                            <div className="field">
                              <label
                                htmlFor={`fixed-${facilityId}`}
                              >
                                고정 예약 회차
                              </label>

                              <select
                                id={`fixed-${facilityId}`}
                                value={
                                  slots.some(
                                    ([start, end]) =>
                                      `${start}|${end}` ===
                                      selectedTime
                                  )
                                    ? selectedTime
                                    : ''
                                }
                                onChange={(event) =>
                                  onTimeChange(
                                    facilityId,
                                    event.target.value
                                  )
                                }
                              >
                                <option value="">
                                  예약 회차 선택
                                </option>

                                {slots.map(
                                  ([start, end]) => (
                                    <option
                                      key={`${start}|${end}`}
                                      value={`${start}|${end}`}
                                    >
                                      {start} ~ {end}
                                    </option>
                                  )
                                )}
                              </select>
                            </div>
                          )}

                          <small>
                            운영시간과 이용시간 제한을
                            확인한 뒤 비교해 주세요.
                            실제 예약 가능 여부는 공식 예약
                            사이트에서 확인하세요.
                          </small>
                        </>
                      ) : slots.length > 0 ? (
                        <>
                          <select
                            id={`time-${facilityId}`}
                            value={selectedTime}
                            onChange={(event) =>
                              onTimeChange(
                                facilityId,
                                event.target.value
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
                          {getSlotMessage(
                            facility,
                            detail
                          )}
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
                    <p>
                      공식 예약 링크 확인 필요
                    </p>
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
              selectedIds.length === 0 ||
              hasPendingDetails ||
              hasDetailErrors ||
              hasBlockedSelection
            }
          >
            {loading
              ? '비교 중...'
              : hasPendingDetails
                ? '시설 상세정보 불러오는 중...'
                : `선택한 시설 ${selectedIds.length}곳 비교하기`}
          </button>
        </>
      )}
    </section>
  )
}

export default FacilityList