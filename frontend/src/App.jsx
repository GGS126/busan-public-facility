
import { useEffect, useState } from 'react'
import { compareFacilities, getOptions } from './api/compare'
import { getFacilitySlots } from './data/facilitySlots'
import Header from './components/Header'
import HeroBanner from './components/HeroBanner'
import SearchForm from './components/SearchForm'
import NaturalLanguageInput from './components/NaturalLanguageInput'
import FacilityList from './components/FacilityList'
import FeeResult from './components/FeeResult'
import './App.css'

// 비교 대상 공공체육시설
// 시설 검색 API 연동 전까지 기존 목록 유지
const facilities = [
  {
    id: 'busan_haeundae_arboretum_tennis',
    name: '해운대수목원 테니스장',
    sport: 'tennis',
    district: '해운대구',
    address: '부산 해운대구 석대동 26',
    bookingUrl:
      'https://reserve.busan.go.kr/rent/view?resveGroupSn=531&progrmSn=619',
  },
  {
    id: 'busan_samrak_ecopark_tennis',
    name: '삼락생태공원 테니스장',
    sport: 'tennis',
    district: '사상구',
    address: '부산 사상구 낙동대로 1231',
    bookingUrl:
      'https://reserve.busan.go.kr/rent/view?resveGroupSn=55&progrmSn=395',
  },
  {
    id: 'busan_gudeok_stadium_tennis',
    name: '구덕운동장 테니스장',
    sport: 'tennis',
    district: '서구',
    address: '부산 서구 망양로 57',
    bookingUrl:
      'https://reserve.busan.go.kr/rent/view?resveGroupSn=475&progrmSn=472',
  },
]

// 오늘 날짜를 YYYY-MM-DD 형식으로 반환
function getToday() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

// 선택지 API 응답 형식 확인
function validateOptions(data) {
  if (
    !data ||
    !Array.isArray(data.sports) ||
    !Array.isArray(data.districts) ||
    !Array.isArray(data.discount_types)
  ) {
    throw new Error(
      '이용조건 선택지의 서버 응답 형식이 올바르지 않습니다.'
    )
  }

  const validOptions = (items) =>
    items.every(
      (item) =>
        item &&
        typeof item.code === 'string' &&
        typeof item.label === 'string'
    )

  if (
    !validOptions(data.sports) ||
    !validOptions(data.discount_types) ||
    !data.districts.every(
      (district) => typeof district === 'string'
    )
  ) {
    throw new Error(
      '이용조건 선택지에 올바르지 않은 데이터가 포함되어 있습니다.'
    )
  }

  return data
}

function App() {
  // 이용조건 입력 상태
  const [sport, setSport] = useState('')
  const [district, setDistrict] = useState('전체')
  const [date, setDate] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [people, setPeople] = useState('1')
  const [discountType, setDiscountType] = useState('none')
  const [eligibleCount, setEligibleCount] = useState('0')

  // 백엔드에서 가져온 이용조건 선택지
  const [options, setOptions] = useState({
    sports: [],
    districts: [],
    discount_types: [],
  })
  const [optionsLoading, setOptionsLoading] = useState(true)
  const [optionsError, setOptionsError] = useState('')
  const [optionsRetry, setOptionsRetry] = useState(0)

  // 시설 검색 및 비교 상태
  const [searched, setSearched] = useState(false)
  const [searchResults, setSearchResults] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [facilityTimes, setFacilityTimes] = useState({})
  const [results, setResults] = useState([])

  // 오류 및 로딩 상태
  const [error, setError] = useState('')
  const [compareError, setCompareError] = useState('')
  const [loading, setLoading] = useState(false)

  // 페이지 진입 시 이용조건 선택지 조회
  useEffect(() => {
    let cancelled = false

    async function loadOptions() {
      try {
        const response = validateOptions(await getOptions())

        if (cancelled) {
          return
        }

        setOptions(response)
        setOptionsError('')

        // 서버가 지원하는 종목 중 하나를 기본 선택
        setSport((previous) => {
          const exists = response.sports.some(
            (item) => item.code === previous
          )

          if (exists) {
            return previous
          }

          const tennis = response.sports.find(
            (item) => item.code === 'tennis'
          )

          return tennis?.code || response.sports[0]?.code || ''
        })

        // 기존 지역이 API 목록에 없다면 전체로 초기화
        setDistrict((previous) =>
          previous === '전체' ||
          response.districts.includes(previous)
            ? previous
            : '전체'
        )

        // 지원하지 않는 감면 유형이면 감면 없음 선택
        setDiscountType((previous) =>
          previous === 'none' ||
          response.discount_types.some(
            (item) => item.code === previous
          )
            ? previous
            : 'none'
        )
      } catch (err) {
        if (!cancelled) {
          setOptionsError(
            err.message ||
              '이용조건 선택지를 불러오지 못했습니다.'
          )
        }
      } finally {
        if (!cancelled) {
          setOptionsLoading(false)
        }
      }
    }

    loadOptions()

    return () => {
      cancelled = true
    }
  }, [optionsRetry])

  // 선택지 다시 불러오기
  function retryOptions() {
    setOptionsLoading(true)
    setOptionsError('')
    setOptionsRetry((previous) => previous + 1)
  }

  // 입력 조건 변경 시 이전 검색 및 비교 결과 초기화
  function clearResult() {
    setSearched(false)
    setSearchResults([])
    setSelectedIds([])
    setFacilityTimes({})
    setResults([])
    setError('')
    setCompareError('')
  }

  // 이용조건 유효성 검사
  function validateConditions() {
    if (optionsLoading || optionsError) {
      return '이용조건 선택지를 먼저 불러와 주세요.'
    }

    if (
      !sport ||
      !options.sports.some((item) => item.code === sport)
    ) {
      return '이용 종목을 올바르게 선택해 주세요.'
    }

    if (
      district !== '전체' &&
      !options.districts.includes(district)
    ) {
      return '이용 지역을 올바르게 선택해 주세요.'
    }

    if (
      discountType !== 'none' &&
      !options.discount_types.some(
        (item) => item.code === discountType
      )
    ) {
      return '감면 유형을 올바르게 선택해 주세요.'
    }

    if (!date) {
      return '이용 날짜를 선택해 주세요.'
    }

    if (date < getToday()) {
      return '지난 날짜는 선택할 수 없습니다.'
    }

    if (
      (startTime && !endTime) ||
      (!startTime && endTime)
    ) {
      return '희망 시작시간과 종료시간을 모두 입력해 주세요.'
    }

    if (startTime && endTime && startTime >= endTime) {
      return '종료시간은 시작시간보다 늦어야 합니다.'
    }

    if (
      people === '' ||
      !Number.isInteger(Number(people)) ||
      Number(people) < 1
    ) {
      return '이용 인원을 올바르게 입력해 주세요.'
    }

    if (
      discountType !== 'none' &&
      (
        eligibleCount === '' ||
        !Number.isInteger(Number(eligibleCount)) ||
        Number(eligibleCount) < 0 ||
        Number(eligibleCount) > Number(people)
      )
    ) {
      return '감면 대상 인원을 올바르게 입력해 주세요.'
    }

    return ''
  }

  // 시설의 예약 회차와 희망 시간이 일치하는지 확인
  function getMatchingTime(facilityId) {
    if (!startTime || !endTime) {
      return ''
    }

    const slots = getFacilitySlots(facilityId, date)

    const matched = slots.find(
      ([start, end]) =>
        start === startTime && end === endTime
    )

    return matched
      ? `${matched[0]}|${matched[1]}`
      : ''
  }

  // 입력 조건에 맞는 시설 검색
  function handleSearch() {
    const message = validateConditions()

    if (message) {
      setError(message)
      return
    }

    // 시설 검색 API 연동 전까지 기존 시설 목록 사용
    const filtered = facilities.filter((facility) => {
      return (
        facility.sport === sport &&
        (district === '전체' || facility.district === district)
      )
    })

    setSearchResults(filtered)
    setSearched(true)
    setSelectedIds([])
    setFacilityTimes({})
    setResults([])
    setError('')
    setCompareError('')

    setTimeout(() => {
      document.getElementById('facilities')?.scrollIntoView({
        behavior: 'smooth',
      })
    }, 100)
  }

  // 시설 선택 시 일치하는 예약 회차 자동 선택
  function toggleFacility(id) {
    const isSelected = selectedIds.includes(id)

    setSelectedIds((previous) =>
      isSelected
        ? previous.filter((item) => item !== id)
        : [...previous, id]
    )

    setFacilityTimes((previous) => {
      const updated = { ...previous }

      if (isSelected) {
        delete updated[id]
      } else {
        const matchedTime = getMatchingTime(id)

        if (matchedTime) {
          updated[id] = matchedTime
        } else {
          delete updated[id]
        }
      }

      return updated
    })

    setResults([])
    setCompareError('')
  }

  // 시설별 이용시간 저장
  function handleTimeChange(facilityId, value) {
    setFacilityTimes((previous) => ({
      ...previous,
      [facilityId]: value,
    }))

    setResults([])
    setCompareError('')
  }

  // 자연어 입력에서 확인한 조건을 직접 입력 폼에 적용
  function handleApplyAI(conditions) {
    // API가 지원하는 종목만 적용
    const requestedSport = conditions.sport || 'tennis'

    const nextSport = options.sports.some(
      (item) => item.code === requestedSport
    )
      ? requestedSport
      : sport

    // API가 지원하는 지역만 적용
    const requestedDistrict = conditions.district || '전체'

    const nextDistrict =
      requestedDistrict === '전체' ||
      options.districts.includes(requestedDistrict)
        ? requestedDistrict
        : '전체'

    setSport(nextSport)
    setDistrict(nextDistrict)
    setDate(conditions.date || '')

    // 자연어 입력 화면과 시간 필드명 일치
    setStartTime(conditions.startTime || '')
    setEndTime(conditions.endTime || '')

    if (conditions.headcount != null) {
      setPeople(String(conditions.headcount))
    }

    clearResult()

    // 화면 갱신 후 01 이용 조건 입력 영역으로 이동
    setTimeout(() => {
      document.getElementById('search')?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    }, 100)
  }

  // 직접 입력 영역으로 이동
  function handleDirectInput() {
    document.getElementById('search')?.scrollIntoView({
      behavior: 'smooth',
    })
  }

  // 선택한 시설을 각자의 이용시간으로 비교
  async function handleCompare() {
    setCompareError('')
    setResults([])

    if (selectedIds.length === 0) {
      setCompareError('비교할 시설을 하나 이상 선택해 주세요.')
      return
    }

    const message = validateConditions()

    if (message) {
      setCompareError(message)
      return
    }

    const missingTime = selectedIds.some(
      (id) => !facilityTimes[id]
    )

    if (missingTime) {
      setCompareError(
        '선택한 모든 시설의 이용시간을 지정해 주세요.'
      )
      return
    }

    setLoading(true)

    try {
      // 시설마다 서로 다른 시간으로 API 요청
      const responses = await Promise.all(
        selectedIds.map(async (facilityId) => {
          const [selectedStart, selectedEnd] =
            facilityTimes[facilityId].split('|')

          const request = {
            facility_ids: [facilityId],
            conditions: {
              sport,
              districts:
                district === '전체' ? [] : [district],
              date,
              start_time: selectedStart,
              end_time: selectedEnd,
              headcount: Number(people),
              discount_types:
                discountType === 'none' ||
                Number(eligibleCount) === 0
                  ? []
                  : [discountType],
              source: 'direct',
            },
          }

          const response = await compareFacilities(request)

          if (
            !response ||
            !Array.isArray(response.results)
          ) {
            throw new Error(
              '서버 응답 형식이 올바르지 않습니다.'
            )
          }

          // 결과에 시설별 선택 날짜 및 시간 추가
          return response.results.map((result) => ({
            ...result,
            selected_date: date,
            selected_start_time: selectedStart,
            selected_end_time: selectedEnd,
          }))
        })
      )

      // 개별 비교 결과를 하나의 배열로 합침
      setResults(responses.flat())

      setTimeout(() => {
        document.getElementById('results')?.scrollIntoView({
          behavior: 'smooth',
        })
      }, 100)
    } catch (err) {
      setCompareError(
        err.message || '시설 비교 중 오류가 발생했습니다.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <Header />
      <HeroBanner />

      <main className="main-container">
        {/* 자연어 이용조건 입력 */}
        <NaturalLanguageInput
          onApply={handleApplyAI}
          onDirectInput={handleDirectInput}
        />

        <div style={{ height: '28px' }} />

        {/* 이용조건 직접 입력 */}
        <SearchForm
          sport={sport}
          setSport={setSport}
          district={district}
          setDistrict={setDistrict}
          date={date}
          setDate={setDate}
          startTime={startTime}
          setStartTime={setStartTime}
          endTime={endTime}
          setEndTime={setEndTime}
          people={people}
          setPeople={setPeople}
          discountType={discountType}
          setDiscountType={setDiscountType}
          eligibleCount={eligibleCount}
          setEligibleCount={setEligibleCount}
          onSearch={handleSearch}
          loading={loading}
          error={error}
          clearResult={clearResult}
          options={options}
          optionsLoading={optionsLoading}
          optionsError={optionsError}
          onRetryOptions={retryOptions}
        />

        {/* 시설 검색 결과 및 시설별 이용시간 선택 */}
        <FacilityList
          facilities={searchResults}
          selectedIds={selectedIds}
          onToggle={toggleFacility}
          searched={searched}
          onCompare={handleCompare}
          loading={loading}
          facilityTimes={facilityTimes}
          onTimeChange={handleTimeChange}
          date={date}
          error={compareError}
        />

        {/* 시설별 요금 및 이용조건 비교 결과 */}
        <FeeResult
          results={results}
          facilities={facilities}
        />

        {/* 서비스 이용 안내 */}
        <section className="guide-section">
          <h2>서비스 이용 안내</h2>

          <div className="guide-grid">
            <p>
              본 서비스는 부산 공공체육시설의 이용조건을
              비교하기 위한 서비스입니다.
            </p>

            <p>
              실제 예약 및 결제는 각 시설의 공식 예약
              사이트에서 진행해 주세요.
            </p>

            <p>
              예약 가능 여부와 최신 요금·규정은 공식
              안내를 확인해 주세요.
            </p>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        부산 공공체육시설 이용조건 비교 서비스
      </footer>
    </>
  )
}

export default App
