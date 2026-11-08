
import { useState } from 'react'
import { getSearchOptions, parseNaturalLanguage } from '../api/compare'

function NaturalLanguageInput({ onApply, onDirectInput }) {
  const [sentence, setSentence] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)
  const [message, setMessage] = useState('')

  const [conditions, setConditions] = useState(null)
  const [options, setOptions] = useState(null)
  const [loading, setLoading] = useState(false)

  async function handleAnalyze() {
    setShowConfirm(false)
    setMessage('')
    if (!sentence.trim()) {
      setMessage('이용 조건을 문장으로 입력해 주세요.')
      return
    }

    setLoading(true)
    try {
      const [catalog, result] = await Promise.all([
        getSearchOptions(),
        parseNaturalLanguage(sentence.trim()),
      ])
      if (result.status !== 'ok' && result.status !== 'need_more') {
        setMessage(result.message || '조건을 추출하지 못했습니다. 직접 입력해 주세요.')
        return
      }

      const parsed = result.conditions
      const districts = parsed.districts ?? []
      const questions = Object.values(result.questions)
      if (districts.length > 1) questions.push('검색할 지역을 한 곳 선택해 주세요.')
      setOptions(catalog)
      setConditions({
        sport: parsed.sport ?? '',
        district: districts.length === 1 ? districts[0] : districts.length === 0 ? '전체' : '',
        date: parsed.date ?? '',
        start_time: parsed.start_time ?? '',
        end_time: parsed.end_time ?? '',
        headcount: parsed.headcount,
        discount_types: parsed.discount_types ?? [],
      })
      setMessage(questions.join(' '))
      setShowConfirm(true)
    } catch {
      setMessage('조건을 불러오지 못했습니다. 잠시 후 다시 시도하거나 직접 입력해 주세요.')
    } finally {
      setLoading(false)
    }
  }

  // 확인 화면에서 조건 수정
  function updateCondition(key, value) {
    setConditions((previous) => ({
      ...previous,
      [key]: value,
    }))
  }

  // 수정한 조건을 직접 입력 폼에 전달
  function handleApply() {
    const sport = options.sports.find(({ code }) => code === conditions.sport)
    if (!sport || !conditions.district) {
      setMessage('이용 종목과 지역을 선택해 주세요.')
      return
    }
    if (!conditions.date) {
      setMessage('이용 날짜를 선택해 주세요.')
      return
    }

    if (
      !conditions.start_time ||
      !/^(?:(?:[01]\d|2[0-3]):[0-5]\d|24:00)$/.test(conditions.end_time) ||
      conditions.start_time >= conditions.end_time
    ) {
      setMessage('시작 시간과 종료 시간을 확인해 주세요.')
      return
    }

    onApply({ ...conditions, sportLabel: sport.label })
    setMessage('')
    setShowConfirm(false)
  }

  return (
    <section className="search-card" id="natural-language">
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
          disabled={loading}
          value={sentence}
          placeholder="예: 이번 주말에 해운대구에서 테니스를 2시간 이용하고 싶어요."
          onChange={(event) => {
            setSentence(event.target.value)
            setMessage('')
            setShowConfirm(false)
          }}
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
      </div>

      <button
        type="button"
        className="search-button"
        onClick={handleAnalyze}
        disabled={loading}
      >
        {loading ? '이용 조건 확인 중…' : '입력 조건 확인하기'}
      </button>

      {message && (
        <p className="result-disclaimer" role="status">
          {message}
        </p>
      )}

      {showConfirm && (
        <div className="result-details">
          <h3>조건 확인 및 수정</h3>

          <p>
            추출된 조건을 확인하고 필요한 항목을 수정해 주세요.
          </p>

          {conditions.headcount != null && <p>추출된 이용 인원은 {conditions.headcount}명입니다.</p>}
          {conditions.discount_types.length > 0 && (
            <p>추출된 감면 유형은 {conditions.discount_types.map((code) =>
              options.discount_types.find((option) => option.code === code)?.label ?? code
            ).join(', ')}입니다. 이용 조건 입력 화면에서 감면 유형과 대상 인원을 선택해 주세요.</p>
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
                  updateCondition('sport', event.target.value)
                }
              >
                <option value="">종목 선택</option>
                {options.sports.map(({ code, label }) => (
                  <option key={code} value={code}>{label}</option>
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
                  updateCondition('district', event.target.value)
                }
              >
                <option value="">지역 선택</option>
                <option value="전체">부산 전체</option>
                {options.districts.map((district) => (
                  <option key={district} value={district}>{district}</option>
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
                value={conditions.date}
                onChange={(event) =>
                  updateCondition('date', event.target.value)
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
                  updateCondition('start_time', event.target.value)
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
                value={conditions.end_time}
                onChange={(event) =>
                  updateCondition('end_time', event.target.value)
                }
              />
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
        onClick={onDirectInput}
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
