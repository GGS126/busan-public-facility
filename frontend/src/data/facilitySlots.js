
export const facilitySlots = {
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
export function getFacilitySlots(facilityId, timeOptions) {
  if (timeOptions?.selection === 'fixed_slot') {
    return timeOptions.slots.map(({ start_time, end_time }) => [start_time, end_time])
  }
  const config = facilitySlots[facilityId]

  if (!config) {
    return []
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
