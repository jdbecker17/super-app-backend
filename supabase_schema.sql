-- Create Institutions Table
CREATE TABLE IF NOT EXISTS institutions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT, -- Clearing code (e.g., 308 for XP, 102 for XP, etc.)
    country TEXT NOT NULL CHECK (country IN ('BR', 'US', 'Global')),
    logo_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create Assets Master Table (Global Directory)
CREATE TABLE IF NOT EXISTS assets_master (
    ticker TEXT PRIMARY KEY, -- PETR4, AAPL, IVVB11
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('stock_br', 'stock_us', 'reit', 'fii', 'etf_br', 'etf_us', 'crypto', 'bond')),
    currency TEXT NOT NULL CHECK (currency IN ('BRL', 'USD')),
    exchange TEXT NOT NULL CHECK (exchange IN ('B3', 'NYSE', 'NASDAQ', 'CRYPTO')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create Transactions Table (Immutable Ledger)
CREATE TABLE IF NOT EXISTS transactions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL, -- Link to Auth User
    ticker TEXT NOT NULL REFERENCES assets_master(ticker),
    institution_id UUID REFERENCES institutions(id),
    type TEXT NOT NULL CHECK (type IN ('BUY', 'SELL')),
    date TIMESTAMP WITH TIME ZONE NOT NULL,
    quantity NUMERIC NOT NULL,
    price NUMERIC NOT NULL, -- Unit Price
    fees NUMERIC DEFAULT 0, -- Total Fees (Brokerage + Exchange)
    total NUMERIC NOT NULL, -- (Price * Qty) + Fees (if Buy) or - Fees (if Sell)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- RLS Policies (Security)
ALTER TABLE institutions ENABLE ROW LEVEL SECURITY;
ALTER TABLE assets_master ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;

-- Allow Read Access to Everyone (Public Directory)
CREATE POLICY "Public Read Institutions" ON institutions FOR SELECT USING (true);
CREATE POLICY "Public Read Assets Master" ON assets_master FOR SELECT USING (true);

-- Allow Users to Manage their OWN Transactions
CREATE POLICY "Users Manage Own Transactions" ON transactions
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Indexes for Performance
CREATE INDEX idx_assets_type ON assets_master(type);
CREATE INDEX idx_transactions_user_date ON transactions(user_id, date);
