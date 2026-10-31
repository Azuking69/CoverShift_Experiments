-- 入り口: cases
-- 店舗の対象月の状態を管理する
CREATE TABLE IF NOT EXISTS cases(
    id           SERIAL PRIMARY KEY,
    store_id     INT NOT NULL,
    target_month TEXT NOT NULL,                      -- YYYY-MM
    state        TEXT NOT NULL DEFAULT 'collection', -- collection, draft, confirmed
    updated_at   TIMESTAMP NOT NULL DEFAULT now()
);


-- スケジューラー
-- 「この時刻に、この案件へ、この合図を出す」という予定を入れる表
CREATE TABLE IF NOT EXISTS scheduler(
    id           SERIAL PRIMARY KEY,                -- 予定のID
    case_id      INT NOT NULL REFERENCES cases(id), -- どの案件に対する予定か
    event        TEXT NOT NULL,                     -- どの合図を出す予定か
    fire_at      TIMESTAMPTZ NOT NULL,              -- いつ出す予定か
    fired        BOOLEAN NOT NULL DEFAULT false     -- 予定が実行されたかどうか
);


-- キュー
-- 「いますぐやる仕事」の票を、順番に並べる表(ワーカーはここから取る)
CREATE TABLE IF NOT EXISTS queue(
    id          SERIAL PRIMARY KEY,                 -- キューのID
    case_id     INT NOT NULL REFERENCES cases(id),  -- どの案件に対するキューか
    event       TEXT NOT NULL,                      -- どの合図を出す予定か
    status      TEXT NOT NULL DEFAULT 'waiting',    -- キューの状態
    locked_at   TIMESTAMPTZ,                        -- キューがロックされた時刻
    done_at     TIMESTAMPTZ,                        -- キューが完了した時刻
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()  -- キューが作成された時刻
);