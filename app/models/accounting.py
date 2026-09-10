
# =============================================================================
# accounting.py
#
# Data models for the "accounting" domain of the Oatmeal Farm Network backend app.
# This file defines SQLAlchemy ORM classes mapping to accounting-related tables,
# including chart of accounts, journal entries, invoices, payments, bills, expenses,
# fiscal years, and other core double-entry bookkeeping objects.
#
# Imported by: main models.py and service layers.
# =============================================================================



from sqlalchemy import Column, Integer, String, DateTime, Date, Text
from sqlalchemy import Numeric as Decimal
from app.database import Base

# ── ACCOUNTING ───────────────────────────────────────────────────

class AccountType(Base):
    __tablename__ = "AccountTypes"
    AccountTypeID       = Column(Integer, primary_key=True, index=True)
    Name                = Column(String(100))
    NormalBalance       = Column(String(10))   # Debit or Credit
    FinancialStatement  = Column(String(50))   # Balance Sheet, Income Statement

class Account(Base):
    __tablename__ = "Accounts"
    AccountID       = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BusinessID      = Column(Integer, index=True)
    AccountTypeID   = Column(Integer)
    AccountNumber   = Column(String(20))
    AccountName     = Column(String(255))
    Description     = Column(Text, nullable=True)
    ParentAccountID = Column(Integer, nullable=True)
    IsActive        = Column(Integer, default=1)
    IsSystem        = Column(Integer, default=0)
    CreatedAt       = Column(DateTime)
    UpdatedAt       = Column(DateTime)

class JournalEntry(Base):
    __tablename__ = "JournalEntries"
    JournalEntryID = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BusinessID     = Column(Integer, index=True)
    EntryNumber    = Column(String(20))
    EntryDate      = Column(Date)
    Description    = Column(Text)
    Reference      = Column(String(100), nullable=True)
    SourceType     = Column(String(50), nullable=True)
    SourceID       = Column(Integer, nullable=True)
    IsPosted       = Column(Integer, default=1)
    CreatedBy      = Column(Integer)
    CreatedAt      = Column(DateTime)

class JournalEntryLine(Base):
    __tablename__ = "JournalEntryLines"
    JournalEntryLineID = Column(Integer, primary_key=True, index=True, autoincrement=True)
    JournalEntryID     = Column(Integer)
    BusinessID         = Column(Integer, index=True)
    AccountID          = Column(Integer)
    DebitAmount        = Column(Decimal(19, 2), default=0)
    CreditAmount       = Column(Decimal(19, 2), default=0)
    Description        = Column(Text, nullable=True)
    LineOrder          = Column(Integer)

class AccountingCustomer(Base):
    __tablename__ = "AccountingCustomers"
    CustomerID       = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BusinessID       = Column(Integer, index=True)
    DisplayName      = Column(String(255))
    CompanyName      = Column(String(255), nullable=True)
    FirstName        = Column(String(100), nullable=True)
    LastName         = Column(String(100), nullable=True)
    Email            = Column(String(255), nullable=True)
    Phone            = Column(String(50), nullable=True)
    BillingAddress1  = Column(String(255), nullable=True)
    BillingCity      = Column(String(100), nullable=True)
    BillingState     = Column(String(50), nullable=True)
    BillingZip       = Column(String(20), nullable=True)
    BillingCountry   = Column(String(50), default='US')
    PaymentTerms     = Column(String(50), default='Net30')
    StripeCustomerID = Column(String(255), nullable=True)
    Notes            = Column(Text, nullable=True)
    IsActive         = Column(Integer, default=1)
    CreatedAt        = Column(DateTime)
    UpdatedAt        = Column(DateTime)

class AccountingVendor(Base):
    __tablename__ = "AccountingVendors"
    VendorID     = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BusinessID   = Column(Integer, index=True)
    DisplayName  = Column(String(255))
    CompanyName  = Column(String(255), nullable=True)
    FirstName    = Column(String(100), nullable=True)
    LastName     = Column(String(100), nullable=True)
    Email        = Column(String(255), nullable=True)
    Phone        = Column(String(50), nullable=True)
    Address1     = Column(String(255), nullable=True)
    City         = Column(String(100), nullable=True)
    State        = Column(String(50), nullable=True)
    Zip          = Column(String(20), nullable=True)
    Country      = Column(String(50), default='US')
    PaymentTerms = Column(String(50), default='Net30')
    Is1099       = Column(Integer, default=0)
    Notes        = Column(Text, nullable=True)
    IsActive     = Column(Integer, default=1)
    CreatedAt    = Column(DateTime)
    UpdatedAt    = Column(DateTime)

class Item(Base):
    __tablename__ = "Items"
    ItemID            = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BusinessID        = Column(Integer, index=True)
    ItemType          = Column(String(50), default='Service')
    SKU               = Column(String(50), nullable=True)
    Name              = Column(String(255))
    Description       = Column(Text, nullable=True)
    SalePrice         = Column(Decimal(19, 2), default=0)
    PurchasePrice     = Column(Decimal(19, 2), default=0)
    SaleAccountID     = Column(Integer, nullable=True)
    PurchaseAccountID = Column(Integer, nullable=True)
    Taxable           = Column(Integer, default=1)
    IsActive          = Column(Integer, default=1)
    CreatedAt         = Column(DateTime)

class Invoice(Base):
    __tablename__ = "Invoices"
    InvoiceID          = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BusinessID         = Column(Integer, index=True)
    CustomerID         = Column(Integer)
    InvoiceNumber      = Column(String(20))
    InvoiceDate        = Column(Date)
    DueDate            = Column(Date)
    Status             = Column(String(20), default='Draft')
    SubTotal           = Column(Decimal(19, 2), default=0)
    TaxAmount          = Column(Decimal(19, 2), default=0)
    TotalAmount        = Column(Decimal(19, 2), default=0)
    AmountPaid         = Column(Decimal(19, 2), default=0)
    BalanceDue         = Column(Decimal(19, 2), default=0)
    JournalEntryID     = Column(Integer, nullable=True)
    TermsAndConditions = Column(Text, nullable=True)
    Notes              = Column(Text, nullable=True)
    PaymentTerms       = Column(String(50), nullable=True)
    CreatedBy          = Column(Integer)
    CreatedAt          = Column(DateTime)
    PaidAt             = Column(DateTime, nullable=True)
    UpdatedAt          = Column(DateTime)

class InvoiceLine(Base):
    __tablename__ = "InvoiceLines"
    InvoiceLineID = Column(Integer, primary_key=True, index=True, autoincrement=True)
    InvoiceID     = Column(Integer)
    BusinessID    = Column(Integer, index=True)
    ItemID        = Column(Integer, nullable=True)
    AccountID     = Column(Integer, nullable=True)
    Description   = Column(Text)
    Quantity      = Column(Decimal(19, 2))
    UnitPrice     = Column(Decimal(19, 2))
    TaxRateID     = Column(Integer, nullable=True)
    TaxAmount     = Column(Decimal(19, 2), default=0)
    LineTotal     = Column(Decimal(19, 2))
    LineOrder     = Column(Integer)

class Payment(Base):
    __tablename__ = "Payments"
    PaymentID             = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BusinessID            = Column(Integer, index=True)
    CustomerID            = Column(Integer)
    PaymentNumber         = Column(String(20))
    PaymentDate           = Column(Date)
    PaymentMethod         = Column(String(50))
    Amount                = Column(Decimal(19, 2))
    UnusedAmount          = Column(Decimal(19, 2), default=0)
    Reference             = Column(String(255), nullable=True)
    StripePaymentIntentID = Column(String(255), nullable=True)
    StripeChargeID        = Column(String(255), nullable=True)
    StripeFee             = Column(Decimal(19, 2), default=0)
    NetAmount             = Column(Decimal(19, 2))
    DepositAccountID      = Column(Integer, nullable=True)
    CreatedBy             = Column(Integer)
    CreatedAt             = Column(DateTime)

class PaymentApplication(Base):
    __tablename__ = "PaymentApplications"
    PaymentApplicationID = Column(Integer, primary_key=True, index=True, autoincrement=True)
    PaymentID            = Column(Integer)
    InvoiceID            = Column(Integer)
    BusinessID           = Column(Integer, index=True)
    AmountApplied        = Column(Decimal(19, 2))

class Bill(Base):
    __tablename__ = "Bills"
    BillID      = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BusinessID  = Column(Integer, index=True)
    VendorID    = Column(Integer)
    BillNumber  = Column(String(20), nullable=True)
    BillDate    = Column(Date)
    DueDate     = Column(Date)
    Status      = Column(String(20), default='Open')
    SubTotal    = Column(Decimal(19, 2), default=0)
    TaxAmount   = Column(Decimal(19, 2), default=0)
    TotalAmount = Column(Decimal(19, 2), default=0)
    AmountPaid  = Column(Decimal(19, 2), default=0)
    BalanceDue  = Column(Decimal(19, 2), default=0)
    Notes       = Column(Text, nullable=True)
    CreatedBy   = Column(Integer)
    CreatedAt   = Column(DateTime)

class BillLine(Base):
    __tablename__ = "BillLines"
    BillLineID  = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BillID      = Column(Integer)
    BusinessID  = Column(Integer, index=True)
    ItemID      = Column(Integer, nullable=True)
    AccountID   = Column(Integer, nullable=True)
    Description = Column(Text)
    Quantity    = Column(Decimal(19, 2))
    UnitPrice   = Column(Decimal(19, 2))
    TaxRateID   = Column(Integer, nullable=True)
    TaxAmount   = Column(Decimal(19, 2), default=0)
    LineTotal   = Column(Decimal(19, 2))
    LineOrder   = Column(Integer)

class Expense(Base):
    __tablename__ = "Expenses"
    ExpenseID        = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BusinessID       = Column(Integer, index=True)
    VendorID         = Column(Integer, nullable=True)
    PaymentAccountID = Column(Integer, nullable=True)
    ExpenseDate      = Column(Date)
    PaymentMethod    = Column(String(50))
    TotalAmount      = Column(Decimal(19, 2))
    Reference        = Column(String(255), nullable=True)
    Notes            = Column(Text, nullable=True)
    CreatedBy        = Column(Integer)
    CreatedAt        = Column(DateTime)

class ExpenseLine(Base):
    __tablename__ = "ExpenseLines"
    ExpenseLineID = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ExpenseID     = Column(Integer)
    BusinessID    = Column(Integer, index=True)
    AccountID     = Column(Integer)
    Description   = Column(Text)
    Amount        = Column(Decimal(19, 2))
    IsBillable    = Column(Integer, default=0)
    CustomerID    = Column(Integer, nullable=True)
    LineOrder     = Column(Integer)

class FiscalYear(Base):
    __tablename__ = "FiscalYears"
    FiscalYearID = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BusinessID   = Column(Integer, index=True)
    YearName     = Column(String(50))
    StartDate    = Column(Date)
    EndDate      = Column(Date)

class FiscalPeriod(Base):
    __tablename__ = "FiscalPeriods"
    FiscalPeriodID = Column(Integer, primary_key=True, index=True, autoincrement=True)
    FiscalYearID   = Column(Integer)
    BusinessID     = Column(Integer, index=True)
    PeriodNumber   = Column(Integer)
    PeriodName     = Column(String(50))
    StartDate      = Column(Date)
    EndDate        = Column(Date)
