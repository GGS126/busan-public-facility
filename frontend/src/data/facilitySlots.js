
export const facilitySlots = {
  busan_haeundae_arboretum_tennis: {
    type: 'fixed',
    slots: [],
    message: '예약 회차 정보를 확인 중입니다.',
  },

  busan_samrak_ecopark_tennis: {
    type: 'seasonal',
    periods: [
      {
        startDate: '2026-10-01',
        endDate: '2027-03-31',
        slots: [
          ['08:00', '10:00'],
          ['10:00', '12:00'],
          ['13:00', '15:00'],
          ['15:00', '17:00'],
        ],
      },
    ],
    message: '선택한 날짜에 적용되는 예약 회차 정보가 없습니다.',
  },

  busan_gudeok_stadium_tennis: {
    type: 'flexible',
    openTime: '08:00',
    closeTime: '22:00',
    durations: [60, 120],
    message: '',
  },
}

// 분 단위 시간을 HH:MM 형식으로 변환
function toTime(minutes) {
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60

  return `${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`
}

// 시설 ID와 이용 날짜에 맞는 시간 목록 반환
export function getFacilitySlots(facilityId, date) {
  const config = facilitySlots[facilityId]

  if (!config) {
    return []
  }

  if (config.type === 'fixed') {
    return config.slots
  }

  if (config.type === 'seasonal') {
    const period = config.periods.find(
      (item) => date >= item.startDate && date <= item.endDate
    )

    return period?.slots || []
  }

  if (config.type === 'flexible') {
    const slots = []
    const [openHour] = config.openTime.split(':').map(Number)
    const [closeHour] = config.closeTime.split(':').map(Number)

    for (
      let start = openHour * 60;
      start < closeHour * 60;
      start += 60
    ) {
      for (const duration of config.durations) {
        if (start + duration <= closeHour * 60) {
          slots.push([
            toTime(start),
            toTime(start + duration),
          ])
        }
      }
    }

    return slots
  }

  return []
}
