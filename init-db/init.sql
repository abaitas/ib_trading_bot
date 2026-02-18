CREATE TABLE IF NOT EXISTS positions (

    id SERIAL PRIMARY KEY,

    account VARCHAR(20),

    con_id BIGINT,

    symbol VARCHAR(20),
    instrument VARCHAR(50),

    sec_type VARCHAR(10),

    expiry VARCHAR(20),
    strike DOUBLE PRECISION,

    multiplier VARCHAR(10),

    currency VARCHAR(10),
    exchange VARCHAR(20),

    size DOUBLE PRECISION,

    avg_cost DOUBLE PRECISION,
    market_price DOUBLE PRECISION,
    market_value DOUBLE PRECISION,

    unrealized_pnl DOUBLE PRECISION,
    realized_pnl DOUBLE PRECISION,

    recorded_at TIMESTAMP NOT NULL
);

