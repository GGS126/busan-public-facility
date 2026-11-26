// 30분 단위 이용시간 목록 생성
const timeOptions = Array.from({ length: 48 }, (_, index) => {
  const hour = String(Math.floor(index / 2)).padStart(2, '0')
  const minute = index % 2 === 0 ? '00' : '30'

  return `${hour}:${minute}`
})

function withSelectedTime(time) {
  if (!time || time === '24:00' || timeOptions.includes(time)) {
    return timeOptions
  }

  return [...timeOptions, time].sort()
}

function SearchForm({
  sport,
  setSport,
  district,
  setDistrict,
  selectedDistricts = [],
  date,
  setDate,
  startTime,
  setStartTime,
  endTime,
  setEndTime,
  people,
  setPeople,
  discountType,
  setDiscountType,
  selectedDiscounts = [],
  eligibleCount,
  setEligibleCount,
  representativeEligible,
  setRepresentativeEligible,
  discountDetails = {},
  setDiscountDetails,
  optionalLightingMinutes,
  setOptionalLightingMinutes,
  onSearch,
  loading,
  error,
  fieldErrors = {},
  clearResult,
  options,
  optionsLoading,
  optionsError,
  onRetryOptions,
}) {
  function update(setter, value) {
    setter(value)
    clearResult()
  }

  // 백엔드 필드명과 프론트엔드 필드명 매칭
  function getFieldError(...names) {
    for (const name of names) {
      if (
        typeof fieldErrors[name] === 'string' &&
        fieldErrors[name]
      ) {
        return fieldErrors[name]
      }
    }

    return ''
  }

  function fieldErrorMessage(id, ...names) {
    const message = getFieldError(...names)

    return message ? (
      <small
        id={`${id}-error`}
        className="error-message"
        role="alert"
      >
        {message}
      </small>
    ) : null
  }

  function getDiscountLabel(code) {
    return (
      options?.discount_types?.find(
        (item) => item.code === code
      )?.label ?? code
    )
  }

  function updateDiscountDetail(code, key, value) {
    if (typeof setDiscountDetails !== 'function') {
      return
    }

    setDiscountDetails((previous) => ({
      ...previous,
      [code]: {
        count: '1',
        holder: false,
        ...previous[code],
        [key]: value,
      },
    }))

    clearResult()
  }

  const sports = options?.sports ?? []
  const districts = options?.districts ?? []
  const discountOptions = options?.discount_types ?? []

  const unavailable =
    optionsLoading || Boolean(optionsError)

  const multipleDiscounts =
    discountType === 'multiple' &&
    selectedDiscounts.length > 1

  return (
    <section className="search-card" id="search">
      <div className="section-heading">
        <span className="section-number">01</span>

        <div>
          <h2>이용 조건 입력</h2>

          <p>종목, 지역, 날짜와 이용 인원을 입력하세요.</p>

          <p>
            희망 이용시간과 일치하는 시설 회차가 있으면
            자동으로 선택됩니다.
          </p>
        </div>
      </div>

      {optionsLoading && (
        <p role="status">
          이용 가능한 종목, 지역 및 감면 유형을 불러오는 중입니다.
        </p>
      )}

      {optionsError && (
        <div role="alert">
          <p className="error-message">
            이용조건 선택지를 불러오지 못했습니다.{' '}
            {optionsError}
          </p>

          <button
            type="button"
            onClick={onRetryOptions}
            disabled={optionsLoading}
          >
            다시 시도
          </button>
        </div>
      )}

      <div className="search-fields">
        <div className="field">
          <label htmlFor="sport">이용 종목</label>

          <select
            id="sport"
            value={sport}
            disabled={unavailable || sports.length === 0}
            aria-invalid={Boolean(getFieldError('sport'))}
            aria-describedby={
              getFieldError('sport')
                ? 'sport-error'
                : undefined
            }
            onChange={(e) =>
              update(setSport, e.target.value)
            }
          >
            {!sports.some(({ code }) => code === sport) && (
              <option value={sport}>
                {sport ||
                  (sports.length === 0
                    ? '선택 가능한 종목 없음'
                    : '이용 종목 선택')}
              </option>
            )}

            {sports.map((item) => (
              <option key={item.code} value={item.code}>
                {item.label}
              </option>
            ))}
          </select>

          {fieldErrorMessage('sport', 'sport')}
        </div>

        <div className="field">
          <label htmlFor="district">이용 지역</label>

          <select
            id="district"
            value={district}
            disabled={unavailable}
            aria-invalid={Boolean(
              getFieldError('district', 'districts')
            )}
            aria-describedby={
              getFieldError('district', 'districts')
                ? 'district-error'
                : undefined
            }
            onChange={(e) =>
              update(setDistrict, e.target.value)
            }
          >
            <option value="전체">부산 전체</option>

            {selectedDistricts.length > 1 && (
              <option value="multiple">
                {selectedDistricts.join(', ')}
              </option>
            )}

            {districts.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>

          {fieldErrorMessage(
            'district',
            'district',
            'districts'
          )}
        </div>

        <div className="field">
          <label htmlFor="date">이용 날짜</label>

          <input
            id="date"
            type="date"
            value={date}
            aria-invalid={Boolean(getFieldError('date'))}
            aria-describedby={
              getFieldError('date')
                ? 'date-error'
                : undefined
            }
            onChange={(e) =>
              update(setDate, e.target.value)
            }
          />

          {fieldErrorMessage('date', 'date')}
        </div>

        <div className="field">
          <label htmlFor="start-time">
            희망 시작시간
          </label>

          <select
            id="start-time"
            value={startTime}
            aria-invalid={Boolean(
              getFieldError('start_time', 'startTime')
            )}
            aria-describedby={
              getFieldError('start_time', 'startTime')
                ? 'start-time-error'
                : undefined
            }
            onChange={(e) =>
              update(setStartTime, e.target.value)
            }
          >
            <option value="">시작시간 선택</option>

            {withSelectedTime(startTime).map((time) => (
              <option key={time} value={time}>
                {time}
              </option>
            ))}
          </select>

          {fieldErrorMessage(
            'start-time',
            'start_time',
            'startTime'
          )}
        </div>

        <div className="field">
          <label htmlFor="end-time">
            희망 종료시간
          </label>

          <select
            id="end-time"
            value={endTime}
            aria-invalid={Boolean(
              getFieldError('end_time', 'endTime')
            )}
            aria-describedby={
              getFieldError('end_time', 'endTime')
                ? 'end-time-error'
                : undefined
            }
            onChange={(e) =>
              update(setEndTime, e.target.value)
            }
          >
            <option value="">종료시간 선택</option>

            {withSelectedTime(endTime)
              .filter(
                (time) => !startTime || time > startTime
              )
              .concat('24:00')
              .map((time) => (
                <option key={time} value={time}>
                  {time}
                </option>
              ))}
          </select>

          {fieldErrorMessage(
            'end-time',
            'end_time',
            'endTime'
          )}
        </div>

        <div className="field">
          <label htmlFor="people">
            전체 이용 인원
          </label>

          <input
            id="people"
            type="number"
            min="1"
            step="1"
            value={people}
            aria-invalid={Boolean(
              getFieldError('headcount', 'people')
            )}
            aria-describedby={
              getFieldError('headcount', 'people')
                ? 'people-error'
                : undefined
            }
            onChange={(e) =>
              update(setPeople, e.target.value)
            }
          />

          {fieldErrorMessage(
            'people',
            'headcount',
            'people'
          )}
        </div>

        <div className="field">
          <label htmlFor="discount">
            감면 유형
          </label>

          <select
            id="discount"
            value={discountType}
            disabled={unavailable}
            aria-invalid={Boolean(
              getFieldError(
                'discount_types',
                'discounts',
                'discount_type'
              )
            )}
            aria-describedby={
              getFieldError(
                'discount_types',
                'discounts',
                'discount_type'
              )
                ? 'discount-error'
                : undefined
            }
            onChange={(e) => {
              const value = e.target.value

              setDiscountType(value)

              if (value !== 'multiple') {
                setEligibleCount(
                  value === 'none' ? '0' : '1'
                )

                setRepresentativeEligible(false)
              }

              clearResult()
            }}
          >
            <option value="none">감면 없음</option>

            {selectedDiscounts.length > 1 && (
              <option value="multiple">
                {selectedDiscounts
                  .map(getDiscountLabel)
                  .join(', ')}
              </option>
            )}

            {discountOptions
              .filter((item) => item.code !== 'none')
              .map((item) => (
                <option
                  key={item.code}
                  value={item.code}
                >
                  {item.label}
                </option>
              ))}
          </select>

          {fieldErrorMessage(
            'discount',
            'discount_types',
            'discounts',
            'discount_type'
          )}
        </div>

        {discountType !== 'none' &&
          discountType !== 'multiple' && (
            <>
              <div className="field">
                <label htmlFor="eligible">
                  감면 대상 인원
                </label>

                <input
                  id="eligible"
                  type="number"
                  min="1"
                  step="1"
                  max={people}
                  value={eligibleCount}
                  aria-invalid={Boolean(
                    getFieldError(
                      'count',
                      'eligibleCount',
                      'eligible_count'
                    )
                  )}
                  aria-describedby={
                    getFieldError(
                      'count',
                      'eligibleCount',
                      'eligible_count'
                    )
                      ? 'eligible-error'
                      : undefined
                  }
                  onChange={(e) =>
                    update(
                      setEligibleCount,
                      e.target.value
                    )
                  }
                />

                {fieldErrorMessage(
                  'eligible',
                  'count',
                  'eligibleCount',
                  'eligible_count'
                )}
              </div>

              <div className="field">
                <label htmlFor="representative-eligible">
                  예약 대표자 감면 대상 여부
                </label>

                <select
                  id="representative-eligible"
                  value={
                    representativeEligible
                      ? 'yes'
                      : 'no'
                  }
                  aria-invalid={Boolean(
                    getFieldError(
                      'holder',
                      'representativeEligible',
                      'representative_eligible'
                    )
                  )}
                  aria-describedby={
                    getFieldError(
                      'holder',
                      'representativeEligible',
                      'representative_eligible'
                    )
                      ? 'representative-eligible-error'
                      : undefined
                  }
                  onChange={(e) =>
                    update(
                      setRepresentativeEligible,
                      e.target.value === 'yes'
                    )
                  }
                >
                  <option value="no">아니요</option>

                  <option value="yes">
                    예 (대표자를 감면 대상 인원에 포함)
                  </option>
                </select>

                {fieldErrorMessage(
                  'representative-eligible',
                  'holder',
                  'representativeEligible',
                  'representative_eligible'
                )}
              </div>
            </>
          )}

        {multipleDiscounts &&
          selectedDiscounts.map((code, index) => {
            const detail = discountDetails[code] ?? {
              count: '',
              holder: false,
            }

            const countId = `eligible-${code}`
            const holderId = `representative-${code}`

            const countErrors = [
              `discounts.${index}.count`,
              `discounts.${code}.count`,
              'count',
            ]

            const holderErrors = [
              `discounts.${index}.holder`,
              `discounts.${code}.holder`,
              'holder',
            ]

            return (
              <div
                key={code}
                style={{ display: 'contents' }}
              >
                <div className="field">
                  <label htmlFor={countId}>
                    {getDiscountLabel(code)} 대상 인원
                  </label>

                  <input
                    id={countId}
                    type="number"
                    min="1"
                    step="1"
                    max={people}
                    value={detail.count}
                    aria-invalid={Boolean(
                      getFieldError(...countErrors)
                    )}
                    aria-describedby={
                      getFieldError(...countErrors)
                        ? `${countId}-error`
                        : undefined
                    }
                    onChange={(e) =>
                      updateDiscountDetail(
                        code,
                        'count',
                        e.target.value
                      )
                    }
                  />

                  {fieldErrorMessage(
                    countId,
                    ...countErrors
                  )}
                </div>

                <div className="field">
                  <label htmlFor={holderId}>
                    {getDiscountLabel(code)} 대표자 해당 여부
                  </label>

                  <select
                    id={holderId}
                    value={detail.holder ? 'yes' : 'no'}
                    aria-invalid={Boolean(
                      getFieldError(...holderErrors)
                    )}
                    aria-describedby={
                      getFieldError(...holderErrors)
                        ? `${holderId}-error`
                        : undefined
                    }
                    onChange={(e) =>
                      updateDiscountDetail(
                        code,
                        'holder',
                        e.target.value === 'yes'
                      )
                    }
                  >
                    <option value="no">아니요</option>

                    <option value="yes">
                      예 (대표자를 감면 대상 인원에 포함)
                    </option>
                  </select>

                  {fieldErrorMessage(
                    holderId,
                    ...holderErrors
                  )}
                </div>
              </div>
            )
          })}

        <div className="field">
          <label htmlFor="optional-lighting-minutes">
            선택 조명 사용 시간 (분)
          </label>

          <input
            id="optional-lighting-minutes"
            type="number"
            min="0"
            step="1"
            value={optionalLightingMinutes}
            aria-invalid={Boolean(
              getFieldError(
                'optional_lighting_minutes',
                'optionalLightingMinutes'
              )
            )}
            aria-describedby={
              getFieldError(
                'optional_lighting_minutes',
                'optionalLightingMinutes'
              )
                ? 'optional-lighting-minutes-error'
                : undefined
            }
            onChange={(e) =>
              update(
                setOptionalLightingMinutes,
                e.target.value
              )
            }
          />

          {fieldErrorMessage(
            'optional-lighting-minutes',
            'optional_lighting_minutes',
            'optionalLightingMinutes'
          )}

          <small>
            사용하지 않으면 0분을 입력하세요.
            시설별 조명 가능 시간은 다를 수 있습니다.
          </small>
        </div>
      </div>

      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      <button
        type="button"
        className="search-button"
        onClick={onSearch}
        disabled={
          loading ||
          unavailable ||
          sports.length === 0
        }
      >
        {loading
          ? '검색 중...'
          : optionsLoading
            ? '이용조건 불러오는 중...'
            : '시설 검색하기'}
      </button>
    </section>
  )
}

export default SearchForm