// HH:MM 형식을 분 단위로 변환
export function toMinutes(time) {
  if (
    typeof time !== 'string' ||
    !/^\d{2}:\d{2}$/.test(time)
  ) {
    return null
  }

  const [hour, minute] = time.split(':').map(Number)

  if (
    hour > 24 ||
    minute > 59 ||
    (hour === 24 && minute !== 0)
  ) {
    return null
  }

  return hour * 60 + minute
}

// 이용 종목에 해당하는 시간 정책 추출
function normalizeTimeOptions(value, sport) {
  const options = Array.isArray(value)
    ? value
    : value && typeof value === 'object'
      ? [value]
      : []

  return options.filter(
    (option) =>
      option &&
      typeof option === 'object' &&
      (!option.sport || option.sport === sport)
  )
}

// 상세조회 및 검색 API의 시간 정책 통합
export function getTimeOptions(detail, facility, sport) {
  const detailOptions = normalizeTimeOptions(
    detail?.time_options,
    sport
  )

  // 상세정보의 시간 정책을 우선 사용
  if (detailOptions.length > 0) {
    return detailOptions
  }

  // 상세정보의 시간 정책이 비어 있으면 검색 결과 사용
  return normalizeTimeOptions(
    facility?.time_options,
    sport
  )
}

// 휴장 및 이용시간 규정 충돌 확인
export function isBlockedFacility(facility, detail) {
  return (
    facility?.closure?.is_closed === true ||
    detail?.closure?.is_closed === true ||
    facility?.slot_status === 'rule_conflict' ||
    detail?.slot_status === 'rule_conflict'
  )
}

// 시설별 이용시간 유효성 검증
export function isValidFacilityTime(
  detail,
  facility,
  sport,
  start,
  end
) {
  const startMinutes = toMinutes(start)
  const endMinutes = toMinutes(end)

  if (
    startMinutes === null ||
    endMinutes === null ||
    endMinutes <= startMinutes
  ) {
    return false
  }

  if (isBlockedFacility(facility, detail)) {
    return false
  }

  return getTimeOptions(
    detail,
    facility,
    sport
  ).some((option) => {
    // 고정 예약 회차
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

    // 자유시간 방식
    if (option.selection !== 'flexible') {
      return false
    }

    const duration = endMinutes - startMinutes

    // 운영 시작시간과 종료시간이 모두 있을 때만 검사
    if (
      option.open_time != null &&
      option.close_time != null
    ) {
      const open = toMinutes(option.open_time)
      const close = toMinutes(option.close_time)

      if (
        open === null ||
        close === null ||
        startMinutes < open ||
        endMinutes > close
      ) {
        return false
      }
    }

    // 최대 이용시간 검사
    if (
      Number.isInteger(option.max_minutes) &&
      duration > option.max_minutes
    ) {
      return false
    }

    // 허용 이용시간 검사
    if (
      Array.isArray(option.allowed_minutes) &&
      option.allowed_minutes.length > 0
    ) {
      return option.allowed_minutes.includes(duration)
    }

    return true
  })
}