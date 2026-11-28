const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');

const app = fs.readFileSync(
  path.join(__dirname, '../src/App.jsx'),
  'utf8'
);

// App.jsx 내부 함수 추출
function handler(name) {
  const start = app.search(
    new RegExp(`  (?:async )?function ${name}\\(`)
  );

  assert.notEqual(
    start,
    -1,
    `Missing handler: ${name}`
  );

  const end =
    app.indexOf('\n  }', start) + '\n  }'.length;

  return app.slice(start, end);
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

  const end =
    app.indexOf('\n}', start) + '\n}'.length;

  return app.slice(start, end);
}

// App.jsx 취소 사유 상수 추출
const cancellationReasons = app.match(
  /const CANCELLATION_REASONS\s*=\s*\[[\s\S]*?\]/
);

assert.ok(
  cancellationReasons,
  'Missing CANCELLATION_REASONS'
);

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
    cancelDate: settings.cancelDate ?? '',
  };

  const pending = [];
  const timers = [];

  const create = new Function(
    'state',
    'pending',
    'timers',
    'settings',
    `
    const selectedIds = ['facility'];

    const facilityTimes = {
      facility: '10:00|12:00',
    };

    const sport = 'tennis';
    const districts = [];

    // 실행 날짜에 영향을 받지 않는 테스트 기준 날짜
    const date = settings.date ?? '2026-12-01';

    const getToday = () =>
      settings.today ?? '2026-11-28';

    const people = settings.people ?? '1';

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
        { code: 'tennis', label: '테니스' },
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

    const searchResults = [
      {
        id: 'facility',
        facility_id: 'facility',
        name: '테스트 시설',
        sport: 'tennis',
      },
    ];

    const facilityDetails = {
      facility: {
        facility_id: 'facility',
        time_options: [
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
        ],
      },
    };

    const detailLoading = {};
    const detailErrors = {};

    const searchRequest = { current: 0 };
    const compareRequest = { current: 0 };
    const detailRequests = { current: {} };

    const noop = () => {};

    const setSearching = noop;
    const setSearched = noop;
    const setSearchResults = noop;
    const setAlternatives = noop;
    const setSelectedIds = noop;
    const setFacilityTimes = noop;
    const setFacilityDetails = noop;
    const setDetailLoading = noop;
    const setDetailErrors = noop;
    const setError = noop;

    const validateConditions = () => '';

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
      state.fieldErrors =
        typeof value === 'function'
          ? value(state.fieldErrors)
          : value;
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

    ${[
      'isValidDate',
      'toMinutes',
      'getTimeOptions',
      'isBlockedFacility',
      'isValidFacilityTime',
      'normalizeFieldErrors',
    ].map(helper).join('\n')}

    ${[
      'resetComparison',
      'clearResult',
      'toggleFacility',
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
      handleTimeChange,
      handleCancellationReasonChange,
      handleCancelDateChange,
      handleCompare,
    };
    `
  );

  return {
    state,
    pending,
    timers,
    ...create(state, pending, timers, settings),
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
      f.state.error,
      /감면 대상 인원/
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
      f.state.error,
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
      /취소일을 입력/
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
      /지난 날짜/
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
      /취소일은 이용일보다 늦을 수 없습니다/
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

    // 변경된 취소 사유로 다시 비교
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

    // 변경된 취소일로 다시 비교
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

    const error = new Error(
      '입력한 이용조건을 확인해 주세요.'
    );

    error.status = 400;
    error.code = 'validation_error';

    error.fields = [
      {
        field: 'conditions.cancellation',
        code: 'invalid_cancellation',
        message: '취소 조건을 확인해 주세요.',
      },
    ];

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

    // 취소일을 수정하면 취소 관련 오류 초기화
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