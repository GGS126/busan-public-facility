import { useState } from 'react'
import { parseNaturalLanguage } from '../api/compare'

function getToday() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

function normalizeTime(value) {
  if (typeof value !== 'string') {
    return ''
  }

  const match = /^(\d{1,2}):(\d{2})$/.exec(value)

  if (!match) {
    return ''
  }

  const hour = Number(match[1])
  const minute = Number(match[2])

  if (
    hour < 0 ||
    hour > 24 ||
    minute < 0 ||
    minute > 59 ||
    (hour === 24 && minute !== 0)
  ) {
    return ''
  }

  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

function getInitialConditions() {
  return {
    sport: '',
    districts: null,
    date: '',
    start_time: '',
    end_time: '',
    headcount: '',
    discount_types: null,
  }
}

function NaturalLanguageInput({
  onApply,
  onDirectInput,
  options,
  optionsLoading = false,
  optionsError = '',
}) {
  const [sentence, setSentence] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [analysisStatus, setAnalysisStatus] = useState('')
  const [missingFields, setMissingFields] = useState([])
  const [questions, setQuestions] = useState({})
  const [conditions, setConditions] = useState(
    getInitialConditions
  )

  const sports = Array.isArray(options?.sports)
    ? options.sports
    : []

  const districts = Array.isArray(options?.districts)
    ? options.districts
    : []

  const discounts = Array.isArray(options?.discount_types)
    ? options.discount_types
    : []

  const unavailable =
    optionsLoading ||
    Boolean(optionsError) ||
    sports.length === 0

  function getDiscountLabel(code) {
    return (
      discounts.find((item) => item.code === code)?.label ??
      code
    )
  }

  function updateCondition(key, value) {
    setConditions((previous) => ({
      ...previous,
      [key]: value,
    }))

    setMessage('')

    setMissingFields((previous) =>
      previous.filter((field) => field !== key)
    )
  }

  function handleSentenceChange(event) {
    setSentence(event.target.value)
    setMessage('')
    setShowConfirm(false)
    setAnalysisStatus('')
    setMissingFields([])
    setQuestions({})
  }

  async function handleAnalyze() {
    const query = sentence.trim()

    if (!query) {
      setMessage('이용 조건을 문장으로 입력해 주세요.')
      setShowConfirm(false)
      return
    }

    if (query.length > 500) {
      setMessage('이용 조건은 500자 이내로 입력해 주세요.')
      setShowConfirm(false)
      return
    }

    if (unavailable) {
      setMessage('이용조건 선택지를 먼저 불러와 주세요.')
      setShowConfirm(false)
      return
    }

    if (loading) {
      return
    }

    setLoading(true)
    setMessage('')
    setShowConfirm(false)
    setAnalysisStatus('')
    setMissingFields([])
    setQuestions({})

    try {
      const response = await parseNaturalLanguage(query)

      if (
        !response ||
        typeof response !== 'object' ||
        !['ok', 'need_more', 'llm_failed'].includes(
          response.status
        )
      ) {
        throw new Error(
          '자연어 분석 결과의 응답 형식이 올바르지 않습니다.'
        )
      }

      setAnalysisStatus(response.status)

      if (response.status === 'llm_failed') {
        setMessage(
          response.message ||
            'AI가 이용 조건을 분석하지 못했습니다. 다시 입력하거나 직접 입력으로 진행해 주세요.'
        )

        return
      }

      const parsed =
        response.conditions &&
        typeof response.conditions === 'object' &&
        !Array.isArray(response.conditions)
          ? response.conditions
          : {}

      const requestedSport =
        typeof parsed.sport === 'string'
          ? parsed.sport
          : ''

      const sportExists = sports.some(
        (item) => item.code === requestedSport
      )

      const nextSport = sportExists
        ? requestedSport
        : ''

      const requestedDistricts = Array.isArray(
        parsed.districts
      )
        ? [...new Set(parsed.districts)]
        : null

      const validDistricts =
        requestedDistricts === null
          ? null
          : requestedDistricts.filter(
              (district) => districts.includes(district)
            )

      const nextDate =
        typeof parsed.date === 'string'
          ? parsed.date
          : ''

      const normalizedStartTime = normalizeTime(
        parsed.start_time
      )

      const nextStartTime =
        normalizedStartTime === '24:00'
          ? ''
          : normalizedStartTime

      const nextEndTime = normalizeTime(
        parsed.end_time
      )

      const nextHeadcount =
        Number.isInteger(parsed.headcount) &&
        parsed.headcount >= 1
          ? String(parsed.headcount)
          : ''

      const requestedDiscounts = Array.isArray(
        parsed.discount_types
      )
        ? [...new Set(parsed.discount_types)]
        : null

      const validDiscounts =
        requestedDiscounts === null
          ? null
          : requestedDiscounts.filter(
              (code) =>
                discounts.some(
                  (item) => item.code === code
                )
            )

      const missing = Array.isArray(
        response.missing_fields
      )
        ? response.missing_fields.filter(
            (field) => typeof field === 'string'
          )
        : []

      const responseQuestions =
        response.questions &&
        typeof response.questions === 'object' &&
        !Array.isArray(response.questions)
          ? response.questions
          : {}

      const notices = []

      let nextDistricts = validDistricts
      let nextDiscounts = validDiscounts

      if (!sportExists && requestedSport) {
        notices.push(
          '분석된 종목이 현재 선택지에 없습니다. 종목을 다시 선택해 주세요.'
        )
      }

      if (
        requestedDistricts !== null &&
        validDistricts.length !== requestedDistricts.length
      ) {
        notices.push(
          '일부 분석된 지역이 현재 선택지에 없습니다. 이용 지역을 다시 확인해 주세요.'
        )

        if (validDistricts.length === 0) {
          nextDistricts = null
        }
      }

      if (
        requestedDiscounts !== null &&
        validDiscounts.length !== requestedDiscounts.length
      ) {
        notices.push(
          '일부 감면 유형을 선택할 수 없습니다. 감면 조건을 다시 확인해 주세요.'
        )

        if (validDiscounts.length === 0) {
          nextDiscounts = null
        }
      }

      if (missing.includes('districts')) {
        nextDistricts = null
      }

      if (missing.includes('discount_types')) {
        nextDiscounts = null
      }

      setConditions({
        sport: nextSport,
        districts: nextDistricts,
        date: nextDate,
        start_time: nextStartTime,
        end_time: nextEndTime,
        headcount: nextHeadcount,
        discount_types: nextDiscounts,
      })

      setMissingFields(missing)
      setQuestions(responseQuestions)

      if (response.status === 'need_more') {
        notices.unshift(
          '일부 이용 조건이 부족합니다. 아래 항목을 확인하고 수정해 주세요.'
        )
      } else {
        notices.unshift(
          'AI 분석이 완료되었습니다. 추출된 조건을 확인해 주세요.'
        )
      }

      if (
        typeof response.message === 'string' &&
        response.message.trim()
      ) {
        notices.push(response.message)
      }

      setMessage(notices.join('\n'))
      setShowConfirm(true)
    } catch (error) {
      setAnalysisStatus('llm_failed')

      setMessage(
        error.message ||
          '자연어 분석 중 오류가 발생했습니다. 직접 입력으로 진행해 주세요.'
      )

      setShowConfirm(false)
    } finally {
      setLoading(false)
    }
  }

  function handleApply() {
    const sport = sports.find(
      (item) => item.code === conditions.sport
    )

    if (!sport) {
      setMessage('이용 종목을 선택해 주세요.')
      return
    }

    if (
      !Array.isArray(conditions.districts) ||
      conditions.districts.some(
        (district) => !districts.includes(district)
      )
    ) {
      setMessage('이용 지역을 선택해 주세요.')
      return
    }

    if (!conditions.date) {
      setMessage('이용 날짜를 선택해 주세요.')
      return
    }

    if (conditions.date < getToday()) {
      setMessage('지난 날짜는 선택할 수 없습니다.')
      return
    }

    const startTime = normalizeTime(
      conditions.start_time
    )

    const endTime = normalizeTime(
      conditions.end_time
    )

    if (
      !startTime ||
      startTime === '24:00' ||
      !endTime ||
      startTime >= endTime
    ) {
      setMessage(
        '시작 시간과 종료 시간을 확인해 주세요.'
      )
      return
    }

    const count = Number(conditions.headcount)

    if (!Number.isInteger(count) || count < 1) {
      setMessage(
        '이용 인원은 1명 이상의 정수로 입력해 주세요.'
      )
      return
    }

    if (
      !Array.isArray(conditions.discount_types) ||
      conditions.discount_types.some(
        (code) =>
          !discounts.some((item) => item.code === code)
      )
    ) {
      setMessage(
        '감면 조건을 확인해 주세요. 감면 없음도 직접 선택할 수 있습니다.'
      )
      return
    }

    onApply({
      sport: conditions.sport,
      sportLabel: sport.label,
      districts: conditions.districts,
      date: conditions.date,
      start_time: startTime,
      end_time: endTime,
      headcount: count,
      discount_types: conditions.discount_types,
      source: 'llm',
    })

    setMessage('')
    setShowConfirm(false)
  }

  function handleDirect() {
    setMessage('')
    setShowConfirm(false)
    onDirectInput()
  }

  const districtValue =
    conditions.districts === null
      ? ''
      : conditions.districts.length > 1
        ? 'multiple'
        : conditions.districts[0] ?? '전체'

  const discountValue =
    conditions.discount_types === null
      ? ''
      : conditions.discount_types.length > 1
        ? 'multiple'
        : conditions.discount_types[0] ?? 'none'

  return (
    <section
      className="search-card"
      id="natural-language"
    >
      <div className="section-heading">
        <span className="section-number">AI</span>

        <div>
          <h2>자연어로 이용 조건 입력</h2>

          <p>
            원하는 이용 조건을 문장으로 입력하고,
            추출된 조건을 확인하세요.
          </p>
        </div>
      </div>

      <div className="field">
        <label htmlFor="natural-input">
          이용 조건 문장
        </label>

        <textarea
          id="natural-input"
          rows={4}
          maxLength={500}
          value={sentence}
          placeholder="예: 내일 해운대구에서 오후 7시부터 9시까지 테니스를 4명이 이용하고 싶어요."
          onChange={handleSentenceChange}
          disabled={loading}
          style={{
            width: '100%',
            padding: '14px',
            border: '1px solid #cbd5e1',
            borderRadius: '9px',
            fontFamily: 'inherit',
            fontSize: '14px',
            resize: 'vertical',
            boxSizing: 'border-box',
          }}
        />

        <small>
          {sentence.length} / 500자
        </small>
      </div>

      {optionsLoading && (
        <p role="status">
          이용조건 선택지를 불러오는 중입니다.
        </p>
      )}

      {optionsError && (
        <p className="error-message" role="alert">
          이용조건 선택지를 불러오지 못했습니다.{' '}
          {optionsError}
        </p>
      )}

      <button
        type="button"
        className="search-button"
        onClick={handleAnalyze}
        disabled={loading || unavailable}
      >
        {loading
          ? 'AI 분석 중...'
          : '입력 조건 확인하기'}
      </button>

      {message && (
        <p
          className={
            analysisStatus === 'llm_failed'
              ? 'error-message'
              : 'result-disclaimer'
          }
          role="status"
          style={{ whiteSpace: 'pre-line' }}
        >
          {message}
        </p>
      )}

      {showConfirm && (
        <div className="result-details">
          <h3>조건 확인 및 수정</h3>

          <p>
            AI가 추출한 이용 조건입니다.
            실제 이용 조건과 일치하는지 확인하고
            필요한 항목을 수정해 주세요.
          </p>

          {analysisStatus === 'need_more' &&
            missingFields.length > 0 && (
              <div
                className="result-disclaimer"
                role="status"
              >
                <strong>
                  추가 확인이 필요한 항목
                </strong>

                <ul>
                  {missingFields.map((field) => (
                    <li key={field}>
                      {questions[field] ||
                        `${field} 항목을 확인해 주세요.`}
                    </li>
                  ))}
                </ul>
              </div>
            )}

          {conditions.discount_types?.length > 0 && (
            <p>
              추출된 감면 유형은{' '}
              {conditions.discount_types
                .map(getDiscountLabel)
                .join(', ')}
              입니다. 이용 조건 입력 화면에서 감면
              대상 인원과 대표자 해당 여부를 확인해 주세요.
            </p>
          )}

          <div className="search-fields">
            <div className="field">
              <label htmlFor="ai-sport">
                이용 종목
              </label>

              <select
                id="ai-sport"
                value={conditions.sport}
                onChange={(event) =>
                  updateCondition(
                    'sport',
                    event.target.value
                  )
                }
              >
                <option value="">
                  종목 선택
                </option>

                {sports.map((item) => (
                  <option
                    key={item.code}
                    value={item.code}
                  >
                    {item.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="ai-district">
                이용 지역
              </label>

              <select
                id="ai-district"
                value={districtValue}
                onChange={(event) => {
                  const value = event.target.value

                  if (value === 'multiple') {
                    return
                  }

                  updateCondition(
                    'districts',
                    value === '전체'
                      ? []
                      : value
                        ? [value]
                        : null
                  )
                }}
              >
                <option value="">
                  지역 선택
                </option>

                <option value="전체">
                  부산 전체
                </option>

                {conditions.districts?.length > 1 && (
                  <option value="multiple">
                    {conditions.districts.join(', ')}
                  </option>
                )}

                {districts.map((district) => (
                  <option
                    key={district}
                    value={district}
                  >
                    {district}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="ai-date">
                이용 날짜
              </label>

              <input
                id="ai-date"
                type="date"
                min={getToday()}
                value={conditions.date}
                onChange={(event) =>
                  updateCondition(
                    'date',
                    event.target.value
                  )
                }
              />
            </div>

            <div className="field">
              <label htmlFor="ai-start">
                시작 시간
              </label>

              <input
                id="ai-start"
                type="time"
                value={conditions.start_time}
                onChange={(event) =>
                  updateCondition(
                    'start_time',
                    event.target.value
                  )
                }
              />
            </div>

            <div className="field">
              <label htmlFor="ai-end">
                종료 시간
              </label>

              <input
                id="ai-end"
                type="text"
                placeholder="HH:MM"
                maxLength={5}
                value={conditions.end_time}
                onChange={(event) =>
                  updateCondition(
                    'end_time',
                    event.target.value
                  )
                }
              />

              <small>
                예: 21:30 또는 24:00
              </small>
            </div>

            <div className="field">
              <label htmlFor="ai-headcount">
                전체 이용 인원
              </label>

              <input
                id="ai-headcount"
                type="number"
                min="1"
                step="1"
                value={conditions.headcount}
                onChange={(event) =>
                  updateCondition(
                    'headcount',
                    event.target.value
                  )
                }
              />
            </div>

            <div className="field">
              <label htmlFor="ai-discount">
                감면 유형
              </label>

              <select
                id="ai-discount"
                value={discountValue}
                onChange={(event) => {
                  const value = event.target.value

                  if (value === 'multiple') {
                    return
                  }

                  updateCondition(
                    'discount_types',
                    value === 'none'
                      ? []
                      : value
                        ? [value]
                        : null
                  )
                }}
              >
                <option value="">
                  감면 조건 선택
                </option>

                <option value="none">
                  감면 없음
                </option>

                {conditions.discount_types?.length > 1 && (
                  <option value="multiple">
                    {conditions.discount_types
                      .map(getDiscountLabel)
                      .join(', ')}
                  </option>
                )}

                {discounts
                  .filter(
                    (item) => item.code !== 'none'
                  )
                  .map((item) => (
                    <option
                      key={item.code}
                      value={item.code}
                    >
                      {item.label}
                    </option>
                  ))}
              </select>

              <small>
                감면 대상 인원과 대표자 해당 여부는
                이용 조건 입력 화면에서 설정할 수 있습니다.
              </small>
            </div>
          </div>

          <button
            type="button"
            className="search-button"
            onClick={handleApply}
          >
            확인한 조건으로 검색 준비
          </button>
        </div>
      )}

      <button
        type="button"
        onClick={handleDirect}
        disabled={loading}
        style={{
          marginTop: '18px',
          padding: '10px 0',
          background: 'transparent',
          border: 'none',
          color: '#2563eb',
          cursor: 'pointer',
          fontWeight: '700',
        }}
      >
        직접 입력으로 진행하기 →
      </button>
    </section>
  )
}

export default NaturalLanguageInput