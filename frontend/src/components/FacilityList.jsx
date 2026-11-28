import {
  getTimeOptions,
  isBlockedFacility,
} from '../data/facilityTimeOptions'

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
  if (
    facility.slot_status === 'rule_conflict' ||
    detail?.slot_status === 'rule_conflict'
  ) {
    return '적용 기간이 겹치는 규정이 있습니다. 공식 안내를 확인해 주세요.'
  }

  const unavailableStatuses = [
    'no_slots',
    'rule_missing',
    'rule_not_in_effect',
  ]

  if (
    unavailableStatuses.includes(
      facility.slot_status
    ) ||
    unavailableStatuses.includes(
      detail?.slot_status
    )
  ) {
    return '선택한 날짜에 적용되는 예약 회차 정보가 없습니다.'
  }

  if (detail) {
    return '선택한 날짜에 확인된 이용시간 규정이 없습니다. 공식 안내를 확인해 주세요.'
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
  onRetryDetail,
}) {
  const alternativeDistricts = Array.isArray(alternatives)
    ? alternatives
    : Array.isArray(alternatives?.districts)
      ? alternatives.districts
      : []

  // 휴장 또는 이용시간 규정 충돌 시설 확인
  const hasBlockedSelection = facilities.some(
    (facility) => {
      const id = facility.id ?? facility.facility_id

      return (
        selectedIds.includes(id) &&
        isBlockedFacility(
          facility,
          facilityDetails[id]
        )
      )
    }
  )

  // 상세정보 조회 중인 시설 확인
  const hasPendingDetails = selectedIds.some(
    (id) => Boolean(detailLoading[id])
  )

  // 상세정보 조회 실패 시설 확인
  const hasDetailErrors = selectedIds.some(
    (id) => Boolean(detailErrors[id])
  )

  // 상세정보가 아직 없는 시설 확인
  const hasMissingDetails = selectedIds.some(
    (id) => !facilityDetails[id]
  )

  // 이용 가능한 시간 정책이 없는 시설 확인
  const hasMissingTimeOptions = facilities.some(
    (facility) => {
      const id = facility.id ?? facility.facility_id

      if (
        !selectedIds.includes(id) ||
        detailLoading[id] ||
        detailErrors[id] ||
        !facilityDetails[id]
      ) {
        return false
      }

      const detail = facilityDetails[id]

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

      const hasFlexibleOption = timeOptions.some(
        (option) =>
          option.selection === 'flexible'
      )

      const hasFixedSlots =
        getFixedSlots(timeOptions).length > 0

      return (
        !hasFlexibleOption &&
        !hasFixedSlots
      )
    }
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

              // 상세정보와 검색 결과의 시간 정책 통합
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

              const [
                selectedStart = '',
                selectedEnd = '',
              ] = selectedTime.split('|')

              // 백엔드 테스트용 가상 시설
              const isVirtualFacility =
                facilityId === 'F001'

              // 개발용 Mock 데이터
              const isMockData =
                !isVirtualFacility &&
                (
                  facility.isTestData === true ||
                  detail?.isTestData === true
                )

              const isTestData =
                isVirtualFacility || isMockData

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

              const blocked = isBlockedFacility(
                facility,
                detail
              )

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
                      detail?.facility_name ||
                      facility.name ||
                      facility.facility_name ||
                      '시설명 확인 필요'}
                  </h3>

                  <p>
                    {detail?.address ||
                      facility.address ||
                      '주소 확인 필요'}
                  </p>

                  {/* 백엔드 테스트용 가상 시설 안내 */}
                  {isVirtualFacility && (
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

                  {/* 개발용 Mock 데이터 안내 */}
                  {isMockData && (
                    <div
                      className="review-box"
                      style={{ marginTop: '12px' }}
                    >
                      <strong>
                        개발용 Mock 데이터
                      </strong>

                      <p>
                        실제 시설 정보를 바탕으로 구성한
                        기능 검증용 데이터입니다.
                        실제 이용시간 및 요금과 다를 수 있습니다.
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
                        <>
                          <p
                            className="error-message"
                            role="alert"
                          >
                            {detailError}
                          </p>

                          <button
                            type="button"
                            onClick={() =>
                              onRetryDetail(facilityId)
                            }
                            disabled={
                              isLoading ||
                              typeof onRetryDetail !==
                                'function'
                            }
                          >
                            상세정보 다시 불러오기
                          </button>

                          <small>
                            시설 선택을 해제하지 않고
                            상세정보를 다시 불러올 수 있습니다.
                          </small>
                        </>
                      ) : !detail ? (
                        <p role="status">
                          시설 상세정보 확인이 필요합니다.
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
                                option.close_time ? (
                                  <p>
                                    이용 가능 시간:{' '}
                                    {option.open_time}
                                    {' ~ '}
                                    {option.close_time}
                                  </p>
                                ) : (
                                  <p>
                                    운영시간 범위가 확인되지
                                    않았습니다. 공식 안내를
                                    확인해 주세요.
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
                        <>
                          <p className="error-message">
                            {getSlotMessage(
                              facility,
                              detail
                            )}
                          </p>

                          <small>
                            이용시간 규정을 확인할 수 없어
                            비교가 제한됩니다.
                            비교 대상에서 제외해 주세요.
                          </small>
                        </>
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
                  ) : isVirtualFacility ? (
                    <p>
                      테스트용 시설로 공식 예약
                      링크가 없습니다.
                    </p>
                  ) : isMockData ? (
                    <p>
                      개발용 Mock 모드에서는 공식 예약
                      링크를 제공하지 않습니다.
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

          {hasDetailErrors && (
            <p className="error-message" role="alert">
              상세정보 조회에 실패한 시설이 있습니다.
              해당 시설의 상세정보를 다시 불러오거나
              비교 대상에서 제외해 주세요.
            </p>
          )}

          {hasMissingTimeOptions && (
            <p className="error-message" role="alert">
              이용시간 규정이 확인되지 않은 시설이 있습니다.
              해당 시설을 비교 대상에서 제외해 주세요.
            </p>
          )}

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
              hasMissingDetails ||
              hasMissingTimeOptions ||
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