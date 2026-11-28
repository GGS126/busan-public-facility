import { useEffect, useRef, useState } from 'react'
import {
  compareFacilities,
  getSearchOptions,
  searchFacilities,
  getFacilityDetail,
} from './api/compare'

import {
  toMinutes,
  isBlockedFacility,
  isValidFacilityTime,
} from './data/facilityTimeOptions'

import Header from './components/Header'
import HeroBanner from './components/HeroBanner'
import SearchForm from './components/SearchForm'
import NaturalLanguageInput from './components/NaturalLanguageInput'
import FacilityList from './components/FacilityList'
import FeeResult from './components/FeeResult'
import './App.css'

// 부산 전체 행정구역
const BUSAN_DISTRICTS = [
  '중구',
  '서구',
  '동구',
  '영도구',
  '부산진구',
  '동래구',
  '남구',
  '북구',
  '해운대구',
  '사하구',
  '금정구',
  '강서구',
  '연제구',
  '수영구',
  '사상구',
  '기장군',
]

// 취소 및 미이용 환불 사유
const CANCELLATION_REASONS = [
  'user_cancel',
  'rain_same_day',
  'rain_unused',
  'force_majeure_or_city_event',
]

// 오늘 날짜 반환
function getToday() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

// 날짜 형식 및 실제 날짜 유효성 확인
function isValidDate(value) {
  if (
    typeof value !== 'string' ||
    !/^\d{4}-\d{2}-\d{2}$/.test(value)
  ) {
    return false
  }

  const parsed = new Date(`${value}T00:00:00Z`)

  return (
    !Number.isNaN(parsed.getTime()) &&
    parsed.toISOString().slice(0, 10) === value
  )
}

// 이용조건 선택지 응답 검증
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

// 시설 상세정보 응답 검증
function validateFacilityDetail(data, facilityId) {
  if (
    !data ||
    data.facility_id !== facilityId ||
    (
      !Array.isArray(data.time_options) &&
      (
        !data.time_options ||
        typeof data.time_options !== 'object'
      )
    )
  ) {
    throw new Error(
      '시설 상세정보의 서버 응답 형식이 올바르지 않습니다.'
    )
  }

  return data
}

// 백엔드 필드별 오류 메시지 정리
function normalizeFieldErrors(fields) {
  if (!fields || typeof fields !== 'object') {
    return {}
  }

  const result = {}

  function add(field, message, code) {
    const normalized =
      typeof field === 'string'
        ? field.replace(/\[(\d+)\]/g, '.$1')
        : ''

    const parts = normalized.split('.')
    const discountIndex = parts.indexOf('discounts')

    let key

    if (
      code === 'invalid_cancellation' ||
      parts.includes('cancellation')
    ) {
      key = 'cancellation'
    } else if (discountIndex !== -1) {
      key = parts.slice(discountIndex).join('.')
    } else if (code === 'invalid_discount') {
      key = 'discounts'
    } else {
      key = parts[parts.length - 1] || '_general'
    }

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
          item.field ||
            (
              Array.isArray(item.loc)
                ? item.loc.join('.')
                : ''
            ),
          item.message || item.msg,
          item.code || item.type
        )
      }
    })
  } else {
    Object.entries(fields).forEach(
      ([field, messages]) => {
        const values = Array.isArray(messages)
          ? messages
          : [messages]

        values.forEach(
          (message) =>
            add(field, message, message?.code)
        )
      }
    )
  }

  return result
}

// 입력란에 연결할 수 없는 오류만 상단 메시지에 추가
function getAPIErrorMessage(
  err,
  normalizedErrors,
  fallback,
  discountTypes = []
) {
  const visibleFields = new Set([
    'sport',
    'district',
    'districts',
    'date',
    'start_time',
    'startTime',
    'end_time',
    'endTime',
    'headcount',
    'people',
    'discount_types',
    'discounts',
    'discount_type',
    'optional_lighting_minutes',
    'optionalLightingMinutes',
    'cancellation',
    'cancel_date',
    'cancellation.cancel_date',
    'cancellation.reason',
  ])

  if (discountTypes.length > 0) {
    visibleFields.add('count')
    visibleFields.add('holder')
  }

  if (discountTypes.length === 1) {
    visibleFields.add('eligibleCount')
    visibleFields.add('eligible_count')
    visibleFields.add('representativeEligible')
    visibleFields.add('representative_eligible')
  }

  discountTypes.forEach((code, index) => {
    visibleFields.add(`discounts.${index}.count`)
    visibleFields.add(`discounts.${index}.holder`)
    visibleFields.add(`discounts.${code}.count`)
    visibleFields.add(`discounts.${code}.holder`)
  })

  const remainingMessages = [
    ...new Set(
      Object.entries(normalizedErrors)
        .filter(([key]) => !visibleFields.has(key))
        .map(([, message]) => message)
        .filter(Boolean)
    ),
  ]

  const message = err.message || fallback

  return [
    ...new Set([
      message,
      ...remainingMessages,
    ]),
  ].join('\n')
}

function App() {
  // 이용조건 입력 상태
  const [sport, setSport] = useState('')
  const [districts, setDistricts] = useState([])

  const district =
    districts.length > 1
      ? 'multiple'
      : districts[0] ?? '전체'

  const [date, setDate] = useState('')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [people, setPeople] = useState('1')

  const [discountTypes, setDiscountTypes] =
    useState([])

  const discountType =
    discountTypes.length > 1
      ? 'multiple'
      : discountTypes[0] ?? 'none'

  const [eligibleCount, setEligibleCount] =
    useState('0')

  const [
    representativeEligible,
    setRepresentativeEligible,
  ] = useState(false)

  // 복수 감면 유형별 대상 인원 및 대표자 자격
  const [discountDetails, setDiscountDetails] =
    useState({})

  const [
    optionalLightingMinutes,
    setOptionalLightingMinutes,
  ] = useState('0')

  // 취소 및 미이용 환불 조건
  const [cancellationReason, setCancellationReason] =
    useState('none')

  const [cancelDate, setCancelDate] =
    useState('')

  const [source, setSource] = useState('direct')

  // 이용조건 선택지 상태
  const [options, setOptions] = useState({
    sports: [],
    districts: [],
    discount_types: [],
  })

  const [optionsLoading, setOptionsLoading] =
    useState(true)

  const [optionsError, setOptionsError] =
    useState('')

  const [optionsRetry, setOptionsRetry] =
    useState(0)

  // 이전 API 응답에 의한 상태 덮어쓰기 방지
  const searchRequest = useRef(0)
  const compareRequest = useRef(0)
  const detailRequests = useRef({})

  // 시설 검색 및 비교 상태
  const [searching, setSearching] =
    useState(false)

  const [searched, setSearched] =
    useState(false)

  const [searchResults, setSearchResults] =
    useState([])

  const [alternatives, setAlternatives] =
    useState([])

  const [selectedIds, setSelectedIds] =
    useState([])

  const [facilityTimes, setFacilityTimes] =
    useState({})

  const [facilityDetails, setFacilityDetails] =
    useState({})

  const [detailLoading, setDetailLoading] =
    useState({})

  const [detailErrors, setDetailErrors] =
    useState({})

  const [results, setResults] = useState([])
  const [error, setError] = useState('')

  const [fieldErrors, setFieldErrors] =
    useState({})

  const [compareError, setCompareError] =
    useState('')

  const [loading, setLoading] =
    useState(false)

  // 백엔드 이용조건 선택지 불러오기
  useEffect(() => {
    let cancelled = false

    async function loadOptions() {
      try {
        const response = validateOptions(
          await getSearchOptions()
        )

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

        // 시설 등록 여부와 관계없이 유효한 부산 지역 유지
        setDistricts((previous) =>
          previous.filter(
            (district) =>
              BUSAN_DISTRICTS.includes(district)
          )
        )

        setDiscountTypes((previous) =>
          previous.filter(
            (code) =>
              response.discount_types.some(
                (item) => item.code === code
              )
          )
        )

        setDiscountDetails((previous) =>
          Object.fromEntries(
            Object.entries(previous).filter(
              ([code]) =>
                response.discount_types.some(
                  (item) => item.code === code
                )
            )
          )
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

  // 선택지 불러오기 재시도
  function retryOptions() {
    setOptionsLoading(true)
    setOptionsError('')
    setOptionsRetry((previous) => previous + 1)
  }

  // 이전 비교 요청 무효화 및 결과 초기화
  function resetComparison() {
    const requestId = ++compareRequest.current

    setLoading(false)
    setResults([])
    setCompareError('')

    return requestId
  }

  // 입력 조건 변경 시 검색 및 비교 결과 초기화
  function clearResult() {
    searchRequest.current += 1
    detailRequests.current = {}

    setSearching(false)
    setSearched(false)
    setSearchResults([])
    setAlternatives([])
    setSelectedIds([])
    setFacilityTimes({})
    setFacilityDetails({})
    setDetailLoading({})
    setDetailErrors({})
    setError('')
    setFieldErrors({})

    resetComparison()
  }

  // 직접 입력으로 지역 변경
  function handleDistrictChange(value) {
    if (value === 'multiple') {
      return
    }

    setDistricts(
      value === '전체' ? [] : [value]
    )
  }

  // 감면 유형 변경
  function handleDiscountChange(value) {
    if (value === 'multiple') {
      return
    }

    setDiscountTypes(
      value === 'none' ? [] : [value]
    )

    setEligibleCount('0')
    setRepresentativeEligible(false)
    setDiscountDetails({})
  }

  // 이용일 변경 시 기존 취소일의 유효성 확인
  function handleDateChange(value) {
    setDate(value)

    if (
      cancelDate &&
      (
        !value ||
        cancelDate > value ||
        cancelDate < getToday()
      )
    ) {
      setCancelDate('')
    }
  }

  // 취소 조건 관련 오류만 초기화
  function clearCancellationErrors() {
    setFieldErrors((previous) => {
      const updated = { ...previous }

      delete updated.cancellation
      delete updated.cancel_date
      delete updated['cancellation.cancel_date']
      delete updated['cancellation.reason']

      return updated
    })
  }

  // 취소 사유 변경
  function handleCancellationReasonChange(value) {
    setCancellationReason(value)

    if (value !== 'user_cancel') {
      setCancelDate('')
    }

    clearCancellationErrors()

    // 검색 결과와 선택 시설은 유지
    resetComparison()
  }

  // 취소일 변경
  function handleCancelDateChange(value) {
    setCancelDate(value)
    clearCancellationErrors()

    // 검색 결과와 선택 시설은 유지
    resetComparison()
  }

  // 공통 이용조건 검증
  function validateConditions() {
    if (optionsLoading || optionsError) {
      return '이용조건 선택지를 먼저 불러와 주세요.'
    }

    if (
      !sport ||
      !options.sports.some(
        (item) => item.code === sport
      )
    ) {
      return '이용 종목을 올바르게 선택해 주세요.'
    }

    // DB에 시설이 없는 지역도 부산 행정구역이면 검색 허용
    if (
      districts.some(
        (district) =>
          !BUSAN_DISTRICTS.includes(district)
      )
    ) {
      return '이용 지역을 올바르게 선택해 주세요.'
    }

    if (
      discountTypes.some(
        (code) =>
          !options.discount_types.some(
            (item) => item.code === code
          )
      )
    ) {
      return '감면 유형을 올바르게 선택해 주세요.'
    }

    if (!date) {
      return '이용 날짜를 선택해 주세요.'
    }

    if (!isValidDate(date)) {
      return '이용 날짜를 올바르게 입력해 주세요.'
    }

    if (date < getToday()) {
      return '지난 날짜는 선택할 수 없습니다.'
    }

    if (
      Boolean(startTime) !== Boolean(endTime)
    ) {
      return '희망 시작시간과 종료시간을 모두 입력해 주세요.'
    }

    if (startTime && endTime) {
      const start = toMinutes(startTime)
      const end = toMinutes(endTime)

      if (start === null || end === null) {
        return '희망 이용시간을 올바르게 입력해 주세요.'
      }

      if (start >= end) {
        return '종료시간은 시작시간보다 늦어야 합니다.'
      }
    }

    if (
      people === '' ||
      !Number.isInteger(Number(people)) ||
      Number(people) < 1
    ) {
      return '이용 인원을 올바르게 입력해 주세요.'
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

    if (
      Number(optionalLightingMinutes) > 0 &&
      startTime &&
      endTime
    ) {
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

  // 감면 유형별 입력값을 API 요청 형식으로 변환
  function buildDiscounts() {
    if (discountTypes.length === 0) {
      return []
    }

    if (discountTypes.length === 1) {
      return [
        {
          type: discountTypes[0],
          count: Number(eligibleCount),
          holder: representativeEligible,
        },
      ]
    }

    return discountTypes.map((code) => ({
      type: code,
      count: Number(
        discountDetails[code]?.count ?? ''
      ),
      holder:
        discountDetails[code]?.holder === true,
    }))
  }

  // 비교 요청에 필요한 감면 정보 검증
  function validateDiscountConditions() {
    if (
      new Set(discountTypes).size !==
      discountTypes.length
    ) {
      return '같은 감면 유형을 중복 선택할 수 없습니다.'
    }

    if (discountTypes.length === 0) {
      return representativeEligible
        ? '감면 유형을 먼저 선택해 주세요.'
        : ''
    }

    if (discountTypes.length === 1) {
      if (
        eligibleCount === '' ||
        !Number.isInteger(Number(eligibleCount)) ||
        Number(eligibleCount) < 1 ||
        Number(eligibleCount) > Number(people)
      ) {
        return '감면 대상 인원을 올바르게 입력해 주세요.'
      }

      return ''
    }

    let totalDiscountCount = 0
    let holderCount = 0

    // 복수 감면 유형별 입력값 검증
    for (const code of discountTypes) {
      const detail = discountDetails[code]

      const label =
        options.discount_types.find(
          (item) => item.code === code
        )?.label ?? code

      if (
        !detail ||
        detail.count === '' ||
        !Number.isInteger(Number(detail.count)) ||
        Number(detail.count) < 1 ||
        Number(detail.count) > Number(people)
      ) {
        return `${label} 감면 대상 인원을 올바르게 입력해 주세요.`
      }

      totalDiscountCount += Number(detail.count)

      if (detail.holder === true) {
        holderCount += 1
      }
    }

    // 감면 대상 인원 합계 검증
    if (totalDiscountCount > Number(people)) {
      return '감면 대상 인원의 합계는 전체 이용 인원을 초과할 수 없습니다.'
    }

    // 예약 대표자는 하나의 감면 유형에만 포함 가능
    if (holderCount > 1) {
      return '예약 대표자는 하나의 감면 유형에만 포함할 수 있습니다.'
    }

    return ''
  }

  // 취소 및 미이용 환불 조건 검증
  function validateCancellationConditions() {
    if (cancellationReason === 'none') {
      return ''
    }

    if (
      !CANCELLATION_REASONS.includes(
        cancellationReason
      )
    ) {
      return '취소 및 미이용 사유를 올바르게 선택해 주세요.'
    }

    if (cancellationReason === 'user_cancel') {
      if (!cancelDate) {
        return '사용자 취소는 취소일을 입력해야 합니다.'
      }

      if (!isValidDate(cancelDate)) {
        return '취소일을 올바르게 입력해 주세요.'
      }

      if (cancelDate < getToday()) {
        return '지난 날짜에 취소한 경우는 계산할 수 없습니다.'
      }

      if (cancelDate > date) {
        return '취소일은 이용일보다 늦을 수 없습니다.'
      }
    } else if (cancelDate) {
      return '우천·불가항력 환불은 취소일을 받지 않습니다.'
    }

    return ''
  }

  // 취소 조건을 API 요청 형식으로 변환
  function buildCancellation() {
    if (cancellationReason === 'none') {
      return null
    }

    if (cancellationReason === 'user_cancel') {
      return {
        reason: cancellationReason,
        cancel_date: cancelDate,
      }
    }

    return {
      reason: cancellationReason,
    }
  }

  // 실제 시설 검색 API 호출
  async function handleSearch() {
    const message = validateConditions()

    if (message) {
      setFieldErrors({})
      setError(message)
      return
    }

    clearResult()

    const requestId = searchRequest.current

    setSearching(true)

    try {
      const response = await searchFacilities({
        sport,
        districts,
        date,

        ...(startTime && endTime
          ? {
              start_time: startTime,
              end_time: endTime,
            }
          : {}),
        source,
      })

      if (requestId !== searchRequest.current) {
        return
      }

      if (
        !response ||
        !Array.isArray(response.results)
      ) {
        throw new Error(
          '시설 검색 결과의 서버 응답 형식이 올바르지 않습니다.'
        )
      }

      const facilities = response.results.map(
        (facility) => ({
          ...facility,
          id: facility.id ?? facility.facility_id,
          sport: facility.sport || sport,
          bookingUrl:
            facility.bookingUrl ??
            facility.booking_url,
        })
      )

      setAlternatives(
        Array.isArray(response.alternatives)
          ? response.alternatives
          : response.alternatives?.districts ?? []
      )

      setSearchResults(facilities)
      setSearched(true)

      requestAnimationFrame(() => {
        if (
          requestId !== searchRequest.current
        ) {
          return
        }

        document
          .getElementById('facilities')
          ?.scrollIntoView({
            behavior: 'smooth',
          })
      })
    } catch (err) {
      if (requestId !== searchRequest.current) {
        return
      }

      const normalizedErrors =
        normalizeFieldErrors(err.fields)

      setFieldErrors(normalizedErrors)

      setError(
        getAPIErrorMessage(
          err,
          normalizedErrors,
          '시설 검색 중 오류가 발생했습니다.',
          discountTypes
        )
      )
    } finally {
      if (requestId === searchRequest.current) {
        setSearching(false)
      }
    }
  }

  // 시설 상세정보 조회 공통 처리
  async function loadFacilityDetail(id, facility) {
    const requestId = searchRequest.current
    const detailRequestId = Symbol(id)

    detailRequests.current[id] =
      detailRequestId

    function isCurrentRequest() {
      return (
        requestId === searchRequest.current &&
        detailRequests.current[id] ===
          detailRequestId
      )
    }

    setDetailLoading((previous) => ({
      ...previous,
      [id]: true,
    }))

    setDetailErrors((previous) => ({
      ...previous,
      [id]: '',
    }))

    // 재조회 시 이전 상세정보 제거
    setFacilityDetails((previous) => {
      const updated = { ...previous }

      delete updated[id]

      return updated
    })

    setFacilityTimes((previous) => {
      const updated = { ...previous }

      delete updated[id]

      return updated
    })

    try {
      const detail = validateFacilityDetail(
        await getFacilityDetail(id, date),
        id
      )

      if (!isCurrentRequest()) {
        return
      }

      setFacilityDetails((previous) => ({
        ...previous,
        [id]: detail,
      }))

      // 희망 이용시간이 시설 규정과 일치하면 자동 선택
      if (
        startTime &&
        endTime &&
        isValidFacilityTime(
          detail,
          facility,
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
      if (!isCurrentRequest()) {
        return
      }

      setDetailErrors((previous) => ({
        ...previous,
        [id]:
          err.message ||
          '시설 상세정보를 불러오지 못했습니다.',
      }))
    } finally {
      if (isCurrentRequest()) {
        setDetailLoading((previous) => ({
          ...previous,
          [id]: false,
        }))
      }
    }
  }

  // 시설 선택 및 상세정보 조회
  async function toggleFacility(id) {
    const isSelected = selectedIds.includes(id)

    resetComparison()

    if (isSelected) {
      delete detailRequests.current[id]

      setSelectedIds((previous) =>
        previous.filter((item) => item !== id)
      )

      setFacilityTimes((previous) => {
        const updated = { ...previous }
        delete updated[id]
        return updated
      })

      setFacilityDetails((previous) => {
        const updated = { ...previous }
        delete updated[id]
        return updated
      })

      setDetailLoading((previous) => {
        const updated = { ...previous }
        delete updated[id]
        return updated
      })

      setDetailErrors((previous) => {
        const updated = { ...previous }
        delete updated[id]
        return updated
      })

      return
    }

    const facility = searchResults.find(
      (item) => item.id === id
    )

    if (!facility) {
      setCompareError(
        '선택한 시설을 찾을 수 없습니다.'
      )

      return
    }

    if (
      isBlockedFacility(
        facility,
        facilityDetails[id]
      )
    ) {
      setCompareError(
        '휴장 또는 이용시간 규정 충돌로 비교할 수 없는 시설입니다.'
      )

      return
    }

    setSelectedIds((previous) =>
      previous.includes(id)
        ? previous
        : [...previous, id]
    )

    await loadFacilityDetail(id, facility)
  }

  // 시설 상세정보 조회 재시도
  async function retryFacilityDetail(id) {
    if (
      !selectedIds.includes(id) ||
      detailLoading[id]
    ) {
      return
    }

    const facility = searchResults.find(
      (item) => item.id === id
    )

    if (!facility) {
      setCompareError(
        '선택한 시설을 찾을 수 없습니다.'
      )

      return
    }

    if (
      isBlockedFacility(
        facility,
        facilityDetails[id]
      )
    ) {
      setCompareError(
        '휴장 또는 이용시간 규정 충돌로 비교할 수 없는 시설입니다.'
      )

      return
    }

    resetComparison()

    // 기존 시설 선택을 유지하면서 상세정보만 재조회
    await loadFacilityDetail(id, facility)
  }

  // 시설별 이용시간 변경
  function handleTimeChange(facilityId, value) {
    setFacilityTimes((previous) => ({
      ...previous,
      [facilityId]: value,
    }))

    resetComparison()
  }

  // 자연어 분석 결과를 직접 입력 폼에 반영
  function handleApplyAI(conditions) {
    if (
      !conditions ||
      typeof conditions !== 'object'
    ) {
      return
    }

    clearResult()
    setSource('llm')

    const requestedSport =
      conditions.sport || sport

    setSport(
      options.sports.some(
        (item) => item.code === requestedSport
      )
        ? requestedSport
        : ''
    )

    const requestedDistricts =
      Array.isArray(conditions.districts)
        ? conditions.districts
        : conditions.district &&
            conditions.district !== '전체'
          ? [conditions.district]
          : []

    setDistricts([
      ...new Set(
        requestedDistricts.filter(
          (district) =>
            typeof district === 'string' &&
            district !== '전체'
        )
      ),
    ])

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

    setPeople(
      requestedHeadcount != null
        ? String(requestedHeadcount)
        : ''
    )

    const requestedDiscountTypes =
      Array.isArray(conditions.discount_types)
        ? conditions.discount_types
        : []

    const validDiscountTypes = [
      ...new Set(
        requestedDiscountTypes.filter(
          (code) =>
            code !== 'none' &&
            options.discount_types.some(
              (item) => item.code === code
            )
        )
      ),
    ]

    setDiscountTypes(validDiscountTypes)

    // AI가 실제 감면 인원을 임의로 확정하지 않도록 초기화
    setEligibleCount(
      validDiscountTypes.length === 0 ? '0' : ''
    )

    setRepresentativeEligible(false)

    // 감면 유형별 대상 인원은 사용자가 직접 입력
    setDiscountDetails(
      Object.fromEntries(
        validDiscountTypes.map((code) => [
          code,
          {
            count: '',
            holder: false,
          },
        ])
      )
    )

    setOptionalLightingMinutes('0')

    // 새로운 자연어 조건 적용 시 이전 취소 조건 초기화
    setCancellationReason('none')
    setCancelDate('')

    requestAnimationFrame(() => {
      document
        .getElementById('search')
        ?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        })
    })
  }

  // 직접 입력 영역으로 이동
  function handleDirectInput() {
    setSource('direct')
    clearResult()

    document
      .getElementById('search')
      ?.scrollIntoView({
        behavior: 'smooth',
      })
  }

  // 선택한 시설의 비교 API 호출
  async function handleCompare() {
    const requestId = resetComparison()

    setFieldErrors({})

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

    const discountMessage =
      validateDiscountConditions()

    if (discountMessage) {
      setFieldErrors({
        discounts: discountMessage,
      })

      setCompareError(
        '감면 입력 조건을 확인해 주세요.'
      )

      return
    }

    // 취소 및 미이용 환불 조건 검증
    const cancellationMessage =
      validateCancellationConditions()

    if (cancellationMessage) {
      setFieldErrors({
        cancellation: cancellationMessage,
      })

      setCompareError(
        '취소 및 미이용 환불 조건을 확인해 주세요.'
      )

      return
    }

    // 검증된 감면 정보를 API 요청에 사용
    const discounts = buildDiscounts()

    // 검증된 취소 조건을 API 요청에 사용
    const cancellation = buildCancellation()

    const missingTime = selectedIds.some(
      (id) => {
        const [start, end] = (
          facilityTimes[id] || ''
        ).split('|')

        const startMinutes = toMinutes(start)
        const endMinutes = toMinutes(end)

        return (
          startMinutes === null ||
          endMinutes === null ||
          startMinutes >= endMinutes
        )
      }
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

      if (
        !facility ||
        !detail ||
        detailLoading[id] ||
        detailErrors[id]
      ) {
        setCompareError(
          '시설 상세정보를 확인한 뒤 비교해 주세요.'
        )

        return
      }

      if (
        isBlockedFacility(facility, detail)
      ) {
        setCompareError(
          `${facility.name}은 휴장 또는 이용시간 규정 충돌로 비교할 수 없습니다.`
        )

        return
      }

      const [selectedStart, selectedEnd] =
        facilityTimes[id].split('|')

      if (
        !isValidFacilityTime(
          detail,
          facility,
          sport,
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
        Number(optionalLightingMinutes) >
        duration
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
              districts,
              date,

              start_time: selectedStart,
              end_time: selectedEnd,

              headcount: Number(people),

              // 동일 감면 유형의 중복 전달 방지
              discount_types: [],

              // 단일 및 복수 감면 유형별 입력 정보
              discounts,

              optional_lighting_minutes:
                Number(optionalLightingMinutes),

              // 취소 조건을 선택한 경우에만 전달
              ...(cancellation
                ? { cancellation }
                : {}),

              source,
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

          return response.results.map(
            (result) => ({
              ...result,
              selected_date: date,
              selected_start_time:
                selectedStart,
              selected_end_time:
                selectedEnd,
            })
          )
        })
      )

      if (
        requestId !== compareRequest.current
      ) {
        return
      }

      setResults(responses.flat())

      setTimeout(() => {
        if (
          requestId !== compareRequest.current
        ) {
          return
        }

        document
          .getElementById('results')
          ?.scrollIntoView({
            behavior: 'smooth',
          })
      }, 100)
    } catch (err) {
      if (
        requestId !== compareRequest.current
      ) {
        return
      }

      const normalizedErrors =
        normalizeFieldErrors(err.fields)

      setFieldErrors(normalizedErrors)

      setCompareError(
        getAPIErrorMessage(
          err,
          normalizedErrors,
          '시설 비교 중 오류가 발생했습니다.',
          discountTypes
        )
      )
    } finally {
      if (
        requestId === compareRequest.current
      ) {
        setLoading(false)
      }
    }
  }

  // 검색 결과와 상세조회 정보를 비교 결과에 전달
  const comparisonFacilities =
    searchResults.map((facility) => ({
      ...facility,
      bookingUrl:
        facilityDetails[facility.id]?.booking_url ??
        facility.bookingUrl ??
        facility.booking_url,
    }))

  return (
    <>
      <Header />
      <HeroBanner />

      <main className="main-container">
        <NaturalLanguageInput
          options={{
            ...options,
            districts: BUSAN_DISTRICTS,
          }}
          onApply={handleApplyAI}
          onDirectInput={handleDirectInput}
          optionsLoading={optionsLoading}
          optionsError={optionsError}
        />

        <div style={{ height: '28px' }} />

        <SearchForm
          sport={sport}
          setSport={setSport}

          options={{
            ...options,
            districts: [
              ...new Set([
                ...options.districts,
                ...districts,
              ]),
            ],
          }}

          optionsLoading={optionsLoading}
          optionsError={optionsError}
          onRetryOptions={retryOptions}

          district={district}
          setDistrict={handleDistrictChange}
          selectedDistricts={districts}

          date={date}
          setDate={handleDateChange}

          startTime={startTime}
          setStartTime={setStartTime}

          endTime={endTime}
          setEndTime={setEndTime}

          people={people}
          setPeople={setPeople}

          discountType={discountType}
          setDiscountType={handleDiscountChange}
          selectedDiscounts={discountTypes}

          eligibleCount={eligibleCount}
          setEligibleCount={setEligibleCount}

          representativeEligible={
            representativeEligible
          }

          setRepresentativeEligible={
            setRepresentativeEligible
          }

          discountDetails={discountDetails}
          setDiscountDetails={setDiscountDetails}

          optionalLightingMinutes={
            optionalLightingMinutes
          }

          setOptionalLightingMinutes={
            setOptionalLightingMinutes
          }

          cancellationReason={
            cancellationReason
          }

          setCancellationReason={
            handleCancellationReasonChange
          }

          cancelDate={cancelDate}

          setCancelDate={
            handleCancelDateChange
          }

          onSearch={handleSearch}
          loading={searching || loading}
          error={error}
          fieldErrors={fieldErrors}

          clearResult={() => {
            setSource('direct')
            clearResult()
          }}
        />

        <FacilityList
          facilities={searchResults}
          alternatives={alternatives}
          selectedIds={selectedIds}
          onToggle={toggleFacility}
          searched={searched}
          onCompare={handleCompare}
          loading={loading}
          facilityTimes={facilityTimes}
          onTimeChange={handleTimeChange}
          error={compareError}
          facilityDetails={facilityDetails}
          detailLoading={detailLoading}
          detailErrors={detailErrors}
          onRetryDetail={retryFacilityDetail}
        />

        <FeeResult
          results={results}
          facilities={comparisonFacilities}
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
              시설별 이용시간 및 예상요금은 확인된
              이용 규정을 기준으로 제공됩니다.
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