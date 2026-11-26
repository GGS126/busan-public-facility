export const facilitySlots = {}

// 백엔드 API에서 제공한 시설 예약 회차 반환
export function getFacilitySlots(facilityId, timeOptions) {
  if (
    timeOptions?.selection === 'fixed_slot' &&
    Array.isArray(timeOptions.slots)
  ) {
    return timeOptions.slots.map(
      ({ start_time, end_time }) => [start_time, end_time]
    )
  }

  const config = facilitySlots[facilityId]

  if (!config) {
    return []
  }

  return []
}