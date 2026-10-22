-- 案件（シフト1件）。state が「いまどの段階か」
CREATE TABLE IF NOT EXISTS cases (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'collecting',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 予約表（スケジューラーが見る）。「この時刻に、この案件へ、この合図を出す」
CREATE TABLE IF NOT EXISTS schedules (
    id      SERIAL PRIMARY KEY,
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

-- 実行の記録（V2で追加）。グラフの各ステップが「何回始まったか」を数えるための表。
-- やり直しや二重実行があると、同じステップの行が2つ以上になる
CREATE TABLE IF NOT EXISTS node_runs (
    id         SERIAL PRIMARY KEY,
    case_id    INT NOT NULL,
    node       TEXT NOT NULL,
    worker     TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
