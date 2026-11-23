
import { useState } from 'react'
import { parseNaturalLanguage } from '../api/compare'

const timeOptions = Array.from({ length: 48 }, (_, index) => {
  const hour = String(Math.floor(index / 2)).padStart(2, '0')
  const minute = index % 2 === 0 ? '00' : '30'
  return `${hour}:${minute}`
})

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
    district: '전체',
    date: '',
    startTime: '',
    endTime: '',
    headcount: '1',
    discountTypes: [],
  }
}

function NaturalLanguageInput({
  onApply,
  onDirectInput,
  options = {
    sports: [],
    districts: [],
    discount_types: [],
  },
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

  const sports = Array.isArray(options.sports)
    ? options.sports
    : []

  const districts = Array.isArray(options.districts)
    ? options.districts
    : []

  const discounts = Array.isArray(options.discount_types)
    ? options.discount_types
    : []

  const unavailable =
    optionsLoading ||
    Boolean(optionsError) ||
    sports.length === 0

  function updateCondition(key, value) {
    setConditions((previous) => ({
      ...previous,
      [key]: value,
    }))

    setMessage('')

    const fieldMap = {
      startTime: 'start_time',
      endTime: 'end_time',
      district: 'districts',
      discountTypes: 'discount_types',
    }

    const backendField = fieldMap[key] || key

    setMissingFields((previous) =>
      previous.filter((field) => field !== backendField)
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
        setShowConfirm(false)
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
        ? parsed.districts
        : []

      const validDistricts = requestedDistricts.filter(
        (district) => districts.includes(district)
      )

      const nextDistrict =
        validDistricts.length > 0
          ? validDistricts[0]
          : '전체'

      const nextDate =
        typeof parsed.date === 'string'
          ? parsed.date
          : ''

      const nextStartTime = normalizeTime(
        parsed.start_time
      )

      const nextEndTime = normalizeTime(
        parsed.end_time
      )

      const nextHeadcount =
        Number.isInteger(parsed.headcount) &&
        parsed.headcount >= 1
          ? String(parsed.headcount)
          : '1'

      const requestedDiscounts = Array.isArray(
        parsed.discount_types
      )
        ? parsed.discount_types
        : []

      const validDiscounts = requestedDiscounts.filter(
        (code) =>
          discounts.some((item) => item.code === code)
      )

      setConditions({
        sport: nextSport,
        district: nextDistrict,
        date: nextDate,
        startTime: nextStartTime,
        endTime: nextEndTime,
        headcount: nextHeadcount,
        discountTypes: validDiscounts,
      })

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

      setMissingFields(missing)
      setQuestions(responseQuestions)

      const notices = []

      if (!sportExists && requestedSport) {
        notices.push(
          '분석된 종목이 현재 선택지에 없습니다. 종목을 다시 선택해 주세요.'
        )
      }

      if (
        requestedDistricts.length > 0 &&
        validDistricts.length === 0
      ) {
        notices.push(
          '분석된 지역을 선택할 수 없어 부산 전체로 설정했습니다.'
        )
      }

      if (requestedDistricts.length > 1) {
        notices.push(
          '여러 지역이 추출되었습니다. 현재 검색 화면은 한 지역만 선택할 수 있어 첫 번째 지역을 적용했습니다.'
        )
      }

      if (
        requestedDiscounts.length !==
        validDiscounts.length
      ) {
        notices.push(
          '일부 감면 유형을 선택할 수 없습니다. 감면 조건을 다시 확인해 주세요.'
        )
      }

      if (validDiscounts.length > 1) {
        notices.push(
          '여러 감면 유형이 추출되었습니다. 현재 직접 입력 화면은 감면 유형 하나만 지원하므로 적용할 감면을 선택해 주세요.'
        )
      }

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
    if (
      !conditions.sport ||
      !sports.some(
        (item) => item.code === conditions.sport
      )
    ) {
      setMessage('이용 종목을 선택해 주세요.')
      return
    }

    if (
      conditions.district !== '전체' &&
      !districts.includes(conditions.district)
    ) {
      setMessage('이용 지역을 다시 선택해 주세요.')
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

    if (
      !conditions.startTime ||
      !conditions.endTime ||
      conditions.startTime >= conditions.endTime
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

    if (conditions.discountTypes.length > 1) {
      setMessage(
        '현재 검색 화면에서는 감면 유형 하나만 선택할 수 있습니다. 적용할 감면 유형을 하나로 선택해 주세요.'
      )
      return
    }

    onApply({
      sport: conditions.sport,
      districts:
        conditions.district === '전체'
          ? []
          : [conditions.district],
      district: conditions.district,
      date: conditions.date,
      start_time: conditions.startTime,
      end_time: conditions.endTime,
      headcount: count,
      discount_types: conditions.discountTypes,
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
          className="result-disclaimer"
          role="status"
          style={{ whiteSpace: 'pre-line' }}
        >
          {message}
        </p>
      )}

      {analysisStatus === 'llm_failed' && (
        <p className="error-message" role="alert">
          자연어 분석을 완료하지 못했습니다.
          문장을 수정해 다시 시도하거나 직접 입력을 이용해 주세요.
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
                <strong>추가 확인이 필요한 항목</strong>

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
                value={conditions.district}
                onChange={(event) =>
                  updateCondition(
                    'district',
                    event.target.value
                  )
                }
              >
                <option value="전체">
                  부산 전체
                </option>

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

              <select
                id="ai-start"
                value={conditions.startTime}
                onChange={(event) =>
                  updateCondition(
                    'startTime',
                    event.target.value
                  )
                }
              >
                <option value="">
                  시작시간 선택
                </option>

                {timeOptions.map((time) => (
                  <option key={time} value={time}>
                    {time}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="ai-end">
                종료 시간
              </label>

              <select
                id="ai-end"
                value={conditions.endTime}
                onChange={(event) =>
                  updateCondition(
                    'endTime',
                    event.target.value
                  )
                }
              >
                <option value="">
                  종료시간 선택
                </option>

                {timeOptions
                  .filter(
                    (time) =>
                      !conditions.startTime ||
                      time > conditions.startTime
                  )
                  .concat('24:00')
                  .map((time) => (
                    <option
                      key={time}
                      value={time}
                    >
                      {time}
                    </option>
                  ))}
              </select>
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
                value={
                  conditions.discountTypes[0] || 'none'
                }
                onChange={(event) =>
                  updateCondition(
                    'discountTypes',
                    event.target.value === 'none'
                      ? []
                      : [event.target.value]
                  )
                }
              >
                <option value="none">
                  감면 없음
                </option>

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
                현재 직접 입력 화면에서는 감면 유형을
                하나만 선택할 수 있습니다.
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
