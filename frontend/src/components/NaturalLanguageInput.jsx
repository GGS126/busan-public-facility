
import { useState } from 'react'

function NaturalLanguageInput({ onApply, onDirectInput }) {
  const [sentence, setSentence] = useState('')
  const [showConfirm, setShowConfirm] = useState(false)
  const [message, setMessage] = useState('')

  const [conditions, setConditions] = useState({
    sport: 'tennis',
    district: '전체',
    date: '',
    startTime: '09:00',
    endTime: '11:00',
  })

  // AI API 연결 전에는 기본 조건을 보여주고 직접 수정하도록 안내
  function handleAnalyze() {
    if (!sentence.trim()) {
      setMessage('이용 조건을 문장으로 입력해 주세요.')
      setShowConfirm(false)
      return
    }

    setConditions({
      sport: 'tennis',
      district: '전체',
      date: '',
      startTime: '09:00',
      endTime: '11:00',
    })

    setMessage(
      '현재 AI API가 연결되지 않았습니다. 아래 조건을 직접 확인하고 수정해 주세요.'
    )
    setShowConfirm(true)
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
    if (!conditions.date) {
      setMessage('이용 날짜를 선택해 주세요.')
      return
    }

    if (
      !conditions.startTime ||
      !conditions.endTime ||
      conditions.startTime >= conditions.endTime
    ) {
      setMessage('시작 시간과 종료 시간을 확인해 주세요.')
      return
    }

    onApply(conditions)
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
      >
        입력 조건 확인하기
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
            AI 분석 결과가 아닌 기본 입력값입니다.
            실제 이용 조건에 맞게 수정해 주세요.
          </p>

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
                <option value="tennis">테니스</option>
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
                <option value="전체">부산 전체</option>
                <option value="해운대구">해운대구</option>
                <option value="사상구">사상구</option>
                <option value="서구">서구</option>
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
                value={conditions.startTime}
                onChange={(event) =>
                  updateCondition('startTime', event.target.value)
                }
              />
            </div>

            <div className="field">
              <label htmlFor="ai-end">
                종료 시간
              </label>
              <input
                id="ai-end"
                type="time"
                value={conditions.endTime}
                onChange={(event) =>
                  updateCondition('endTime', event.target.value)
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
