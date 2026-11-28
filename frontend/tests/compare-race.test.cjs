const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const app = fs.readFileSync(
  path.join(__dirname, '../src/App.jsx'),
  'utf8'
);

const timeModule = fs.readFileSync(
  path.join(
    __dirname,
    '../src/data/facilityTimeOptions.js'
  ),
  'utf8'
);

// 공통 시간 정책 모듈 불러오기
const timeHelpers = new Function(
  timeModule.replace(/^export\s+/gm, '') +
  `
  return {
    toMinutes,
    getTimeOptions,
    isBlockedFacility,
    isValidFacilityTime,
  };
  `
)();

// App.jsx 내부 함수 추출
function handler(name) {
  const start = app.search(
    new RegExp(`^  (?:async )?function ${name}\\(`, 'm')
  );

  assert.notEqual(
    start,
    -1,
    `Missing handler: ${name}`
  );

  const end = app.indexOf('\n  }', start);

  assert.notEqual(
    end,
    -1,
    `Missing handler end: ${name}`
  );

  return app.slice(
    start,
    end + '\n  }'.length
  );
}

// App.jsx 공통 함수 추출
function helper(name) {
  const start = app.search(
    new RegExp(`^function ${name}\\(`, 'm')
  );

  assert.notEqual(
    start,
    -1,
    `Missing helper: ${name}`
  );

  const end = app.indexOf('\n}', start);

  assert.notEqual(
    end,
    -1,
    `Missing helper end: ${name}`
  );

  return app.slice(
    start,
    end + '\n}'.length
  );
}

// App.jsx 취소 사유 상수 추출
const cancellationReasons = app.match(
  /const CANCELLATION_REASONS\s*=\s*\[[\s\S]*?\]/
);

assert.ok(
  cancellationReasons,
  'Missing CANCELLATION_REASONS'
);

// 시설 시간 정책 테스트 데이터
const fixedTimeOptions = [
  {
    sport: 'tennis',
    selection: 'fixed_slot',
    slots: [
      {
        start_time: '10:00',
        end_time: '12:00',
      },
    ],
  },
];

// 시설 상세정보 테스트 데이터
function detailResponse(timeOptions = fixedTimeOptions) {
  return {
    facility_id: 'facility',
    facility_name: '테스트 시설',
    time_options: timeOptions,
    booking_url: null,
  };
}

// 테스트 환경 구성
function fixture(settings = {}) {
  const state = {
    results: [],
    error: '',
    loading: false,
    scrolls: 0,
    fieldErrors: {},

    cancellationReason:
      settings.cancellationReason ?? 'none',

    cancelDate:
      settings.cancelDate ?? '',

    selectedIds:
      settings.selectedIds ?? ['facility'],

    facilityTimes:
      settings.facilityTimes ?? {
        facility: '10:00|12:00',
      },

    facilityDetails:
      settings.facilityDetails ?? {
        facility: detailResponse(),
      },

    detailLoading:
      settings.detailLoading ?? {},

    detailErrors:
      settings.detailErrors ?? {},
  };

  const pending = [];
  const detailPending = [];
  const timers = [];

  const create = new Function(
    'state',
    'pending',
    'detailPending',
    'timers',
    'settings',
    'timeHelpers',
    `
    const {
      toMinutes,
      getTimeOptions,
      isBlockedFacility,
      isValidFacilityTime,
    } = timeHelpers;

    let selectedIds = state.selectedIds;
    let facilityTimes = state.facilityTimes;
    let facilityDetails = state.facilityDetails;
    let detailLoading = state.detailLoading;
    let detailErrors = state.detailErrors;

    const sport = 'tennis';
    const districts = [];

    // 실행 날짜에 영향을 받지 않는 기준 날짜
    const date =
      settings.date ?? '2026-12-01';

    const getToday = () =>
      settings.today ?? '2026-11-28';

    const startTime =
      settings.startTime ?? '10:00';

    const endTime =
      settings.endTime ?? '12:00';

    const people =
      settings.people ?? '1';

    const discountTypes =
      settings.discountTypes ?? [];

    const eligibleCount =
      settings.eligibleCount ?? '0';

    const representativeEligible =
      settings.representativeEligible ?? false;

    const discountDetails =
      settings.discountDetails ?? {};

    const optionalLightingMinutes =
      settings.optionalLightingMinutes ?? '0';

    let cancellationReason =
      settings.cancellationReason ?? 'none';

    let cancelDate =
      settings.cancelDate ?? '';

    ${cancellationReasons[0]}

    const source = 'direct';

    const options = {
      sports: [
        {
          code: 'tennis',
          label: '테니스',
        },
      ],

      districts: [],

      discount_types: [
        {
          code: 'multi_child',
          label: '다자녀 가정',
        },
        {
          code: 'disabled',
          label: '장애인',
        },
      ],
    };

    let searchResults =
      settings.searchResults ?? [
        {
          id: 'facility',
          facility_id: 'facility',
          name: '테스트 시설',
          sport: 'tennis',
        },
      ];

    const searchRequest = {
      current: 0,
    };

    const compareRequest = {
      current: 0,
    };

    const detailRequests = {
      current: {},
    };

    const noop = () => {};

    const setSearching = noop;
    const setSearched = noop;
    const setAlternatives = noop;
    const setError = noop;

    const validateConditions = () => '';

    function applyValue(previous, value) {
      return typeof value === 'function'
        ? value(previous)
        : value;
    }

    const setSearchResults = value => {
      searchResults = applyValue(
        searchResults,
        value
      );
    };

    const setSelectedIds = value => {
      selectedIds = applyValue(
        selectedIds,
        value
      );

      state.selectedIds = selectedIds;
    };

    const setFacilityTimes = value => {
      facilityTimes = applyValue(
        facilityTimes,
        value
      );

      state.facilityTimes = facilityTimes;
    };

    const setFacilityDetails = value => {
      facilityDetails = applyValue(
        facilityDetails,
        value
      );

      state.facilityDetails = facilityDetails;
    };

    const setDetailLoading = value => {
      detailLoading = applyValue(
        detailLoading,
        value
      );

      state.detailLoading = detailLoading;
    };

    const setDetailErrors = value => {
      detailErrors = applyValue(
        detailErrors,
        value
      );

      state.detailErrors = detailErrors;
    };

    const setResults = value => {
      state.results = value;
    };

    const setCompareError = value => {
      state.error = value;
    };

    const setLoading = value => {
      state.loading = value;
    };

    const setFieldErrors = value => {
      state.fieldErrors = applyValue(
        state.fieldErrors,
        value
      );
    };

    const setCancellationReason = value => {
      cancellationReason = value;
      state.cancellationReason = value;
    };

    const setCancelDate = value => {
      cancelDate = value;
      state.cancelDate = value;
    };

    const setTimeout = fn => {
      timers.push(fn);
    };

    const document = {
      getElementById: () => ({
        scrollIntoView: () => {
          state.scrolls++;
        },
      }),
    };

    const compareFacilities = request =>
      new Promise((resolve, reject) => {
        pending.push({
          resolve,
          reject,
          request,
        });
      });

    const getFacilityDetail = (id, date) =>
      new Promise((resolve, reject) => {
        detailPending.push({
          resolve,
          reject,
          id,
          date,
        });
      });

    ${[
      'isValidDate',
      'validateFacilityDetail',
      'normalizeFieldErrors',
      'getAPIErrorMessage',
    ].map(helper).join('\n')}

    ${[
      'resetComparison',
      'clearResult',
      'loadFacilityDetail',
      'toggleFacility',
      'retryFacilityDetail',
      'handleTimeChange',
      'buildDiscounts',
      'validateDiscountConditions',
      'clearCancellationErrors',
      'handleCancellationReasonChange',
      'handleCancelDateChange',
      'validateCancellationConditions',
      'buildCancellation',
      'handleCompare',
    ].map(handler).join('\n')}

    return {
      clearResult,
      toggleFacility,
      retryFacilityDetail,
      handleTimeChange,
      handleCancellationReasonChange,
      handleCancelDateChange,
      handleCompare,
      normalizeFieldErrors,
      getAPIErrorMessage,
    };
    `
  );

  return {
    state,
    pending,
    detailPending,
    timers,

    ...create(
      state,
      pending,
      detailPending,
      timers,
      settings,
      timeHelpers
    ),
  };
}

// 비교 API 응답 예시
const response = id => ({
  results: [
    {
      facility_id: id,
      fee: {
        status: 'calculated',
      },
    },
  ],
});

// 백엔드 입력 검증 오류 예시
function validationError(fields) {
  const error = new Error(
    '입력한 이용조건을 확인해 주세요.'
  );

  error.status = 400;
  error.code = 'validation_error';
  error.fields = fields;

  return error;
}

// 1~3. 조건 변경 시 이전 비교 응답 무시
for (const change of [
  'clearResult',
  'toggleFacility',
  'handleTimeChange',
]) {
  test(
    `ignores old comparison after ${change}`,
    async () => {
      const f = fixture();

      const request = f.handleCompare();

      assert.equal(f.pending.length, 1);

      await f[change](
        'facility',
        '11:00|12:00'
      );

      f.pending[0].resolve(response('old'));

      await request;

      assert.deepEqual(f.state.results, []);
      assert.equal(f.state.loading, false);
    }
  );
}

// 4. 이전 요청 실패가 최신 요청에 영향을 주지 않는지 확인
test(
  'old failure cannot overwrite a new request or its loading state',
  async () => {
    const f = fixture();

    const first = f.handleCompare();
    const second = f.handleCompare();

    assert.equal(f.pending.length, 2);

    f.pending[0].reject(
      new Error('old error')
    );

    await first;

    assert.equal(f.state.error, '');
    assert.equal(f.state.loading, true);

    f.pending[1].resolve(response('new'));

    await second;

    assert.equal(
      f.state.results[0].facility_id,
      'new'
    );

    assert.equal(f.state.loading, false);
  }
);

// 5. 최신 비교 결과 유지
test(
  'newest result survives an older successful response',
  async () => {
    const f = fixture();

    const first = f.handleCompare();
    const second = f.handleCompare();

    assert.equal(f.pending.length, 2);

    f.pending[1].resolve(response('new'));

    await second;

    f.pending[0].resolve(response('old'));

    await first;

    assert.equal(
      f.state.results[0].facility_id,
      'new'
    );
  }
);

// 6. 무효화된 비교 요청의 화면 이동 방지
test(
  'invalidated comparison cannot scroll back to old results',
  async () => {
    const f = fixture();

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    f.pending[0].resolve(response('valid'));

    await request;

    assert.equal(f.timers.length, 1);

    f.clearResult();

    f.timers.forEach(fn => fn());

    assert.equal(f.state.scrolls, 0);
  }
);

// 7. 단일 감면 대상 인원 전달
test(
  'single discount sends the entered eligible count to the common engine',
  async () => {
    const f = fixture({
      discountTypes: ['multi_child'],
      eligibleCount: '1',
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    const conditions =
      f.pending[0].request.conditions;

    assert.deepEqual(
      conditions.discount_types,
      []
    );

    assert.deepEqual(
      conditions.discounts,
      [
        {
          type: 'multi_child',
          count: 1,
          holder: false,
        },
      ]
    );

    f.pending[0].resolve(response('valid'));

    await request;
  }
);

// 8. 복수 감면 유형에 임의의 대상 인원을 배정하지 않음
test(
  'multiple discount types are not assigned an invented per-type count',
  async () => {
    const f = fixture({
      discountTypes: [
        'multi_child',
        'disabled',
      ],

      eligibleCount: '1',
      discountDetails: {},
    });

    await f.handleCompare();

    assert.equal(f.pending.length, 0);

    assert.match(
      f.state.fieldErrors.discounts,
      /감면 대상 인원/
    );

    assert.match(
      f.state.error,
      /감면 입력 조건/
    );

    assert.deepEqual(f.state.results, []);
    assert.equal(f.state.loading, false);
  }
);

// 9. 복수 감면 유형별 입력값 전달
test(
  'multiple discounts send explicitly entered counts and holders',
  async () => {
    const f = fixture({
      people: '5',

      discountTypes: [
        'multi_child',
        'disabled',
      ],

      discountDetails: {
        multi_child: {
          count: '2',
          holder: true,
        },

        disabled: {
          count: '1',
          holder: false,
        },
      },
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    const conditions =
      f.pending[0].request.conditions;

    assert.equal(conditions.headcount, 5);

    assert.deepEqual(
      conditions.discount_types,
      []
    );

    assert.deepEqual(
      conditions.discounts,
      [
        {
          type: 'multi_child',
          count: 2,
          holder: true,
        },
        {
          type: 'disabled',
          count: 1,
          holder: false,
        },
      ]
    );

    f.pending[0].resolve(response('valid'));

    await request;
  }
);

// 10. 전체 이용 인원을 초과하는 감면 인원 차단
test(
  'discount count cannot exceed total headcount',
  async () => {
    const f = fixture({
      people: '2',
      discountTypes: ['disabled'],
      eligibleCount: '3',
    });

    await f.handleCompare();

    assert.equal(f.pending.length, 0);

    assert.match(
      f.state.fieldErrors.discounts,
      /감면 대상 인원/
    );

    assert.equal(f.state.loading, false);
  }
);

// 11. 예약 대표자의 감면 대상 여부 전달
test(
  'single discount sends representative eligibility',
  async () => {
    const f = fixture({
      people: '3',
      discountTypes: ['disabled'],
      eligibleCount: '2',
      representativeEligible: true,
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    assert.deepEqual(
      f.pending[0].request.conditions.discounts,
      [
        {
          type: 'disabled',
          count: 2,
          holder: true,
        },
      ]
    );

    f.pending[0].resolve(response('valid'));

    await request;
  }
);

// 12. 선택 조명 사용시간 전달
test(
  'optional lighting minutes are sent to the compare API',
  async () => {
    const f = fixture({
      optionalLightingMinutes: '60',
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    assert.equal(
      f.pending[0].request.conditions
        .optional_lighting_minutes,
      60
    );

    f.pending[0].resolve(response('valid'));

    await request;
  }
);

// 13. 시설 이용시간을 초과하는 조명 사용시간 차단
test(
  'optional lighting cannot exceed facility usage duration',
  async () => {
    const f = fixture({
      optionalLightingMinutes: '121',
    });

    await f.handleCompare();

    assert.equal(f.pending.length, 0);

    assert.match(
      f.state.error,
      /선택 조명 사용 시간/
    );

    assert.equal(f.state.loading, false);
  }
);

// 14. 취소 조건을 선택하지 않은 경우 필드 생략
test(
  'cancellation is omitted when no cancellation reason is selected',
  async () => {
    const f = fixture({
      cancellationReason: 'none',
      cancelDate: '',
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    const conditions =
      f.pending[0].request.conditions;

    assert.equal(
      Object.hasOwn(conditions, 'cancellation'),
      false
    );

    f.pending[0].resolve(response('valid'));

    await request;
  }
);

// 15. 사용자 취소 사유 및 취소일 전달
test(
  'user cancellation sends reason and cancellation date',
  async () => {
    const f = fixture({
      cancellationReason: 'user_cancel',
      cancelDate: '2026-11-29',
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    assert.deepEqual(
      f.pending[0].request.conditions.cancellation,
      {
        reason: 'user_cancel',
        cancel_date: '2026-11-29',
      }
    );

    f.pending[0].resolve(response('valid'));

    await request;
  }
);

// 16~18. 우천 및 불가항력 사유는 취소일 없이 전달
for (const reason of [
  'rain_same_day',
  'rain_unused',
  'force_majeure_or_city_event',
]) {
  test(
    `${reason} sends cancellation reason without a cancellation date`,
    async () => {
      const f = fixture({
        cancellationReason: reason,
        cancelDate: '',
      });

      const request = f.handleCompare();

      assert.equal(f.pending.length, 1);

      const cancellation =
        f.pending[0].request.conditions.cancellation;

      assert.deepEqual(
        cancellation,
        { reason }
      );

      assert.equal(
        Object.hasOwn(cancellation, 'cancel_date'),
        false
      );

      f.pending[0].resolve(response('valid'));

      await request;
    }
  );
}

// 19. 사용자 취소일 미입력 차단
test(
  'user cancellation requires a cancellation date',
  async () => {
    const f = fixture({
      cancellationReason: 'user_cancel',
      cancelDate: '',
    });

    await f.handleCompare();

    assert.equal(f.pending.length, 0);

    assert.match(
      f.state.error,
      /취소 및 미이용 환불 조건/
    );

    assert.match(
      f.state.fieldErrors.cancellation,
      /취소일을 입력/
    );

    assert.deepEqual(f.state.results, []);
    assert.equal(f.state.loading, false);
  }
);

// 20. 과거 취소일 입력 차단
test(
  'cancellation date cannot be earlier than today',
  async () => {
    const f = fixture({
      cancellationReason: 'user_cancel',
      cancelDate: '2026-11-27',
    });

    await f.handleCompare();

    assert.equal(f.pending.length, 0);

    assert.match(
      f.state.error,
      /취소 및 미이용 환불 조건/
    );

    assert.match(
      f.state.fieldErrors.cancellation,
      /지난 날짜/
    );

    assert.deepEqual(f.state.results, []);
    assert.equal(f.state.loading, false);
  }
);

// 21. 이용일 이후 취소일 입력 차단
test(
  'cancellation date cannot be later than the usage date',
  async () => {
    const f = fixture({
      cancellationReason: 'user_cancel',
      cancelDate: '2026-12-02',
    });

    await f.handleCompare();

    assert.equal(f.pending.length, 0);

    assert.match(
      f.state.error,
      /취소 및 미이용 환불 조건/
    );

    assert.match(
      f.state.fieldErrors.cancellation,
      /취소일은 이용일보다 늦을 수 없습니다/
    );

    assert.deepEqual(f.state.results, []);
    assert.equal(f.state.loading, false);
  }
);

// 22. 취소 사유 변경 시 이전 비교 응답 무효화
test(
  'changing cancellation reason invalidates old comparison and clears cancellation date',
  async () => {
    const f = fixture({
      cancellationReason: 'user_cancel',
      cancelDate: '2026-11-29',
    });

    const first = f.handleCompare();

    assert.equal(f.pending.length, 1);

    f.handleCancellationReasonChange(
      'rain_unused'
    );

    assert.equal(
      f.state.cancellationReason,
      'rain_unused'
    );

    assert.equal(f.state.cancelDate, '');
    assert.equal(f.state.loading, false);

    f.pending[0].resolve(response('old'));

    await first;

    assert.deepEqual(f.state.results, []);
    assert.equal(f.state.loading, false);
    assert.equal(f.timers.length, 0);

    const second = f.handleCompare();

    assert.equal(f.pending.length, 2);

    assert.deepEqual(
      f.pending[1].request.conditions.cancellation,
      {
        reason: 'rain_unused',
      }
    );

    f.pending[1].resolve(response('new'));

    await second;

    assert.equal(
      f.state.results[0].facility_id,
      'new'
    );
  }
);

// 23. 취소일 변경 시 이전 비교 응답 무효화
test(
  'changing cancellation date invalidates old comparison',
  async () => {
    const f = fixture({
      cancellationReason: 'user_cancel',
      cancelDate: '2026-11-29',
    });

    const first = f.handleCompare();

    assert.equal(f.pending.length, 1);

    f.handleCancelDateChange(
      '2026-11-30'
    );

    assert.equal(
      f.state.cancelDate,
      '2026-11-30'
    );

    assert.equal(f.state.loading, false);

    f.pending[0].resolve(response('old'));

    await first;

    assert.deepEqual(f.state.results, []);
    assert.equal(f.state.loading, false);
    assert.equal(f.timers.length, 0);

    const second = f.handleCompare();

    assert.equal(f.pending.length, 2);

    assert.deepEqual(
      f.pending[1].request.conditions.cancellation,
      {
        reason: 'user_cancel',
        cancel_date: '2026-11-30',
      }
    );

    f.pending[1].resolve(response('new'));

    await second;

    assert.equal(
      f.state.results[0].facility_id,
      'new'
    );
  }
);

// 24. 백엔드 취소 조건 오류를 입력 영역에 전달
test(
  'invalid cancellation API error is mapped to the cancellation field',
  async () => {
    const f = fixture({
      cancellationReason: 'user_cancel',
      cancelDate: '2026-11-29',
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    const error = validationError([
      {
        field: 'conditions.cancellation',
        code: 'invalid_cancellation',
        message: '취소 조건을 확인해 주세요.',
      },
    ]);

    f.pending[0].reject(error);

    await request;

    assert.equal(
      f.state.fieldErrors.cancellation,
      '취소 조건을 확인해 주세요.'
    );

    assert.match(
      f.state.error,
      /입력한 이용조건/
    );

    assert.deepEqual(f.state.results, []);
    assert.equal(f.state.loading, false);

    f.handleCancelDateChange(
      '2026-11-30'
    );

    assert.equal(
      f.state.fieldErrors.cancellation,
      undefined
    );

    assert.equal(f.state.error, '');
  }
);

// 25. 복수 감면 인원 합계가 전체 이용 인원을 초과하면 차단
test(
  'combined discount counts cannot exceed total headcount',
  async () => {
    const f = fixture({
      people: '3',

      discountTypes: [
        'multi_child',
        'disabled',
      ],

      discountDetails: {
        multi_child: {
          count: '2',
          holder: true,
        },

        disabled: {
          count: '2',
          holder: false,
        },
      },
    });

    await f.handleCompare();

    assert.equal(f.pending.length, 0);

    assert.match(
      f.state.fieldErrors.discounts,
      /합계는 전체 이용 인원을 초과/
    );

    assert.equal(f.state.loading, false);
  }
);

// 26. 여러 감면 유형에 대표자를 중복 포함하면 차단
test(
  'only one discount type may include the reservation holder',
  async () => {
    const f = fixture({
      people: '4',

      discountTypes: [
        'multi_child',
        'disabled',
      ],

      discountDetails: {
        multi_child: {
          count: '1',
          holder: true,
        },

        disabled: {
          count: '1',
          holder: true,
        },
      },
    });

    await f.handleCompare();

    assert.equal(f.pending.length, 0);

    assert.match(
      f.state.fieldErrors.discounts,
      /대표자는 하나의 감면 유형/
    );

    assert.equal(f.state.loading, false);
  }
);

// 27. 감면 인원 합계가 전체 이용 인원과 같으면 허용
test(
  'combined discount counts may equal total headcount',
  async () => {
    const f = fixture({
      people: '3',

      discountTypes: [
        'multi_child',
        'disabled',
      ],

      discountDetails: {
        multi_child: {
          count: '2',
          holder: true,
        },

        disabled: {
          count: '1',
          holder: false,
        },
      },
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    assert.deepEqual(
      f.pending[0].request.conditions.discounts,
      [
        {
          type: 'multi_child',
          count: 2,
          holder: true,
        },
        {
          type: 'disabled',
          count: 1,
          holder: false,
        },
      ]
    );

    f.pending[0].resolve(response('valid'));

    await request;
  }
);

// 28. 운영시간이 null인 자유시간 시설 비교 허용
test(
  'flexible time is valid when operating hours are unknown',
  () => {
    const detail = detailResponse([
      {
        sport: 'tennis',
        selection: 'flexible',
        open_time: null,
        close_time: null,
        max_minutes: 120,
      },
    ]);

    assert.equal(
      timeHelpers.isValidFacilityTime(
        detail,
        {},
        'tennis',
        '10:00',
        '12:00'
      ),
      true
    );
  }
);

// 29. 운영시간 미확인 상태에서도 최대 이용시간 제한 유지
test(
  'flexible time still enforces maximum duration without operating hours',
  () => {
    const detail = detailResponse([
      {
        sport: 'tennis',
        selection: 'flexible',
        open_time: null,
        close_time: null,
        max_minutes: 120,
      },
    ]);

    assert.equal(
      timeHelpers.isValidFacilityTime(
        detail,
        {},
        'tennis',
        '10:00',
        '13:00'
      ),
      false
    );
  }
);

// 30. 상세 시간 정책이 비어 있으면 검색 결과 정책 사용
test(
  'empty detail time options fall back to search result time options',
  () => {
    const detail = detailResponse([]);

    const facility = {
      time_options: fixedTimeOptions,
    };

    assert.deepEqual(
      timeHelpers.getTimeOptions(
        detail,
        facility,
        'tennis'
      ),
      fixedTimeOptions
    );

    assert.equal(
      timeHelpers.isValidFacilityTime(
        detail,
        facility,
        'tennis',
        '10:00',
        '12:00'
      ),
      true
    );
  }
);

// 31. 상세조회와 검색 결과 모두 시간 정책이 없으면 비교 제한
test(
  'missing time policies do not invent a flexible time policy',
  () => {
    const detail = detailResponse([]);

    const facility = {
      time_options: [],
    };

    assert.deepEqual(
      timeHelpers.getTimeOptions(
        detail,
        facility,
        'tennis'
      ),
      []
    );

    assert.equal(
      timeHelpers.isValidFacilityTime(
        detail,
        facility,
        'tennis',
        '10:00',
        '12:00'
      ),
      false
    );
  }
);

// 32. 상세조회에 유효한 시간 정책이 있으면 우선 적용
test(
  'detail time options take precedence over search result options',
  () => {
    const detailOptions = [
      {
        sport: 'tennis',
        selection: 'fixed_slot',
        slots: [
          {
            start_time: '14:00',
            end_time: '16:00',
          },
        ],
      },
    ];

    const detail = detailResponse(
      detailOptions
    );

    const facility = {
      time_options: fixedTimeOptions,
    };

    assert.deepEqual(
      timeHelpers.getTimeOptions(
        detail,
        facility,
        'tennis'
      ),
      detailOptions
    );

    assert.equal(
      timeHelpers.isValidFacilityTime(
        detail,
        facility,
        'tennis',
        '10:00',
        '12:00'
      ),
      false
    );

    assert.equal(
      timeHelpers.isValidFacilityTime(
        detail,
        facility,
        'tennis',
        '14:00',
        '16:00'
      ),
      true
    );
  }
);

// 33. 운영시간이 없는 자유시간 시설의 실제 비교 요청 허용
test(
  'comparison accepts flexible time with unknown operating hours',
  async () => {
    const f = fixture({
      facilityDetails: {
        facility: detailResponse([
          {
            sport: 'tennis',
            selection: 'flexible',
            open_time: null,
            close_time: null,
            max_minutes: 120,
          },
        ]),
      },
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    assert.equal(
      f.pending[0].request.conditions.start_time,
      '10:00'
    );

    assert.equal(
      f.pending[0].request.conditions.end_time,
      '12:00'
    );

    f.pending[0].resolve(response('valid'));

    await request;

    assert.equal(
      f.state.results[0].facility_id,
      'valid'
    );
  }
);

// 34. 상세 시간 정책이 비어 있어도 검색 결과 정책으로 비교
test(
  'comparison uses search time options when detail options are empty',
  async () => {
    const f = fixture({
      searchResults: [
        {
          id: 'facility',
          name: '테스트 시설',
          sport: 'tennis',
          time_options: fixedTimeOptions,
        },
      ],

      facilityDetails: {
        facility: detailResponse([]),
      },
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    f.pending[0].resolve(response('valid'));

    await request;

    assert.equal(
      f.state.results[0].facility_id,
      'valid'
    );
  }
);

// 35. 두 응답 모두 시간 정책이 없으면 비교 요청 차단
test(
  'comparison is blocked when both time policies are missing',
  async () => {
    const f = fixture({
      facilityDetails: {
        facility: detailResponse([]),
      },
    });

    await f.handleCompare();

    assert.equal(f.pending.length, 0);

    assert.match(
      f.state.error,
      /이용시간을 다시 선택/
    );
  }
);

// 36. 백엔드 전체 감면 조건 오류 연결
test(
  'invalid discount API error is mapped to the discount field',
  async () => {
    const f = fixture({
      people: '2',
      discountTypes: ['disabled'],
      eligibleCount: '1',
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    const error = validationError([
      {
        field: 'conditions',
        code: 'invalid_discount',
        message: '감면 조건을 확인해 주세요.',
      },
    ]);

    f.pending[0].reject(error);

    await request;

    assert.equal(
      f.state.fieldErrors.discounts,
      '감면 조건을 확인해 주세요.'
    );

    assert.equal(
      f.state.error,
      '입력한 이용조건을 확인해 주세요.'
    );

    assert.equal(f.state.loading, false);
  }
);

// 37. 단일 감면 인원 오류 필드 유지 및 중복 안내 방지
test(
  'single discount count error keeps its indexed field without duplicating the summary',
  async () => {
    const f = fixture({
      people: '2',
      discountTypes: ['disabled'],
      eligibleCount: '1',
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    const error = validationError([
      {
        field: 'conditions.discounts.0.count',
        code: 'invalid_discount',
        message: '감면 인원을 확인해 주세요.',
      },
    ]);

    f.pending[0].reject(error);

    await request;

    assert.equal(
      f.state.fieldErrors['discounts.0.count'],
      '감면 인원을 확인해 주세요.'
    );

    assert.equal(
      f.state.error,
      '입력한 이용조건을 확인해 주세요.'
    );

    assert.equal(f.state.loading, false);
  }
);

// 38. 단일 감면 대표자 오류 필드 유지
test(
  'single discount holder error keeps its indexed field',
  async () => {
    const f = fixture({
      people: '2',
      discountTypes: ['disabled'],
      eligibleCount: '1',
    });

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    const error = validationError([
      {
        field: 'conditions.discounts[0].holder',
        code: 'invalid_discount',
        message: '대표자 조건을 확인해 주세요.',
      },
    ]);

    f.pending[0].reject(error);

    await request;

    assert.equal(
      f.state.fieldErrors['discounts.0.holder'],
      '대표자 조건을 확인해 주세요.'
    );

    assert.equal(
      f.state.error,
      '입력한 이용조건을 확인해 주세요.'
    );
  }
);

// 39. 입력란에 연결되지 않는 오류는 상단 안내에 표시
test(
  'unmapped field errors remain visible in the error summary',
  async () => {
    const f = fixture();

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    const error = validationError([
      {
        field: 'conditions.unknown_field',
        code: 'validation_error',
        message: '추가 조건을 확인해 주세요.',
      },
    ]);

    f.pending[0].reject(error);

    await request;

    assert.equal(
      f.state.fieldErrors.unknown_field,
      '추가 조건을 확인해 주세요.'
    );

    assert.match(
      f.state.error,
      /추가 조건을 확인해 주세요/
    );
  }
);

// 40. 시설 상세정보 조회 실패 후 선택 상태 유지
test(
  'facility remains selected when detail loading fails',
  async () => {
    const f = fixture({
      selectedIds: [],
      facilityTimes: {},
      facilityDetails: {},
    });

    const request = f.toggleFacility(
      'facility'
    );

    assert.equal(f.detailPending.length, 1);

    assert.deepEqual(
      f.state.selectedIds,
      ['facility']
    );

    assert.equal(
      f.state.detailLoading.facility,
      true
    );

    f.detailPending[0].reject(
      new Error('상세정보 조회 실패')
    );

    await request;

    assert.deepEqual(
      f.state.selectedIds,
      ['facility']
    );

    assert.equal(
      f.state.detailErrors.facility,
      '상세정보 조회 실패'
    );

    assert.equal(
      f.state.detailLoading.facility,
      false
    );
  }
);

// 41. 상세정보 재시도 성공 후 비교 가능
test(
  'retrying facility detail restores comparison without deselecting the facility',
  async () => {
    const f = fixture({
      selectedIds: ['facility'],
      facilityTimes: {},
      facilityDetails: {},

      detailErrors: {
        facility: '상세정보 조회 실패',
      },
    });

    const retry = f.retryFacilityDetail(
      'facility'
    );

    assert.equal(f.detailPending.length, 1);

    assert.deepEqual(
      f.state.selectedIds,
      ['facility']
    );

    assert.equal(
      f.state.detailLoading.facility,
      true
    );

    assert.equal(
      f.state.detailErrors.facility,
      ''
    );

    f.detailPending[0].resolve(
      detailResponse()
    );

    await retry;

    assert.equal(
      f.state.detailLoading.facility,
      false
    );

    assert.equal(
      f.state.facilityDetails.facility.facility_id,
      'facility'
    );

    assert.equal(
      f.state.facilityTimes.facility,
      '10:00|12:00'
    );

    const request = f.handleCompare();

    assert.equal(f.pending.length, 1);

    f.pending[0].resolve(response('valid'));

    await request;

    assert.equal(
      f.state.results[0].facility_id,
      'valid'
    );
  }
);

// 42. 상세정보 재시도 실패 시 오류 다시 표시
test(
  'failed detail retry restores the detail error',
  async () => {
    const f = fixture({
      facilityTimes: {},
      facilityDetails: {},

      detailErrors: {
        facility: '첫 번째 오류',
      },
    });

    const retry = f.retryFacilityDetail(
      'facility'
    );

    assert.equal(f.detailPending.length, 1);

    f.detailPending[0].reject(
      new Error('재시도 실패')
    );

    await retry;

    assert.deepEqual(
      f.state.selectedIds,
      ['facility']
    );

    assert.equal(
      f.state.detailErrors.facility,
      '재시도 실패'
    );

    assert.equal(
      f.state.detailLoading.facility,
      false
    );
  }
);

// 43. 선택하지 않은 시설의 상세정보 재시도 차단
test(
  'detail retry is ignored for an unselected facility',
  async () => {
    const f = fixture({
      selectedIds: [],
    });

    await f.retryFacilityDetail(
      'facility'
    );

    assert.equal(f.detailPending.length, 0);
  }
);

// 44. 상세정보 조회 중 중복 재시도 차단
test(
  'detail retry is ignored while a detail request is pending',
  async () => {
    const f = fixture({
      detailLoading: {
        facility: true,
      },
    });

    await f.retryFacilityDetail(
      'facility'
    );

    assert.equal(f.detailPending.length, 0);
  }
);

// 45. 상세정보 조회 중 시설 선택 해제 시 이전 응답 무시
test(
  'old detail response is ignored after facility deselection',
  async () => {
    const f = fixture({
      selectedIds: [],
      facilityTimes: {},
      facilityDetails: {},
    });

    const request = f.toggleFacility(
      'facility'
    );

    assert.equal(f.detailPending.length, 1);

    await f.toggleFacility('facility');

    f.detailPending[0].resolve(
      detailResponse()
    );

    await request;

    assert.deepEqual(
      f.state.selectedIds,
      []
    );

    assert.equal(
      f.state.facilityDetails.facility,
      undefined
    );

    assert.equal(
      f.state.facilityTimes.facility,
      undefined
    );

    assert.equal(
      f.state.detailLoading.facility,
      undefined
    );
  }
);

// 46. 검색 조건 변경 후 이전 상세정보 응답 무시
test(
  'old detail response is ignored after search conditions change',
  async () => {
    const f = fixture({
      selectedIds: [],
      facilityTimes: {},
      facilityDetails: {},
    });

    const request = f.toggleFacility(
      'facility'
    );

    assert.equal(f.detailPending.length, 1);

    f.clearResult();

    f.detailPending[0].resolve(
      detailResponse()
    );

    await request;

    assert.deepEqual(
      f.state.selectedIds,
      []
    );

    assert.deepEqual(
      f.state.facilityDetails,
      {}
    );

    assert.deepEqual(
      f.state.facilityTimes,
      {}
    );

    assert.deepEqual(
      f.state.detailLoading,
      {}
    );
  }
);

// 47. 휴장 시설 비교 제한
test(
  'closed facilities cannot pass time validation',
  () => {
    const facility = {
      closure: {
        is_closed: true,
      },

      time_options: fixedTimeOptions,
    };

    assert.equal(
      timeHelpers.isBlockedFacility(
        facility,
        detailResponse()
      ),
      true
    );

    assert.equal(
      timeHelpers.isValidFacilityTime(
        detailResponse(),
        facility,
        'tennis',
        '10:00',
        '12:00'
      ),
      false
    );
  }
);

// 48. 이용시간 규정 충돌 시설 비교 제한
test(
  'facilities with conflicting rules cannot pass time validation',
  () => {
    const detail = {
      ...detailResponse(),
      slot_status: 'rule_conflict',
    };

    assert.equal(
      timeHelpers.isBlockedFacility(
        {},
        detail
      ),
      true
    );

    assert.equal(
      timeHelpers.isValidFacilityTime(
        detail,
        {},
        'tennis',
        '10:00',
        '12:00'
      ),
      false
    );
  }
);