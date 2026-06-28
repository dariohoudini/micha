"""
Chart of Accounts (doc CH1.1) — IFRS-aligned, AOA functional currency.

Each account: (code, name, type, normal_balance). Normal balance is the
side that *increases* the account: assets/expenses = debit, liabilities/
equity/revenue = credit. This is the integrity backbone — a trial balance
that doesn't balance is a bug, not a business decision.
"""

ASSET = 'asset'
LIABILITY = 'liability'
EQUITY = 'equity'
REVENUE = 'revenue'
COST_OF_REVENUE = 'cost_of_revenue'
OPERATING_EXPENSE = 'operating_expense'
OTHER = 'other'

DEBIT = 'debit'
CREDIT = 'credit'

# (code, name, type, normal_balance)
CHART_OF_ACCOUNTS = [
    # ── Assets ──────────────────────────────────────────────────────
    ('1000', 'Cash — BAI Current Account', ASSET, DEBIT),
    ('1010', 'Cash — Atlântico Account', ASSET, DEBIT),
    ('1020', 'Cash — APPYPAY Settlement', ASSET, DEBIT),
    ('1030', 'Cash in Transit — COD', ASSET, DEBIT),
    ('1100', 'Accounts Receivable — Sellers', ASSET, DEBIT),
    ('1101', 'Accounts Receivable — Couriers', ASSET, DEBIT),
    ('1150', 'Allowance for Doubtful Accounts', ASSET, CREDIT),  # contra-asset
    ('1200', 'Prepaid Expenses', ASSET, DEBIT),
    ('1250', 'Input IVA Recoverable', ASSET, DEBIT),
    ('1400', 'Intangible Assets — MICHA Platform', ASSET, DEBIT),
    ('1450', 'Accumulated Amortisation — Platform', ASSET, CREDIT),  # contra
    # ── Liabilities ─────────────────────────────────────────────────
    ('2000', 'Escrow Liability — Buyer Funds', LIABILITY, CREDIT),
    ('2010', 'Wallet Liability — Buyer', LIABILITY, CREDIT),
    ('2020', 'Seller Payable', LIABILITY, CREDIT),
    ('2025', 'Courier Payable', LIABILITY, CREDIT),
    ('2030', 'IVA Payable', LIABILITY, CREDIT),
    ('2040', 'Refunds Payable', LIABILITY, CREDIT),
    ('2050', 'Dispute Reserve', LIABILITY, CREDIT),
    ('2060', 'COD Clearing', LIABILITY, CREDIT),
    ('2099', 'Accrued Liabilities', LIABILITY, CREDIT),
    ('2100', 'Deferred Revenue — Annual Fees', LIABILITY, CREDIT),
    ('2110', 'Ad Credits (Deferred)', LIABILITY, CREDIT),
    ('2200', 'Salaries Payable', LIABILITY, CREDIT),
    ('2300', 'Loans Payable — Shareholders', LIABILITY, CREDIT),
    ('2400', 'Expense Claims Payable', LIABILITY, CREDIT),
    ('2500', 'Income Tax Payable', LIABILITY, CREDIT),
    ('2510', 'IRPC Withholding Payable', LIABILITY, CREDIT),
    ('2999', 'Suspense Clearing', LIABILITY, CREDIT),
    # ── Equity ──────────────────────────────────────────────────────
    ('3000', 'Share Capital', EQUITY, CREDIT),
    ('3010', 'Retained Earnings', EQUITY, CREDIT),
    ('3020', 'Share Premium', EQUITY, CREDIT),
    # ── Revenue ─────────────────────────────────────────────────────
    ('4000', 'Commission Revenue', REVENUE, CREDIT),
    ('4010', 'Annual Fee Revenue', REVENUE, CREDIT),
    ('4020', 'Advertising Revenue', REVENUE, CREDIT),
    ('4030', 'Delivery Fee Revenue', REVENUE, CREDIT),
    ('4040', 'COD Fee Revenue', REVENUE, CREDIT),
    ('4990', 'Provision Release (Other Income)', REVENUE, CREDIT),
    # ── Cost of Revenue ─────────────────────────────────────────────
    ('5000', 'PSP Processing Fees', COST_OF_REVENUE, DEBIT),
    ('5010', 'Logistics & Courier Cost', COST_OF_REVENUE, DEBIT),
    ('5020', 'Fraud Losses', COST_OF_REVENUE, DEBIT),
    ('5030', 'Refund Cost (platform-absorbed)', COST_OF_REVENUE, DEBIT),
    # ── Operating Expense ───────────────────────────────────────────
    ('6000', 'Salaries & Benefits', OPERATING_EXPENSE, DEBIT),
    ('6010', 'Technology Infrastructure', OPERATING_EXPENSE, DEBIT),
    ('6011', 'Amortisation — MICHA Platform', OPERATING_EXPENSE, DEBIT),
    ('6020', 'Marketing & Promotions', OPERATING_EXPENSE, DEBIT),
    ('6030', 'Bad Debt Expense', OPERATING_EXPENSE, DEBIT),
    ('6500', 'Income Tax Expense', OPERATING_EXPENSE, DEBIT),
    # ── Other Income / Expense ──────────────────────────────────────
    ('7000', 'FX Gain/Loss', OTHER, DEBIT),
    ('7010', 'Interest Income', OTHER, CREDIT),
    ('7100', 'Impairment Loss', OTHER, DEBIT),
    ('7200', 'Interest Expense', OTHER, DEBIT),
]

# Quick lookups
ACCOUNT_TYPE = {code: typ for code, _, typ, _ in CHART_OF_ACCOUNTS}
NORMAL_BALANCE = {code: nb for code, _, _, nb in CHART_OF_ACCOUNTS}
ACCOUNT_NAME = {code: name for code, name, _, _ in CHART_OF_ACCOUNTS}

# Statement groupings (doc CH24)
REVENUE_CODES = ['4000', '4010', '4020', '4030', '4040', '4990']
COR_CODES = ['5000', '5010', '5020', '5030']
OPEX_CODES = ['6000', '6010', '6011', '6020', '6030']
OTHER_CODES = ['7000', '7010', '7100', '7200']
ASSET_CODES = [c for c, _, t, _ in CHART_OF_ACCOUNTS if t == ASSET]
LIABILITY_CODES = [c for c, _, t, _ in CHART_OF_ACCOUNTS if t == LIABILITY]
EQUITY_CODES = [c for c, _, t, _ in CHART_OF_ACCOUNTS if t == EQUITY]
# Cash accounts for the liquidity-coverage check (doc CH4)
CASH_CODES = ['1000', '1010', '1020', '1030']
