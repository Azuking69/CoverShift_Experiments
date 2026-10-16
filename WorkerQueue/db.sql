-- 案件（シフト1件）。state が「いまどの段階か」
-- NOT EXISTS: 既に存在する場合は何もしない
CREATE TABLE IF NOT EXISTS cases (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'collecting',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 予約表（スケジューラーが見る）。「この時刻に、この案件へ、この合図を出す」
CREATE TABLE IF NOT EXISTS schedules (
    id      SERIAL PRIMARY KEY,
    -- REFERENCES: 外部キー制約。cases.id が存在しない場合はエラーになる
    case_id INT NOT NULL REFERENCES cases(id),
    event   TEXT NOT NULL,
    fire_at TIMESTAMPTZ NOT NULL,
    fired   BOOLEAN NOT NULL DEFAULT false
);

-- 仕事リスト（キュー）。status: waiting / processing / done
CREATE TABLE IF NOT EXISTS queue (
    id         SERIAL PRIMARY KEY,
    case_id    INT NOT NULL REFERENCES cases(id),
    event      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'waiting',
    locked_at  TIMESTAMPTZ,            -- ワーカーが取った時刻
    done_at    TIMESTAMPTZ,            -- 処理が終わった時刻
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
