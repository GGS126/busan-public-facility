
export const facilitySlots = {}

// 시설 ID와 이용 날짜에 맞는 시간 목록 반환
export function getFacilitySlots(facilityId, timeOptions) {
  if (timeOptions?.selection === 'fixed_slot') {
    return timeOptions.slots.map(({ start_time, end_time }) => [start_time, end_time])
  }
  const config = facilitySlots[facilityId]

  if (!config) {
    return []
  }


  return []
}
