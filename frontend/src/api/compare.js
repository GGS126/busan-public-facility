
const USE_MOCK_API =
  import.meta.env.VITE_USE_MOCK_API !== 'false'

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || ''

const REQUEST_TIMEOUT = 10000

// API 요청 공통 처리
async function requestAPI(path, options = {}) {
  const controller = new AbortController()

  const timeoutId = setTimeout(() => {
    controller.abort()
  }, REQUEST_TIMEOUT)

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    })

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('요청한 API를 찾을 수 없습니다.')
      }

      if (response.status >= 500) {
        throw new Error(
          '서버에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.'
        )
      }

      throw new Error(
        `요청을 처리할 수 없습니다. (${response.status})`
      )
    }

    return await response.json()
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error(
        '서버 응답 시간이 초과되었습니다. 다시 시도해 주세요.'
      )
    }

    if (error instanceof TypeError) {
      throw new Error(
        '서버에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.'
      )
    }

    throw error
  } finally {
    clearTimeout(timeoutId)
  }
}

// 개발용 모의 비교 결과 생성
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
      payment_due: null,
      expected_refund: null,
      net_cost_after_refund: null,
      review_items: [
        {
          reason:
            '실제 요금 계산 API가 아직 연결되지 않았습니다.',
        },
      ],
    },
    terms: null,
    checklist: [],
    sources: [],
  }
}

// 시설 비교 API
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
