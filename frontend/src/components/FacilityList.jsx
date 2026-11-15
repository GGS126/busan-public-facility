
import {
  facilitySlots,
  getFacilitySlots,
} from '../data/facilitySlots'

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

function FacilityList({
  facilities,
  selectedIds,
  onToggle,
  searched,
  onCompare,
  loading,
  facilityTimes,
  onTimeChange,
  date,
  error,
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
            <span>
              검색 결과 {facilities.length}곳
            </span>

            <span>
              비교 대상 {selectedIds.length}곳 선택됨
            </span>
          </div>

          <div className="facility-grid">
            {facilities.map((facility) => {
              const selected = selectedIds.includes(
                facility.id
              )

              const slots = getFacilitySlots(
                facility.id,
                date
              )

              const selectedTime =
                facilityTimes[facility.id] || ''

              const isTestData =
                facility.isTestData === true

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
                      {facility.district}
                    </span>
                  </div>

                  <div className="facility-symbol">
                    {getSportIcon(facility.sport)}
                  </div>

                  <h3>{facility.name}</h3>

                  <p>{facility.address}</p>

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
                        표시된 이용시간과 요금은 기능
                        검증을 위한 예시 데이터입니다.
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

                      {slots.length > 0 ? (
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

                          {isTestData && (
                            <p
                              style={{
                                fontSize: '13px',
                                marginTop: '8px',
                              }}
                            >
                              ※ 테스트용 시간대이며
                              실제 예약 가능 여부와
                              관계없습니다.
                            </p>
                          )}
                        </>
                      ) : (
                        <p className="error-message">
                          {facilitySlots[facility.id]
                            ?.message ||
                            '예약 회차 정보 확인이 필요합니다.'}
                        </p>
                      )}
                    </div>
                  )}

                  {facility.bookingUrl &&
                  !isTestData ? (
                    <a
                      className="facility-booking-link"
                      href={facility.bookingUrl}
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
            <p className="error-message">
              {error}
            </p>
          )}

          <button
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
