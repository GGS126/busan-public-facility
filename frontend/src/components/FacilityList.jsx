
import {
  facilitySlots,
  getFacilitySlots,
} from '../data/facilitySlots'

function FacilityList({
  facilities,
  alternatives,
  selectedIds,
  onToggle,
  searched,
  onCompare,
  loading,
  facilityTimes,
  onTimeChange,
  error,
}) {
  return (
    <section className="facility-section" id="facilities">
      <div className="section-heading">
        <span className="section-number">02</span>
        <div>
          <h2>시설 검색 결과</h2>
          <p>비교할 시설을 선택하고 이용시간을 지정하세요.</p>
        </div>
      </div>

      {!searched ? (
        <div className="result-empty">
          <h3>아직 시설을 검색하지 않았습니다</h3>
          <p>이용 조건을 입력한 뒤 시설 검색하기를 눌러주세요.</p>
        </div>
      ) : facilities.length === 0 ? (
        <div className="facility-no-results">
          <h3>검색 결과가 없습니다</h3>
          <p>다른 지역이나 이용 조건으로 다시 검색해 주세요.</p>
          {alternatives.length > 0 && <p>검색 가능한 다른 지역은 {alternatives.join(', ')}입니다.</p>}
        </div>
      ) : (
        <>
          <div className="facility-list-info">
            <span>검색 결과 {facilities.length}곳</span>
            <span>비교 대상 {selectedIds.length}곳 선택됨</span>
          </div>

          <div className="facility-grid">
            {facilities.map((facility) => {
              const selected = selectedIds.includes(facility.id)
              const slots = getFacilitySlots(facility.id, facility.time_options)
              const selectedTime = facilityTimes[facility.id] || ''

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
                      {facility.sport === 'tennis'
                        ? '테니스'
                        : facility.sport}
                    </span>
                    <span className="facility-district">
                      {facility.district}
                    </span>
                  </div>

                  <div className="facility-symbol">🎾</div>

                  <h3>{facility.name}</h3>
                  <p>{facility.address}</p>
                  {facility.closure?.is_closed && (
                    <div>
                      <p>정기 휴장일입니다. {facility.closure.matched_rules.map(rule => rule.note).join(' / ')}</p>
                      {facility.closure.source_url && <a href={facility.closure.source_url} target="_blank" rel="noopener noreferrer">휴장 규정 출처</a>}
                    </div>
                  )}
                  {facility.closure?.status === 'needs_calendar_resolution' && (
                    <p>명절 휴장 여부는 공식 예약 안내에서 확인해 주세요.</p>
                  )}
                  {!facility.closure?.is_closed && facility.time_check?.status === 'not_eligible' && (
                    <p>희망 시간이 시설의 이용시간 규정과 맞지 않습니다. 시간을 다시 확인해 주세요.</p>
                  )}

                  {facility.slot_status === 'rule_conflict' && (
                    <p className="error-message">적용 기간이 겹치는 규정이 있습니다. 공식 안내를 확인해 주세요.</p>
                  )}
                  <label className="facility-check">
                    <input
                      type="checkbox"
                      checked={selected}
                      disabled={facility.closure?.is_closed === true || facility.slot_status === 'rule_conflict'}
                      onChange={() => onToggle(facility.id)}
                    />
                    비교 대상에 포함
                  </label>

                  {selected && (
                    <div className="field">
                      <label htmlFor={`time-${facility.id}`}>
                        이용시간 선택
                      </label>

                      {facility.time_options?.selection === 'flexible' ? (
                        <div>
                          <input aria-label="시설 이용 시작시간" type="time" value={selectedTime.split('|')[0] || ''}
                            onChange={event => onTimeChange(facility.id, `${event.target.value}|${selectedTime.split('|')[1] || ''}`)} />
                          <input aria-label="시설 이용 종료시간" type="time" value={selectedTime.split('|')[1] || ''}
                            onChange={event => onTimeChange(facility.id, `${selectedTime.split('|')[0] || ''}|${event.target.value}`)} />
                          <p>운영시간과 이용시간 제한을 확인한 뒤 비교해 주세요.</p>
                        </div>
                      ) : slots.length > 0 ? (
                        <select
                          id={`time-${facility.id}`}
                          value={selectedTime}
                          onChange={(e) =>
                            onTimeChange(facility.id, e.target.value)
                          }
                        >
                          <option value="">이용시간을 선택하세요</option>

                          {slots.map(([start, end]) => {
                            const value = `${start}|${end}`

                            return (
                              <option key={value} value={value}>
                                {start} ~ {end}
                              </option>
                            )
                          })}
                        </select>
                      ) : (
                        <p className="error-message">
                          {facility.slot_status === 'rule_conflict'
                            ? '적용 기간이 겹치는 규정이 있습니다. 공식 안내를 확인해 주세요.'
                            : ['no_slots', 'rule_missing', 'rule_not_in_effect'].includes(facility.slot_status)
                            ? '선택한 날짜에 적용되는 예약 회차 정보가 없습니다.'
                            : facilitySlots[facility.id]?.message || '예약 회차 정보 확인이 필요합니다.'}
                        </p>
                      )}
                    </div>
                  )}

                  {facility.bookingUrl ? (
                    <a
                      className="facility-booking-link"
                      href={facility.bookingUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      공식 예약 사이트 이동 ↗
                    </a>
                  ) : (
                    <p>공식 예약 링크 확인 필요</p>
                  )}
                </article>
              )
            })}
          </div>

          {error && <p className="error-message">{error}</p>}

          <button
            className="search-button"
            onClick={onCompare}
            disabled={loading || selectedIds.length === 0}
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
