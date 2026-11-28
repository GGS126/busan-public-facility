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

// 취소 및 미이용 사유 표시
function getCancellationLabel(reason) {
  const labels = {
    user_cancel: '사용자 취소',
    rain_same_day: '당일 우천',
    rain_unused: '우천으로 미이용',
    force_majeure_or_city_event: '천재지변·부산시 행사',
  }

  return labels[reason] || '확인 필요'
}

// 이용일 기준 취소 시점 표시
function formatDaysBefore(value) {
  if (!Number.isInteger(value) || value < 0) {
    return '확인 필요'
  }

  return value === 0
    ? '이용 당일 취소'
    : `이용일 ${value}일 전 취소`
}

function getFacility(result, facilities) {
  return facilities.find(
    (item) =>
      item.id === result.facility_id ||
      item.facility_id === result.facility_id
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

function hasValidAmount(value) {
  return typeof value === 'number' && Number.isFinite(value)
}

// 환불 규정과 관련된 출처 조회
function getRefundSources(refund, sources) {
  if (!refund || !Array.isArray(sources)) {
    return []
  }

  const sourceIds = new Set()

  if (refund.source_id) {
    sourceIds.add(refund.source_id)
  }

  if (Array.isArray(refund.review_items)) {
    refund.review_items.forEach((item) => {
      if (item?.source_id) {
        sourceIds.add(item.source_id)
      }
    })
  }

  return sources.filter(
    (source) => sourceIds.has(source.source_id)
  )
}

function FeeAmountRow({ label, amount, className = '' }) {
  return (
    <div className={`fee-row ${className}`.trim()}>
      <span>{label}</span>
      <strong>{formatWon(amount)}</strong>
    </div>
  )
}

function ReviewItems({ items, title = '추가 확인사항' }) {
  if (!Array.isArray(items) || items.length === 0) {
    return null
  }

  return (
    <div className="review-box">
      <h4>{title}</h4>

      <ul>
        {items.map((item, index) => (
          <li key={index}>
            {getItemText(item)}
          </li>
        ))}
      </ul>
    </div>
  )
}

// 취소 및 미이용 예상 환불 결과
function CancelRefundResult({
  refund,
  sources = [],
}) {
  if (!refund || typeof refund !== 'object') {
    return null
  }

  const calculated =
    refund.status === 'calculated'

  const needsReview =
    refund.status === 'needs_review'

  const hasRefundRate =
    typeof refund.rate_percent === 'number' &&
    Number.isFinite(refund.rate_percent) &&
    refund.rate_percent >= 0 &&
    refund.rate_percent <= 100

  // 백엔드에서 확정한 금액만 표시
  const hasCalculatedAmounts =
    calculated &&
    hasValidAmount(refund.refund_amount) &&
    hasValidAmount(refund.cost_after_refund)

  const reviewItems =
    Array.isArray(refund.review_items)
      ? refund.review_items
      : []

  const refundSources =
    getRefundSources(refund, sources)

  const statusLabel = hasCalculatedAmounts
    ? '계산 완료'
    : '확인 필요'

  return (
    <div className="result-details cancel-refund-section">
      <div className="cancel-refund-heading">
        <h4>취소·미이용 예상 환불</h4>

        <span
          className={
            hasCalculatedAmounts
              ? 'refund-status refund-calculated'
              : 'refund-status refund-needs-review'
          }
        >
          {statusLabel}
        </span>
      </div>

      <p className="refund-description">
        예약 후 취소하거나 이용하지 못하는 경우의
        예상 환불 정보입니다.
        감면에 따른 환급액과는 별개입니다.
      </p>

      <div className="refund-summary">
        <div className="fee-row">
          <span>취소 및 미이용 사유</span>

          <strong>
            {getCancellationLabel(refund.reason)}
          </strong>
        </div>

        {refund.reason === 'user_cancel' && (
          <div className="fee-row">
            <span>취소 시점</span>

            <strong>
              {formatDaysBefore(refund.days_before)}
            </strong>
          </div>
        )}

        <div className="fee-row">
          <span>규정상 환불률</span>

          <strong>
            {hasRefundRate
              ? `${refund.rate_percent}%`
              : '확인 필요'}
          </strong>
        </div>
      </div>

      {hasCalculatedAmounts ? (
        <div className="refund-amount-box">
          <FeeAmountRow
            label="예상 취소 환불액"
            amount={refund.refund_amount}
            className="refund-amount"
          />

          <FeeAmountRow
            label="취소 환불 후 예상 부담액"
            amount={refund.cost_after_refund}
            className="final-price"
          />

          <small>
            온라인 선결제 예상액을 기준으로
            계산된 환불 정보입니다.
          </small>
        </div>
      ) : (
        <div className="review-box refund-review-box">
          <h4>환불 금액 확인 필요</h4>

          {needsReview ? (
            <p>
              현재 이용조건에서는 실제 환불 금액을
              확정할 수 없습니다.
              환불 규정과 추가 확인사항을 참고해 주세요.
            </p>
          ) : calculated ? (
            <p>
              서버에서 반환한 환불 금액 정보가
              올바르지 않습니다.
              공식 안내를 확인해 주세요.
            </p>
          ) : (
            <p>
              서버에서 반환한 환불 상태를
              확인할 수 없습니다.
              공식 안내를 확인해 주세요.
            </p>
          )}

          <div className="fee-row">
            <span>예상 취소 환불액</span>
            <strong>확인 필요</strong>
          </div>

          <div className="fee-row">
            <span>취소 환불 후 예상 부담액</span>
            <strong>확인 필요</strong>
          </div>
        </div>
      )}

      {/* 환불 규정 및 신청 방법 */}
      {typeof refund.note === 'string' &&
        refund.note.trim() && (
          <div className="refund-note">
            <h4>환불 규정 및 신청 방법</h4>

            <p>{refund.note}</p>
          </div>
        )}

      {/* 환불 금액을 확정하지 못한 이유 */}
      <ReviewItems
        items={reviewItems}
        title="환불 추가 확인사항"
      />

      {!hasCalculatedAmounts &&
        reviewItems.length === 0 && (
          <p>
            환불에 필요한 세부 조건은
            해당 시설의 공식 안내를 확인해 주세요.
          </p>
        )}

      {/* 취소 및 미이용 환불 규정의 자료 출처 */}
      <div className="refund-sources">
        <h4>환불 규정 출처</h4>

        {refundSources.length > 0 ? (
          refundSources.map((source, index) => (
            <div
              key={`${source.source_id || 'refund-source'}-${index}`}
            >
              {isTestSource(source) ? (
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
                    환불 규정 공식 자료 확인 ↗
                  </a>
                </p>
              ) : (
                <p>환불 규정 출처 링크 확인 필요</p>
              )}

              <p>
                자료 확인일:{' '}

                {displayText(source.checked_at)}
              </p>
            </div>
          ))
        ) : (
          <p>
            환불 규정의 상세 출처를 확인할 수 없습니다.
            시설의 공식 안내를 확인해 주세요.
          </p>
        )}
      </div>

      <small className="refund-disclaimer">
        예상 환불 정보는 실제 예약 취소 또는
        환불 신청 결과를 보장하지 않습니다.
      </small>
    </div>
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

            const calculated =
              fee.status === 'calculated'

            const needsReview =
              fee.status === 'needs_review'

            const notEligible =
              fee.status === 'not_eligible'

            const feeItems = Array.isArray(fee.items)
              ? fee.items
              : []

            const reviewItems = Array.isArray(fee.review_items)
              ? fee.review_items
              : []

            // 상세 환불 규정 목록
            const refundNotes =
              Array.isArray(result.terms?.refund_notes)
                ? result.terms.refund_notes.filter(
                    (note) =>
                      typeof note === 'string' &&
                      note.trim()
                  )
                : []

            const facility = getFacility(result, facilities)

            const isTestData =
              facility?.isTestData === true ||
              result.facility_id === 'F001'

            const bookingUrl =
              !isTestData
                ? facility?.bookingUrl ||
                  facility?.booking_url ||
                  null
                : null

            // 결제 방식이 확인되지 않은 금액이 있는지 확인
            const hasUnverifiedPayment =
              hasValidAmount(fee.payment_unverified) &&
              fee.payment_unverified > 0

            const hasPaymentBreakdown =
              hasValidAmount(fee.online_prepay) ||
              hasValidAmount(fee.onsite_payment) ||
              hasValidAmount(fee.payment_unverified)

            const hasAnyFeeAmount =
              feeItems.some((item) =>
                hasValidAmount(item.amount)
              ) ||
              hasValidAmount(fee.total) ||
              hasValidAmount(fee.payment_due) ||
              hasValidAmount(fee.online_prepay) ||
              hasValidAmount(fee.onsite_payment) ||
              hasValidAmount(fee.payment_unverified) ||
              hasValidAmount(fee.expected_refund) ||
              hasValidAmount(fee.net_cost_after_refund)

            const statusLabel = calculated
              ? '계산 완료'
              : notEligible
                ? '이용조건 불충족'
                : '확인 필요'

            return (
              <article
                className="comparison-card"
                key={result.facility_id}
              >
                <div className="comparison-header">
                  <span className="result-tag">
                    {statusLabel}
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

                  {notEligible && (
                    <div className="review-box">
                      <h4>이용조건 불충족</h4>

                      <p>
                        선택한 이용조건으로는 해당 시설을
                        이용할 수 없거나 이용 가능 여부를
                        확인해야 합니다.
                      </p>
                    </div>
                  )}

                  {needsReview && (
                    <div className="review-box">
                      <h4>요금 확인 필요</h4>

                      <p>
                        일부 요금이나 결제 조건을 확정할 수
                        없습니다. 확인된 금액이 있다면
                        아래에 표시합니다.
                      </p>
                    </div>
                  )}

                  {feeItems.length > 0 ? (
                    <div className="fee-list">
                      {feeItems.map((item, index) => (
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
                  ) : (
                    <p>
                      {hasAnyFeeAmount
                        ? '세부 요금 항목은 확인되지 않았습니다.'
                        : '확인된 요금 항목이 없습니다.'}
                    </p>
                  )}

                  {hasAnyFeeAmount && (
                    <div className="fee-total">
                      <FeeAmountRow
                        label="예상 총 이용요금"
                        amount={fee.total}
                      />

                      {/* 결제 방식 미확인 금액이 있으면
                          최초 결제 예상액을 표시하지 않음 */}
                      {!hasUnverifiedPayment && (
                        <FeeAmountRow
                          label="최초 결제 예상액"
                          amount={fee.payment_due}
                        />
                      )}

                      {/* 감면 환급과 취소 환불 구분 */}
                      <FeeAmountRow
                        label="예상 감면 환급액"
                        amount={fee.expected_refund}
                      />

                      <FeeAmountRow
                        label="감면 적용 후 예상 부담액"
                        amount={fee.net_cost_after_refund}
                        className="final-price"
                      />
                    </div>
                  )}

                  {/* 결제 방식별 금액 */}
                  {hasPaymentBreakdown && (
                    <div className="result-details">
                      <h4>결제 방식별 금액</h4>

                      <FeeAmountRow
                        label="온라인 선결제 예상액"
                        amount={fee.online_prepay}
                      />

                      <FeeAmountRow
                        label="현장 결제 예상액"
                        amount={fee.onsite_payment}
                      />

                      <FeeAmountRow
                        label="결제 방식 미확인 금액"
                        amount={fee.payment_unverified}
                      />

                      {hasUnverifiedPayment && (
                        <div className="review-box">
                          <h4>결제 방식 확인 필요</h4>

                          <p>
                            일부 요금의 결제 방식이
                            확인되지 않아 최초 결제 예상액을
                            확정할 수 없습니다.
                            확인된 온라인 선결제액과
                            현장 결제액을 참고해 주세요.
                          </p>
                        </div>
                      )}

                      <p>
                        결제 방식별 금액은 백엔드에서
                        확인된 규정을 기준으로 표시합니다.
                        확인되지 않은 항목은 별도로
                        확인해야 합니다.
                      </p>
                    </div>
                  )}

                  {!calculated &&
                    !needsReview &&
                    !notEligible && (
                      <div className="review-box">
                        <h4>요금 상태 확인 필요</h4>

                        <p>
                          서버에서 반환한 요금 상태를
                          확인할 수 없습니다.
                        </p>
                      </div>
                    )}

                  <ReviewItems
                    items={reviewItems}
                    title="요금 및 이용조건 추가 확인사항"
                  />

                  {needsReview &&
                    reviewItems.length === 0 && (
                      <p>
                        추가 확인이 필요한 항목이
                        있습니다. 공식 안내를 확인해
                        주세요.
                      </p>
                    )}
                </div>

                {/* 취소 및 미이용 예상 환불 */}
                <CancelRefundResult
                  refund={result.cancel_refund}
                  sources={result.sources}
                />

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

                  {/* 취소 조건 미선택 시에도 상세 규정 표시 */}
                  <div className="refund-rules">
                    <h4>상세 환불 규정</h4>

                    {refundNotes.length > 0 ? (
                      <ul className="refund-notes-list">
                        {refundNotes.map((note, index) => (
                          <li key={index}>
                            {note}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p>
                        상세 환불 규정은
                        시설의 공식 안내를 확인해 주세요.
                      </p>
                    )}
                  </div>
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

                  <ReviewItems
                    items={result.checklist_review_items}
                    title="준비사항 추가 확인사항"
                  />
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
        실제 예약 가능 여부와 최종 요금 및 환불 금액은
        각 시설의 공식 안내에서 확인해야 합니다.
        테스트용 시설의 정보는 실제 예약에
        사용할 수 없습니다.
      </p>
    </section>
  )
}

export default FeeResult