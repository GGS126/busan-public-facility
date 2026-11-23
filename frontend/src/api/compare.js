const USE_MOCK_API =
  import.meta.env.VITE_USE_MOCK_API === 'true'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || ''

const REQUEST_TIMEOUT = 10000

function formatFieldErrors(fields) {
  if (!fields || typeof fields !== 'object') {
    return ''
  }

  if (Array.isArray(fields)) {
    return fields
      .map((item) => {
        if (!item || typeof item !== 'object') {
          return ''
        }

        const field =
          typeof item.field === 'string'
            ? item.field
            : ''

        const message =
          typeof item.message === 'string'
            ? item.message
            : '입력값을 확인해 주세요.'

        return field
          ? `${field}: ${message}`
          : message
      })
      .filter(Boolean)
      .join('\n')
  }

  return Object.entries(fields)
    .flatMap(([field, errors]) => {
      const values = Array.isArray(errors)
        ? errors
        : [errors]

      return values.map((value) => {
        const message =
          typeof value === 'string'
            ? value
            : value &&
                typeof value === 'object' &&
                typeof value.message === 'string'
              ? value.message
              : JSON.stringify(value)

        return `${field}: ${message}`
      })
    })
    .join('\n')
}

function formatValidationErrors(detail) {
  if (!Array.isArray(detail)) {
    return ''
  }

  return detail
    .map((item) => {
      if (!item || typeof item !== 'object') {
        return ''
      }

      const field = Array.isArray(item.loc)
        ? item.loc
            .filter((part) => part !== 'body')
            .join('.')
        : ''

      const message =
        typeof item.msg === 'string'
          ? item.msg
          : '입력값을 확인해 주세요.'

      return field
        ? `${field}: ${message}`
        : message
    })
    .filter(Boolean)
    .join('\n')
}

function createAPIError(response, data) {
  const errorInfo = data?.error
  const errorCode = errorInfo?.code || null

  const fieldErrors = formatFieldErrors(
    errorInfo?.fields
  )

  const validationErrors = formatValidationErrors(
    data?.detail
  )

  let message

  if (
    response.status === 404 &&
    errorCode === 'facility_not_found'
  ) {
    message = '요청한 체육시설을 찾을 수 없습니다.'
  } else if (response.status === 404) {
    message = '요청한 API 경로를 찾을 수 없습니다.'
  } else if (
    errorCode === 'validation_error' &&
    (response.status === 400 ||
      response.status === 422)
  ) {
    message =
      typeof errorInfo?.message === 'string' &&
      errorInfo.message.trim()
        ? errorInfo.message
        : '입력한 이용조건을 확인해 주세요.'
  } else if (
    typeof errorInfo?.message === 'string' &&
    errorInfo.message.trim()
  ) {
    message = errorInfo.message
  } else if (response.status === 422) {
    message = '입력한 이용조건을 확인해 주세요.'
  } else if (response.status >= 500) {
    message =
      '서버에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.'
  } else {
    message =
      `요청을 처리할 수 없습니다. (${response.status})`
  }

  const details = [
    fieldErrors,
    validationErrors,
  ]
    .filter(Boolean)
    .join('\n')

  if (details) {
    message += `\n${details}`
  }

  const error = new Error(message)

  error.status = response.status
  error.code = errorCode
  error.fields = errorInfo?.fields || null

  return error
}

async function requestAPI(path, options = {}) {
  const controller = new AbortController()

  const timeoutId = setTimeout(() => {
    controller.abort()
  }, REQUEST_TIMEOUT)

  try {
    const response = await fetch(
      `${API_BASE_URL}${path}`,
      {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      }
    )

    const contentType =
      response.headers.get('content-type') || ''

    let data = null

    if (contentType.includes('application/json')) {
      try {
        data = await response.json()
      } catch {
        data = null
      }
    }

    if (!response.ok) {
      throw createAPIError(response, data)
    }

    if (data === null) {
      throw new Error(
        '서버에서 올바른 JSON 응답을 받지 못했습니다.'
      )
    }

    return data
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error(
        '서버 응답 시간이 초과되었습니다. 다시 시도해 주세요.',
        { cause: error }
      )
    }

    if (error instanceof TypeError) {
      throw new Error(
        '서버에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.',
        { cause: error }
      )
    }

    throw error
  } finally {
    clearTimeout(timeoutId)
  }
}

function createMockResult(facilityId) {
  const names = {
    busan_haeundae_arboretum_tennis:
      '해운대수목원 테니스장',
    busan_samrak_ecopark_tennis:
      '삼락생태공원 테니스장',
    busan_gudeok_stadium_tennis:
      '구덕운동장 테니스장',
  }

  return {
    facility_id: facilityId,
    facility_name:
      names[facilityId] || facilityId,
    fee: {
      status: 'needs_review',
      items: [],
      payment_due: null,
      expected_refund: null,
      net_cost_after_refund: null,
      review_items: [
        {
          reason:
            '현재 개발용 Mock API를 사용하고 있습니다.',
        },
      ],
    },
    terms: null,
    checklist: [],
    sources: [],
  }
}

// 기존 시설 비교 API
export async function compareFacilities(request) {
  if (USE_MOCK_API) {
    return {
      results: request.facility_ids.map(
        createMockResult
      ),
    }
  }

  return requestAPI('/api/compare', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

// 기존 이용조건 선택지 API
export async function getOptions() {
  return requestAPI('/api/options')
}

// PR #28: 시설 상세 조회 API
export async function getFacilityDetail(facilityId, date) {
  if (!facilityId) {
    throw new Error('시설 ID가 필요합니다.')
  }

  if (!date || !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
    throw new Error(
      '이용 날짜는 YYYY-MM-DD 형식이어야 합니다.'
    )
  }

  const path =
    `/api/facilities/${encodeURIComponent(facilityId)}` +
    `?date=${encodeURIComponent(date)}`

  // Mock 모드에서는 상세정보를 임의로 생성하지 않는다.
  // PR #28의 실제 API 응답을 확인해야 하므로 호출한다.
  return requestAPI(path)
}