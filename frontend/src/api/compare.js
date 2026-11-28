import { facilities } from '../data/mockFacilities'

const USE_MOCK_API = import.meta.env.VITE_USE_MOCK_API === 'true'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

const REQUEST_TIMEOUT = 10000
const NATURAL_LANGUAGE_TIMEOUT = 45000

// API 필드 오류 정규화
function normalizeAPIFields(fields, detail) {
  if (Array.isArray(fields) && fields.length > 0) {
    return fields
  }

  if (
    fields &&
    typeof fields === 'object' &&
    !Array.isArray(fields) &&
    Object.keys(fields).length > 0
  ) {
    return fields
  }

  if (Array.isArray(detail)) {
    const validationFields = detail
      .filter(
        (item) =>
          item &&
          typeof item === 'object'
      )
      .map((item) => ({
        field: Array.isArray(item.loc)
          ? item.loc
              .filter((part) => part !== 'body')
              .join('.')
          : '',
        code: item.type || 'validation_error',
        message:
          typeof item.msg === 'string'
            ? item.msg
            : '입력값을 확인해 주세요.',
      }))

    return validationFields.length
      ? validationFields
      : null
  }

  return null
}

// API 오류 생성
function createAPIError(response, data) {
  const errorInfo = data?.error
  const errorCode = errorInfo?.code || null

  const fields = normalizeAPIFields(
    errorInfo?.fields,
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
    (response.status === 400 || response.status === 422)
  ) {
    message = '입력한 이용조건을 확인해 주세요.'
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
    message = `요청을 처리할 수 없습니다. (${response.status})`
  }

  // 필드별 오류를 상단 메시지에 중복 추가하지 않음
  const error = new Error(message)

  error.status = response.status
  error.code = errorCode
  error.fields = fields

  return error
}

// API 요청 공통 처리
async function requestAPI(path, options = {}) {
  const {
    timeout = REQUEST_TIMEOUT,
    ...fetchOptions
  } = options

  const controller = new AbortController()

  const timeoutId = setTimeout(
    () => controller.abort(),
    timeout
  )

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions.headers,
      },
    })

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

// Mock 시설 이용시간 정책 공통 처리
function getMockTimeOptions(facility) {
  // 기존 사상구 고정 시간대 유지
  if (facility.district === '사상구') {
    const slots = [
      '08:00|10:00',
      '10:00|12:00',
      '13:00|15:00',
      '15:00|17:00',
    ].map((slot) => {
      const [start_time, end_time] = slot.split('|')

      return {
        start_time,
        end_time,
      }
    })

    return {
      selection: 'fixed_slot',
      slots,
    }
  }

  const timeOptions = facility.time_options

  if (
    Array.isArray(timeOptions) &&
    timeOptions.length > 0
  ) {
    return timeOptions
  }

  if (
    timeOptions &&
    typeof timeOptions === 'object' &&
    !Array.isArray(timeOptions) &&
    Object.keys(timeOptions).length > 0
  ) {
    return timeOptions
  }

  // 운영시간 정보가 없는 Mock 시설은 자유시간 방식 사용
  return {
    selection: 'flexible',
    open_time: null,
    close_time: null,
  }
}

// 개발용 Mock 시설 상세정보
function createMockFacilityDetail(facility, date) {
  return {
    ...facility,
    facility_id:
      facility.facility_id || facility.id,
    facility_name:
      facility.facility_name || facility.name,
    date,
    booking_url:
      facility.booking_url ||
      facility.bookingUrl ||
      null,
    time_options: getMockTimeOptions(facility),
    sources: Array.isArray(facility.sources)
      ? facility.sources
      : [],
    isTestData: true,
  }
}

// 개발용 Mock 비교 결과
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
    facility_name: names[facilityId] || facilityId,
    fee: {
      status: 'needs_review',
      items: [],
      total: null,
      payment_due: null,
      online_prepay: null,
      onsite_payment: null,
      payment_unverified: null,
      expected_refund: null,
      net_cost_after_refund: null,
      review_items: [
        {
          reason: '현재 개발용 Mock API를 사용하고 있습니다.',
        },
      ],
    },
    cancel_refund: null,
    terms: null,
    checklist: [],
    checklist_review_items: [],
    sources: [],
  }
}

// 시설 요금 비교 API
export async function compareFacilities(request) {
  if (USE_MOCK_API) {
    return {
      results: request.facility_ids.map(createMockResult),
    }
  }

  return requestAPI('/api/compare', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

// 시설 검색 조건 선택지 API
export async function getSearchOptions() {
  if (USE_MOCK_API) {
    return {
      sports: [
        {
          code: 'tennis',
          label: '테니스',
        },
      ],
      districts: [
        ...new Set(
          facilities.map((facility) => facility.district)
        ),
      ],
      discount_types: [
        {
          code: 'disabled',
          label: '장애인',
        },
        {
          code: 'multi_child',
          label: '다자녀 가정',
        },
      ],
    }
  }

  return requestAPI('/api/facilities/options')
}

// 기존 선택지 조회 함수 호환
export async function getOptions() {
  return getSearchOptions()
}

// 시설 상세정보 API
export async function getFacilityDetail(facilityId, date) {
  if (!facilityId) {
    throw new Error('시설 ID가 필요합니다.')
  }

  if (
    !date ||
    !/^\d{4}-\d{2}-\d{2}$/.test(date)
  ) {
    throw new Error(
      '이용 날짜는 YYYY-MM-DD 형식이어야 합니다.'
    )
  }

  // Mock 모드에서는 실제 백엔드에 요청하지 않음
  if (USE_MOCK_API) {
    const facility = facilities.find(
      (item) =>
        (item.facility_id || item.id) === facilityId
    )

    if (!facility) {
      const error = new Error(
        '요청한 체육시설을 찾을 수 없습니다.'
      )

      error.status = 404
      error.code = 'facility_not_found'
      error.fields = null

      throw error
    }

    return createMockFacilityDetail(facility, date)
  }

  const path =
    `/api/facilities/${encodeURIComponent(facilityId)}` +
    `?date=${encodeURIComponent(date)}`

  return requestAPI(path)
}

// 자연어 이용조건 추출 API
export async function parseNaturalLanguage(sentence) {
  if (
    typeof sentence !== 'string' ||
    !sentence.trim()
  ) {
    throw new Error(
      '이용 조건을 문장으로 입력해 주세요.'
    )
  }

  if (sentence.trim().length > 500) {
    throw new Error(
      '이용 조건은 500자 이내로 입력해 주세요.'
    )
  }

  if (USE_MOCK_API) {
    return {
      status: 'llm_failed',
      message: '모의 모드에서는 직접 입력해 주세요.',
    }
  }

  return requestAPI('/api/query/parse', {
    method: 'POST',
    body: JSON.stringify({
      query: sentence.trim(),
    }),
    timeout: NATURAL_LANGUAGE_TIMEOUT,
  })
}

// 시설 검색 API
export async function searchFacilities(conditions) {
  if (USE_MOCK_API) {
    const districts = Array.isArray(conditions.districts)
      ? conditions.districts
      : []

    const candidates = facilities.filter(
      (facility) => facility.sport === conditions.sport
    )

    const results = candidates
      .filter(
        (facility) =>
          !districts.length ||
          districts.includes(facility.district)
      )
      .map((facility) => {
        const timeOptions = getMockTimeOptions(facility)

        const result = {
          ...facility,
          id: facility.facility_id || facility.id,
          time_options: timeOptions,
          isTestData: true,
        }

        if (facility.district !== '사상구') {
          return result
        }

        const requested =
          conditions.start_time && conditions.end_time

        const matches = timeOptions.slots.some(
          (slot) =>
            slot.start_time === conditions.start_time &&
            slot.end_time === conditions.end_time
        )

        return {
          ...result,
          time_check: {
            status: requested
              ? matches
                ? 'eligible'
                : 'not_eligible'
              : 'unknown',
          },
        }
      })

    return {
      results,
      alternatives: results.length
        ? null
        : {
            districts: [
              ...new Set(
                candidates.map(
                  (facility) => facility.district
                )
              ),
            ].sort(),
          },
    }
  }

  const result = await requestAPI('/api/facilities/search', {
    method: 'POST',
    body: JSON.stringify({ conditions }),
  })

  if (!Array.isArray(result.results)) {
    throw new Error(
      '서버에서 올바른 시설 검색 결과를 받지 못했습니다.'
    )
  }

  return {
    ...result,
    results: result.results.map((facility) => ({
      ...facility,
      id: facility.facility_id,
      bookingUrl: facility.booking_url,
    })),
  }
}