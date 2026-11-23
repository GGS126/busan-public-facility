
import { useEffect, useState } from 'react'
import {
  compareFacilities,
  getOptions,
  getFacilityDetail,
} from './api/compare'

import Header from './components/Header'
import HeroBanner from './components/HeroBanner'
import SearchForm from './components/SearchForm'
import NaturalLanguageInput from './components/NaturalLanguageInput'
import FacilityList from './components/FacilityList'
import FeeResult from './components/FeeResult'
import './App.css'

// 시설 검색 API 연동 전 임시 목록
const facilities = [
  {
    id: 'F001',
    name: '예시 체육관',
    sport: 'futsal',
    district: '해운대구',
    address: '백엔드 연동 테스트용 가상 시설 (실제 주소 없음)',
    bookingUrl: null,
    isTestData: true,
  },
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

function getToday() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

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

function validateFacilityDetail(data, facilityId) {
  if (
    !data ||
    data.facility_id !== facilityId ||
    !Array.isArray(data.time_options)
  ) {
    throw new Error(
      '시설 상세정보의 서버 응답 형식이 올바르지 않습니다.'
    )
  }

  return data
}

function toMinutes(time) {
  if (!time || !/^\d{2}:\d{2}$/.test(time)) {
    return null
  }

  const [hour, minute] = time.split(':').map(Number)

  return hour * 60 + minute
}

function getTimeOptions(detail, sport) {
  if (!detail || !Array.isArray(detail.time_options)) {
    return []
  }

  return detail.time_options.filter(
    (option) => option.sport === sport
  )
}

function isValidFacilityTime(detail, sport, start, end) {
  const startMinutes = toMinutes(start)
  const endMinutes = toMinutes(end)

  if (
    startMinutes === null ||
    endMinutes === null ||
    endMinutes <= startMinutes
  ) {
    return false
  }

  return getTimeOptions(detail, sport).some((option) => {
    if (option.selection === 'fixed_slot') {
      return (
        Array.isArray(option.slots) &&
        option.slots.some(
          (slot) =>
            slot.start_time === start &&
            slot.end_time === end
        )
      )
    }

    if (option.selection !== 'flexible') {
      return false
    }

    const open = toMinutes(option.open_time)
    const close = toMinutes(option.close_time)
    const duration = endMinutes - startMinutes

    if (
      open === null ||
      close === null ||
      startMinutes < open ||
      endMinutes > close
    ) {
      return false
    }

    if (
      Number.isInteger(option.max_minutes) &&
      duration > option.max_minutes
    ) {
      return false
    }

    if (
      Array.isArray(option.allowed_minutes) &&
      option.allowed_minutes.length > 0
    ) {
      return option.allowed_minutes.includes(duration)
    }

    return (
      Number.isInteger(option.max_minutes) &&
      option.max_minutes > 0 &&
      duration % 30 === 0 &&
      startMinutes % 30 === 0
    )
  })
}

function normalizeFieldErrors(fields) {
  if (!fields || typeof fields !== 'object') {
    return {}
  }

  const result = {}

  function add(field, message) {
    if (typeof field !== 'string' || !field.trim()) {
      return
    }

    const key = field
      .replace(/\[(\d+)\]/g, '.$1')
      .split('.')
      .pop()

    const text =
      typeof message === 'string'
        ? message
        : message &&
            typeof message.message === 'string'
          ? message.message
          : '입력값을 확인해 주세요.'

    if (text && !result[key]) {
      result[key] = text
    }
  }

  if (Array.isArray(fields)) {
    fields.forEach((item) => {
      if (item && typeof item === 'object') {
        add(
          item.field || item.loc?.join('.'),
          item.message || item.msg
        )
      }
    })
  } else {
    Object.entries(fields).forEach(([field, messages]) => {
      const values = Array.isArray(messages)
        ? messages
        : [messages]

      values.forEach((message) => add(field, message))
    })
  }

  return result
}

function App() {
  const [sport, setSport] = useState('')
  const [district, setDistrict] = useState('전체')
  const [date, setDate] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [people, setPeople] = useState('1')
  const [discountType, setDiscountType] = useState('none')
  const [eligibleCount, setEligibleCount] = useState('0')

  const [
    representativeEligible,
    setRepresentativeEligible,
  ] = useState(false)

  const [
    optionalLightingMinutes,
    setOptionalLightingMinutes,
  ] = useState('0')

  const [options, setOptions] = useState({
    sports: [],
    districts: [],
    discount_types: [],
  })

  const [optionsLoading, setOptionsLoading] = useState(true)
  const [optionsError, setOptionsError] = useState('')
  const [optionsRetry, setOptionsRetry] = useState(0)

  const [searched, setSearched] = useState(false)
  const [searchResults, setSearchResults] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [facilityTimes, setFacilityTimes] = useState({})
  const [facilityDetails, setFacilityDetails] = useState({})
  const [detailLoading, setDetailLoading] = useState({})
  const [detailErrors, setDetailErrors] = useState({})
  const [results, setResults] = useState([])

  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [compareError, setCompareError] = useState('')
  const [loading, setLoading] = useState(false)

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

        setSport((previous) => {
          if (
            response.sports.some(
              (item) => item.code === previous
            )
          ) {
            return previous
          }

          const tennis = response.sports.find(
            (item) => item.code === 'tennis'
          )

          return (
            tennis?.code ||
            response.sports[0]?.code ||
            ''
          )
        })

        setDistrict((previous) =>
          previous === '전체' ||
          response.districts.includes(previous)
            ? previous
            : '전체'
        )

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

  function retryOptions() {
    setOptionsLoading(true)
    setOptionsError('')
    setOptionsRetry((previous) => previous + 1)
  }

  function clearResult() {
    setSearched(false)
    setSearchResults([])
    setSelectedIds([])
    setFacilityTimes({})
    setFacilityDetails({})
    setDetailLoading({})
    setDetailErrors({})
    setResults([])
    setError('')
    setFieldErrors({})
    setCompareError('')
  }

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
      Boolean(startTime) !== Boolean(endTime)
    ) {
      return '희망 시작시간과 종료시간을 모두 입력해 주세요.'
    }

    if (
      startTime &&
      endTime &&
      startTime >= endTime
    ) {
      return '종료시간은 시작시간보다 늦어야 합니다.'
    }

    if (
      people === '' ||
      !Number.isInteger(Number(people)) ||
      Number(people) < 1
    ) {
      return '이용 인원을 올바르게 입력해 주세요.'
    }

    if (discountType !== 'none') {
      if (
        eligibleCount === '' ||
        !Number.isInteger(Number(eligibleCount)) ||
        Number(eligibleCount) < 1 ||
        Number(eligibleCount) > Number(people)
      ) {
        return '감면 대상 인원을 올바르게 입력해 주세요.'
      }
    }

    if (
      representativeEligible &&
      (
        discountType === 'none' ||
        Number(eligibleCount) < 1
      )
    ) {
      return '대표자가 감면 대상인 경우 감면 대상 인원을 확인해 주세요.'
    }

    if (
      optionalLightingMinutes === '' ||
      !Number.isInteger(
        Number(optionalLightingMinutes)
      ) ||
      Number(optionalLightingMinutes) < 0
    ) {
      return '선택 조명 사용 시간을 0 이상의 정수로 입력해 주세요.'
    }

    if (Number(optionalLightingMinutes) > 0) {
      if (!startTime || !endTime) {
        return '선택 조명을 사용하려면 희망 이용시간을 입력해 주세요.'
      }

      const duration =
        toMinutes(endTime) - toMinutes(startTime)

      if (
        Number(optionalLightingMinutes) > duration
      ) {
        return '선택 조명 사용 시간은 시설 이용 시간보다 길 수 없습니다.'
      }
    }

    return ''
  }

  function handleSearch() {
    const message = validateConditions()

    if (message) {
      setFieldErrors({})
      setError(message)
      return
    }

    const filtered = facilities.filter(
      (facility) =>
        facility.sport === sport &&
        (
          district === '전체' ||
          facility.district === district
        )
    )

    setSearchResults(filtered)
    setSearched(true)
    setSelectedIds([])
    setFacilityTimes({})
    setFacilityDetails({})
    setDetailLoading({})
    setDetailErrors({})
    setResults([])
    setError('')
    setFieldErrors({})
    setCompareError('')

    setTimeout(() => {
      document.getElementById('facilities')?.scrollIntoView({
        behavior: 'smooth',
      })
    }, 100)
  }

  async function toggleFacility(id) {
    const isSelected = selectedIds.includes(id)

    if (isSelected) {
      setSelectedIds((previous) =>
        previous.filter((item) => item !== id)
      )

      setFacilityTimes((previous) => {
        const updated = { ...previous }
        delete updated[id]
        return updated
      })

      setResults([])
      setCompareError('')
      return
    }

    setSelectedIds((previous) => [...previous, id])

    setDetailLoading((previous) => ({
      ...previous,
      [id]: true,
    }))

    setDetailErrors((previous) => ({
      ...previous,
      [id]: '',
    }))

    setResults([])
    setCompareError('')

    try {
      const detail = validateFacilityDetail(
        await getFacilityDetail(id, date),
        id
      )

      setFacilityDetails((previous) => ({
        ...previous,
        [id]: detail,
      }))

      // 희망 이용시간이 실제 상세 규정과 일치하면 자동 선택
      if (
        startTime &&
        endTime &&
        isValidFacilityTime(
          detail,
          sport,
          startTime,
          endTime
        )
      ) {
        setFacilityTimes((previous) => ({
          ...previous,
          [id]: `${startTime}|${endTime}`,
        }))
      }
    } catch (err) {
      setDetailErrors((previous) => ({
        ...previous,
        [id]:
          err.message ||
          '시설 상세정보를 불러오지 못했습니다.',
      }))
    } finally {
      setDetailLoading((previous) => ({
        ...previous,
        [id]: false,
      }))
    }
  }

  function handleTimeChange(facilityId, value) {
    setFacilityTimes((previous) => ({
      ...previous,
      [facilityId]: value,
    }))

    setResults([])
    setCompareError('')
  }

  function handleApplyAI(conditions) {
    const requestedSport =
      conditions.sport || sport

    const nextSport = options.sports.some(
      (item) => item.code === requestedSport
    )
      ? requestedSport
      : sport

    // 백엔드 districts 배열과 기존 district 값 모두 지원
    const requestedDistricts =
      Array.isArray(conditions.districts)
        ? conditions.districts
        : []

    const requestedDistrict =
      requestedDistricts.length > 0
        ? requestedDistricts[0]
        : conditions.district || '전체'

    const nextDistrict =
      requestedDistrict === '전체' ||
      options.districts.includes(requestedDistrict)
        ? requestedDistrict
        : '전체'

    setSport(nextSport)
    setDistrict(nextDistrict)
    setDate(conditions.date || '')

    setStartTime(
      conditions.start_time ||
      conditions.startTime ||
      ''
    )

    setEndTime(
      conditions.end_time ||
      conditions.endTime ||
      ''
    )

    const requestedHeadcount =
      conditions.headcount ??
      conditions.people

    if (requestedHeadcount != null) {
      setPeople(String(requestedHeadcount))
    }

    // AI가 추출한 감면 유형을 직접 입력 폼에 반영
    const requestedDiscountTypes = Array.isArray(
      conditions.discount_types
    )
      ? conditions.discount_types
      : []

    const nextDiscountType =
      requestedDiscountTypes.find(
        (code) =>
          code !== 'none' &&
          options.discount_types.some(
            (item) => item.code === code
          )
      ) || 'none'

    setDiscountType(nextDiscountType)

    // AI는 실제 감면 대상 인원이나 대표자 자격을 확정하지 않음
    setEligibleCount('0')
    setRepresentativeEligible(false)

    clearResult()

    setTimeout(() => {
      document.getElementById('search')?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    }, 100)
  }

  function handleDirectInput() {
    document.getElementById('search')?.scrollIntoView({
      behavior: 'smooth',
    })
  }

  async function handleCompare() {
    setCompareError('')
    setFieldErrors({})
    setResults([])

    if (selectedIds.length === 0) {
      setCompareError(
        '비교할 시설을 하나 이상 선택해 주세요.'
      )
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

    for (const id of selectedIds) {
      const facility = searchResults.find(
        (item) => item.id === id
      )

      const detail = facilityDetails[id]

      if (!facility || !detail) {
        setCompareError(
          '시설 상세정보를 확인한 뒤 비교해 주세요.'
        )
        return
      }

      const [selectedStart, selectedEnd] =
        facilityTimes[id].split('|')

      if (
        !isValidFacilityTime(
          detail,
          facility.sport,
          selectedStart,
          selectedEnd
        )
      ) {
        setCompareError(
          `${facility.name}의 이용시간을 다시 선택해 주세요.`
        )
        return
      }

      const duration =
        toMinutes(selectedEnd) -
        toMinutes(selectedStart)

      if (
        Number(optionalLightingMinutes) > duration
      ) {
        setCompareError(
          `${facility.name}의 선택 조명 사용 시간이 이용시간보다 깁니다.`
        )
        return
      }
    }

    setLoading(true)

    try {
      const responses = await Promise.all(
        selectedIds.map(async (facilityId) => {
          const [selectedStart, selectedEnd] =
            facilityTimes[facilityId].split('|')

          const request = {
            facility_ids: [facilityId],
            conditions: {
              sport,
              districts:
                district === '전체'
                  ? []
                  : [district],
              date,
              start_time: selectedStart,
              end_time: selectedEnd,
              headcount: Number(people),
              discount_types: [],
              discounts:
                discountType === 'none'
                  ? []
                  : [
                      {
                        type: discountType,
                        count: Number(eligibleCount),
                        holder: representativeEligible,
                      },
                    ],
              optional_lighting_minutes:
                Number(optionalLightingMinutes),
              source: 'direct',
            },
          }

          const response =
            await compareFacilities(request)

          if (
            !response ||
            !Array.isArray(response.results)
          ) {
            throw new Error(
              '서버 응답 형식이 올바르지 않습니다.'
            )
          }

          return response.results.map((result) => ({
            ...result,
            selected_date: date,
            selected_start_time: selectedStart,
            selected_end_time: selectedEnd,
          }))
        })
      )

      setResults(responses.flat())

      setTimeout(() => {
        document.getElementById('results')?.scrollIntoView({
          behavior: 'smooth',
        })
      }, 100)
    } catch (err) {
      setFieldErrors(
        normalizeFieldErrors(err.fields)
      )

      setCompareError(
        err.message ||
        '시설 비교 중 오류가 발생했습니다.'
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
        <NaturalLanguageInput
          onApply={handleApplyAI}
          onDirectInput={handleDirectInput}
          options={options}
          optionsLoading={optionsLoading}
          optionsError={optionsError}
        />

        <div style={{ height: '28px' }} />

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
          representativeEligible={representativeEligible}
          setRepresentativeEligible={setRepresentativeEligible}
          optionalLightingMinutes={optionalLightingMinutes}
          setOptionalLightingMinutes={setOptionalLightingMinutes}
          onSearch={handleSearch}
          loading={loading}
          error={error}
          fieldErrors={fieldErrors}
          clearResult={clearResult}
          options={options}
          optionsLoading={optionsLoading}
          optionsError={optionsError}
          onRetryOptions={retryOptions}
        />

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
          facilityDetails={facilityDetails}
          detailLoading={detailLoading}
          detailErrors={detailErrors}
        />

        <FeeResult
          results={results}
          facilities={facilities}
        />

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

            <p>
              현재 예시 체육관(F001)은 백엔드 연동을
              검증하기 위한 가상 테스트 시설입니다.
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
