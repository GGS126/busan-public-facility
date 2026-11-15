
function formatWon(value) {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${value.toLocaleString('ko-KR')}원`
    : '확인 필요'
}

function displayText(value) {
  if (typeof value === 'string' && value.trim()) {
    return value
  }

  if (typeof value === 'number') {
    return String(value)
  }

  return '확인 필요'
}

function getItemText(item) {
  if (typeof item === 'string') {
    return item
  }

  if (!item || typeof item !== 'object') {
    return '확인 필요'
  }

  return (
    item.description ||
    item.label ||
    item.reason ||
    item.message ||
    item.name ||
    '확인 필요'
  )
}

function getFeeLabel(type) {
  const labels = {
    base: '기본 이용요금',
    lighting: '조명료',
    discount: '감면액',
    additional: '추가 요금',
  }

  return labels[type] || type || '기타 요금'
}

function getFacility(result, facilities) {
  return facilities.find(
    (item) => item.id === result.facility_id
  )
}

function isExampleUrl(url) {
  if (typeof url !== 'string' || !url.trim()) {
    return false
  }

  try {
    const hostname = new URL(url).hostname.toLowerCase()

    return (
      hostname === 'example.com' ||
      hostname.endsWith('.example.com')
    )
  } catch {
    return false
  }
}

function isTestSource(source) {
  return (
    source?.license === '가상 데이터' ||
    isExampleUrl(source?.url)
  )
}

function FeeResult({ results, facilities = [] }) {
  return (
    <section className="result-section" id="results">
      <div className="section-heading">
        <span className="section-number">03</span>

        <div>
          <h2>시설 비교 결과</h2>
          <p>
            시설별 이용시간, 예상요금, 예약·취소 조건과
            준비사항을 확인하세요.
          </p>
        </div>
      </div>

      {results.length === 0 ? (
        <div className="result-empty">
          <div className="result-empty-icon">₩</div>
          <h3>아직 조회된 결과가 없습니다</h3>
          <p>
            시설을 검색하고 비교할 대상을 선택해 주세요.
          </p>
        </div>
      ) : (
        <div className="comparison-grid">
          {results.map((result) => {
            const fee = result.fee || {}
            const calculated = fee.status === 'calculated'

            const facility = getFacility(result, facilities)

            const isTestData =
              facility?.isTestData === true ||
              result.facility_id === 'F001'

            const bookingUrl =
              !isTestData ? facility?.bookingUrl : null

            return (
              <article
                className="comparison-card"
                key={result.facility_id}
              >
                <div className="comparison-header">
                  <span className="result-tag">
                    {calculated ? '계산 완료' : '확인 필요'}
                  </span>

                  <h3>
                    {displayText(result.facility_name)}
                  </h3>
                </div>

                {isTestData && (
                  <div
                    className="review-box"
                    style={{ marginTop: '12px' }}
                  >
                    <strong>
                      백엔드 연동 테스트용 가상 시설
                    </strong>

                    <p>
                      이 시설의 요금과 예약 규정은
                      실제 부산 공공체육시설 정보가
                      아닌 테스트 데이터입니다.
                    </p>
                  </div>
                )}

                {/* 선택한 이용조건 */}
                <div className="result-details">
                  <h4>선택한 이용조건</h4>

                  <p>
                    이용 날짜:{' '}
                    <strong>
                      {displayText(result.selected_date)}
                    </strong>
                  </p>

                  <p>
                    이용시간:{' '}
                    <strong>
                      {displayText(
                        result.selected_start_time
                      )}
                      {' ~ '}
                      {displayText(
                        result.selected_end_time
                      )}
                    </strong>
                  </p>
                </div>

                {/* 예상요금 */}
                <div className="result-details">
                  <h4>예상요금</h4>

                  {calculated ? (
                    <>
                      <div className="fee-list">
                        {fee.items?.map((item, index) => (
                          <div
                            className="fee-row"
                            key={`${item.rule_id || item.type}-${index}`}
                          >
                            <span>
                              {getFeeLabel(item.type)}
                            </span>

                            <strong>
                              {formatWon(item.amount)}
                            </strong>
                          </div>
                        ))}
                      </div>

                      <div className="fee-total">
                        <div className="fee-row">
                          <span>최초 결제 예상액</span>
                          <strong>
                            {formatWon(fee.payment_due)}
                          </strong>
                        </div>

                        <div className="fee-row">
                          <span>예상 환급액</span>
                          <strong>
                            {formatWon(fee.expected_refund)}
                          </strong>
                        </div>

                        <div className="fee-row final-price">
                          <span>최종 예상 부담액</span>
                          <strong>
                            {formatWon(
                              fee.net_cost_after_refund
                            )}
                          </strong>
                        </div>
                      </div>

                      {fee.review_items?.length > 0 && (
                        <div className="review-box">
                          <h4>추가 확인사항</h4>

                          <ul>
                            {fee.review_items.map(
                              (item, index) => (
                                <li key={index}>
                                  {getItemText(item)}
                                </li>
                              )
                            )}
                          </ul>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="review-box">
                      <h4>요금 확인 필요</h4>

                      <p>
                        현재 조건의 요금을 확정할 수
                        없습니다.
                      </p>

                      {fee.review_items?.length ? (
                        <ul>
                          {fee.review_items.map(
                            (item, index) => (
                              <li key={index}>
                                {getItemText(item)}
                              </li>
                            )
                          )}
                        </ul>
                      ) : (
                        <p>
                          추가 확인이 필요한 항목입니다.
                        </p>
                      )}
                    </div>
                  )}
                </div>

                {/* 예약 및 환불 규정 */}
                <div className="result-details">
                  <h4>예약·취소·환불 조건</h4>

                  <p>
                    예약 시작:{' '}
                    {displayText(
                      result.terms?.booking_open
                    )}
                  </p>

                  <p>
                    취소 기한:{' '}
                    {displayText(
                      result.terms?.cancel_deadline
                    )}
                  </p>

                  <p>
                    환불 규정:{' '}
                    {displayText(result.terms?.refund)}
                  </p>
                </div>

                {/* 준비사항 */}
                <div className="result-details">
                  <h4>준비사항 및 증빙서류</h4>

                  {result.checklist?.length ? (
                    <ul>
                      {result.checklist.map(
                        (item, index) => (
                          <li key={index}>
                            {getItemText(item)}
                          </li>
                        )
                      )}
                    </ul>
                  ) : (
                    <p>
                      현재 응답에 등록된 준비사항이
                      없습니다.
                    </p>
                  )}

                  {result.checklist_review_items
                    ?.length > 0 && (
                    <>
                      <h4>추가 확인사항</h4>

                      <ul>
                        {result.checklist_review_items.map(
                          (item, index) => (
                            <li key={index}>
                              {getItemText(item)}
                            </li>
                          )
                        )}
                      </ul>
                    </>
                  )}
                </div>

                {/* 자료 출처 */}
                <div className="result-details">
                  <h4>자료 출처 및 확인일</h4>

                  {result.sources?.length ? (
                    result.sources.map(
                      (source, index) => {
                        const testSource =
                          isTestSource(source)

                        return (
                          <div
                            key={`${source.source_id || 'source'}-${index}`}
                          >
                            {testSource ? (
                              <p>
                                테스트용 가상 출처
                                {source.source_id
                                  ? ` (${source.source_id})`
                                  : ''}
                              </p>
                            ) : source.url ? (
                              <p>
                                <a
                                  href={source.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  자료 출처 확인 ↗
                                </a>
                              </p>
                            ) : (
                              <p>
                                출처 링크: 확인 필요
                              </p>
                            )}

                            <p>
                              자료 확인일:{' '}
                              {displayText(
                                source.checked_at
                              )}
                            </p>
                          </div>
                        )
                      }
                    )
                  ) : (
                    <p>
                      출처 및 확인일 정보가 아직
                      연결되지 않았습니다.
                    </p>
                  )}

                  {bookingUrl ? (
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
                </div>
              </article>
            )
          })}
        </div>
      )}

      <p className="result-disclaimer">
        본 서비스는 참고용 정보를 제공합니다.
        실제 예약 가능 여부와 최종 요금은
        각 시설의 공식 안내에서 확인해야 합니다.
        테스트용 시설의 정보는 실제 예약에
        사용할 수 없습니다.
      </p>
    </section>
  )
}

export default FeeResult
