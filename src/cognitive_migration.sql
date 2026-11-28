CREATE TABLE cognitive_assessments (
    id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL
        REFERENCES profiles(id)
        ON DELETE CASCADE,

    instrument_id TEXT NOT NULL
        DEFAULT 'legacy_cognitive_assessment',

    instrument_version INTEGER NOT NULL
        CHECK (instrument_version > 0),

    session_version INTEGER NOT NULL
        CHECK (session_version > 0),

    blueprint_version INTEGER NOT NULL
        CHECK (blueprint_version > 0),

    bank_id TEXT NOT NULL,
    form_id TEXT NOT NULL,

    form_manifest JSONB NOT NULL
        CHECK (jsonb_typeof(form_manifest) = 'object'),

    administration_protocol JSONB NOT NULL
        CHECK (
            jsonb_typeof(administration_protocol)
            = 'object'
        ),

    status TEXT NOT NULL
        CHECK (
            status IN (
                'ready',
                'memorize',
                'respond',
                'answered',
                'completed',
                'interrupted',
                'abandoned'
            )
        ),

    session_state JSONB NOT NULL
        CHECK (jsonb_typeof(session_state) = 'object'),

    revision BIGINT NOT NULL DEFAULT 0
        CHECK (revision >= 0),

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_utc TIMESTAMPTZ,

    UNIQUE (id, profile_id),

    CHECK (
        (status = 'completed')
        = (completed_utc IS NOT NULL)
    )
);


CREATE TABLE cognitive_assessment_items (
    assessment_id TEXT NOT NULL
        REFERENCES cognitive_assessments(id)
        ON DELETE CASCADE,

    block_index INTEGER NOT NULL
        CHECK (block_index >= 0),

    item_index INTEGER NOT NULL
        CHECK (item_index >= 0),

    item_id TEXT NOT NULL,
    presentation_id TEXT NOT NULL,
    question_id TEXT NOT NULL,
    exposure_hash TEXT NOT NULL,

    domain TEXT NOT NULL
        CHECK (
            domain IN (
                'fluid_reasoning',
                'visual_spatial',
                'verbal_comprehension',
                'quantitative_reasoning',
                'working_memory',
                'processing_speed'
            )
        ),

    family TEXT NOT NULL,

    programmed_difficulty INTEGER NOT NULL
        CHECK (
            programmed_difficulty BETWEEN 1 AND 5
        ),

    item_record JSONB NOT NULL
        CHECK (jsonb_typeof(item_record) = 'object'),

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        assessment_id,
        block_index,
        item_index
    ),

    UNIQUE (assessment_id, item_id),
    UNIQUE (assessment_id, question_id),
    UNIQUE (assessment_id, exposure_hash)
);


CREATE TABLE cognitive_responses (
    assessment_id TEXT NOT NULL,

    block_index INTEGER NOT NULL,
    item_index INTEGER NOT NULL,

    outcome TEXT NOT NULL
        CHECK (
            outcome IN (
                'correct',
                'incorrect',
                'timed_out',
                'not_reached'
            )
        ),

    selected_option_id TEXT,
    correct BOOLEAN,

    presented_ms BIGINT
        CHECK (presented_ms >= 0),

    response_started_ms BIGINT
        CHECK (response_started_ms >= 0),

    recorded_ms BIGINT NOT NULL
        CHECK (recorded_ms >= 0),

    response_latency_ms BIGINT
        CHECK (response_latency_ms >= 0),

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (
        assessment_id,
        block_index,
        item_index
    ),

    FOREIGN KEY (
        assessment_id,
        block_index,
        item_index
    )
    REFERENCES cognitive_assessment_items (
        assessment_id,
        block_index,
        item_index
    )
    ON DELETE CASCADE,

    CHECK (
        (
            outcome = 'correct'
            AND correct IS TRUE
            AND selected_option_id IS NOT NULL
        )
        OR
        (
            outcome = 'incorrect'
            AND correct IS FALSE
            AND selected_option_id IS NOT NULL
        )
        OR
        (
            outcome IN ('timed_out', 'not_reached')
            AND correct IS NULL
            AND selected_option_id IS NULL
        )
    ),

    CHECK (
        (
            outcome = 'not_reached'
            AND presented_ms IS NULL
            AND response_started_ms IS NULL
        )
        OR
        (
            outcome <> 'not_reached'
            AND presented_ms IS NOT NULL
        )
    ),

    CHECK (
        presented_ms IS NULL
        OR presented_ms <= recorded_ms
    ),

    CHECK (
        response_started_ms IS NULL
        OR (
            presented_ms IS NOT NULL
            AND response_started_ms >= presented_ms
            AND response_started_ms <= recorded_ms
        )
    ),

    CHECK (
        (
            outcome IN ('correct', 'incorrect')
            AND response_started_ms IS NOT NULL
            AND response_latency_ms IS NOT NULL
            AND response_latency_ms =
                recorded_ms - response_started_ms
        )
        OR
        (
            outcome IN ('timed_out', 'not_reached')
            AND response_latency_ms IS NULL
        )
    )
);


CREATE TABLE cognitive_administration_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    assessment_id TEXT NOT NULL
        REFERENCES cognitive_assessments(id)
        ON DELETE CASCADE,

    event_type TEXT NOT NULL
        CHECK (
            event_type IN (
                'assessment_created',
                'block_started',
                'item_presented',
                'memory_exposure_completed',
                'response_recorded',
                'block_completed',
                'assessment_interrupted',
                'assessment_completed',
                'assessment_abandoned'
            )
        ),

    block_index INTEGER
        CHECK (block_index >= 0),

    item_index INTEGER
        CHECK (item_index >= 0),

    event_ms BIGINT NOT NULL
        CHECK (event_ms >= 0),

    event_data JSONB NOT NULL DEFAULT '{}'
        CHECK (jsonb_typeof(event_data) = 'object'),

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE cognitive_assessment_results (
    assessment_id TEXT PRIMARY KEY,

    profile_id TEXT NOT NULL,

    scoring_version INTEGER NOT NULL
        CHECK (scoring_version > 0),

    reporting_status TEXT NOT NULL
        DEFAULT 'experimental_raw'
        CHECK (
            reporting_status IN (
                'experimental_raw',
                'provisional_estimate',
                'validated_norm_referenced'
            )
        ),

    domain_results JSONB NOT NULL
        CHECK (jsonb_typeof(domain_results) = 'object'),

    estimated_iq NUMERIC(7,2)
        CHECK (estimated_iq > 0),

    iq_interval_lower NUMERIC(7,2),
    iq_interval_upper NUMERIC(7,2),

    population_percentile NUMERIC(7,4)
        CHECK (
            population_percentile BETWEEN 0 AND 100
        ),

    scoring_methodology JSONB NOT NULL
        CHECK (
            jsonb_typeof(scoring_methodology)
            = 'object'
        ),

    reference_distribution_id TEXT,

    scientifically_validated BOOLEAN NOT NULL
        DEFAULT FALSE,

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (assessment_id, profile_id),

    FOREIGN KEY (assessment_id, profile_id)
        REFERENCES cognitive_assessments(id, profile_id)
        ON DELETE CASCADE,

    CHECK (
        (
            reporting_status = 'experimental_raw'
            AND estimated_iq IS NULL
            AND population_percentile IS NULL
            AND iq_interval_lower IS NULL
            AND iq_interval_upper IS NULL
            AND scientifically_validated IS FALSE
        )
        OR
        (
            reporting_status = 'provisional_estimate'
            AND estimated_iq IS NOT NULL
            AND reference_distribution_id IS NOT NULL
            AND scientifically_validated IS FALSE
        )
        OR
        (
            reporting_status = 'validated_norm_referenced'
            AND estimated_iq IS NOT NULL
            AND reference_distribution_id IS NOT NULL
            AND scientifically_validated IS TRUE
        )
    ),

    CHECK (
        (
            iq_interval_lower IS NULL
            AND iq_interval_upper IS NULL
        )
        OR
        (
            iq_interval_lower IS NOT NULL
            AND iq_interval_upper IS NOT NULL
            AND estimated_iq IS NOT NULL
            AND iq_interval_lower > 0
            AND iq_interval_lower <= estimated_iq
            AND iq_interval_upper >= estimated_iq
        )
    )
);


CREATE TABLE cognitive_preferences (
    profile_id TEXT PRIMARY KEY
        REFERENCES profiles(id)
        ON DELETE CASCADE,

    model_integration_enabled BOOLEAN NOT NULL
        DEFAULT FALSE,

    model_assessment_id TEXT,

    display_on_home BOOLEAN NOT NULL
        DEFAULT FALSE,

    display_on_cognitive_page BOOLEAN NOT NULL
        DEFAULT FALSE,

    display_assessment_id TEXT,

    model_consent_utc TIMESTAMPTZ,

    created_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_utc TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (
        model_assessment_id,
        profile_id
    )
    REFERENCES cognitive_assessment_results (
        assessment_id,
        profile_id
    )
    ON DELETE RESTRICT,

    FOREIGN KEY (
        display_assessment_id,
        profile_id
    )
    REFERENCES cognitive_assessment_results (
        assessment_id,
        profile_id
    )
    ON DELETE RESTRICT,

    CHECK (
        (
            model_integration_enabled IS TRUE
            AND model_assessment_id IS NOT NULL
            AND model_consent_utc IS NOT NULL
        )
        OR
        (
            model_integration_enabled IS FALSE
            AND model_assessment_id IS NULL
            AND model_consent_utc IS NULL
        )
    ),

    CHECK (
        (
            (display_on_home OR display_on_cognitive_page)
            AND display_assessment_id IS NOT NULL
        )
        OR
        (
            NOT display_on_home
            AND NOT display_on_cognitive_page
            AND display_assessment_id IS NULL
        )
    )
);


CREATE INDEX cognitive_assessments_profile_history_idx
    ON cognitive_assessments (
        profile_id,
        created_utc DESC
    );


CREATE UNIQUE INDEX cognitive_one_active_assessment_idx
    ON cognitive_assessments (profile_id)
    WHERE status IN (
        'ready',
        'memorize',
        'respond',
        'answered'
    );


CREATE INDEX cognitive_items_exposure_idx
    ON cognitive_assessment_items (exposure_hash);


CREATE INDEX cognitive_events_assessment_idx
    ON cognitive_administration_events (
        assessment_id,
        id
    );


CREATE INDEX cognitive_results_profile_history_idx
    ON cognitive_assessment_results (
        profile_id,
        created_utc DESC
    );
