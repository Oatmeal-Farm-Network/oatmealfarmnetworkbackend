-- Saige (supervisor graph) control-plane schema (Phase 1)
-- Apply against the farm SQL database when ready.
-- Localhost currently uses saige/data/saige_proposals.json until these tables exist.

IF OBJECT_ID('dbo.SaigeProposals', 'U') IS NULL
BEGIN
  CREATE TABLE dbo.SaigeProposals (
    ProposalID        UNIQUEIDENTIFIER NOT NULL PRIMARY KEY DEFAULT NEWID(),
    PeopleID          INT NULL,
    BusinessID        INT NULL,
    ThreadID          NVARCHAR(128) NOT NULL,
    ToolName          NVARCHAR(128) NOT NULL,
    ArgsJson          NVARCHAR(MAX) NULL,
    RiskClass         NVARCHAR(32) NOT NULL DEFAULT 'low_write',
    Domain            NVARCHAR(64) NULL,
    Summary           NVARCHAR(500) NULL,
    Status            NVARCHAR(32) NOT NULL DEFAULT 'pending', -- pending|approved|rejected|executed|failed
    DecidedBy         INT NULL,
    ExecutionResult   NVARCHAR(MAX) NULL,
    CreatedAt         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    UpdatedAt         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
  );
  CREATE INDEX IX_SaigeProposals_Business_Status ON dbo.SaigeProposals(BusinessID, Status);
  CREATE INDEX IX_SaigeProposals_Thread ON dbo.SaigeProposals(ThreadID);
END
GO

IF OBJECT_ID('dbo.SaigeProposalEvents', 'U') IS NULL
BEGIN
  CREATE TABLE dbo.SaigeProposalEvents (
    EventID           UNIQUEIDENTIFIER NOT NULL PRIMARY KEY DEFAULT NEWID(),
    ProposalID        UNIQUEIDENTIFIER NOT NULL,
    EventType         NVARCHAR(64) NOT NULL,
    MetaJson          NVARCHAR(MAX) NULL,
    CreatedAt         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_SaigeProposalEvents_Proposal FOREIGN KEY (ProposalID)
      REFERENCES dbo.SaigeProposals(ProposalID)
  );
END
GO

IF OBJECT_ID('dbo.SaigeSessions', 'U') IS NULL
BEGIN
  CREATE TABLE dbo.SaigeSessions (
    ThreadID          NVARCHAR(128) NOT NULL PRIMARY KEY,
    PeopleID          INT NULL,
    BusinessID        INT NULL,
    ActiveFieldID     INT NULL,
    ActiveAnimalID    INT NULL,
    Mode              NVARCHAR(32) NULL,
    UpdatedAt         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
  );
END
GO

IF OBJECT_ID('dbo.SaigeUserPreferences', 'U') IS NULL
BEGIN
  CREATE TABLE dbo.SaigeUserPreferences (
    PeopleID          INT NOT NULL PRIMARY KEY,
    PrefsJson         NVARCHAR(MAX) NULL,
    UpdatedAt         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
  );
END
GO

IF OBJECT_ID('dbo.SaigePlans', 'U') IS NULL
BEGIN
  CREATE TABLE dbo.SaigePlans (
    PlanID            UNIQUEIDENTIFIER NOT NULL PRIMARY KEY DEFAULT NEWID(),
    BusinessID        INT NOT NULL,
    PeopleID          INT NULL,
    Title             NVARCHAR(200) NOT NULL,
    Status            NVARCHAR(32) NOT NULL DEFAULT 'draft',
    CreatedAt         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    UpdatedAt         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
  );
END
GO

IF OBJECT_ID('dbo.SaigePlanItems', 'U') IS NULL
BEGIN
  CREATE TABLE dbo.SaigePlanItems (
    PlanItemID        UNIQUEIDENTIFIER NOT NULL PRIMARY KEY DEFAULT NEWID(),
    PlanID            UNIQUEIDENTIFIER NOT NULL,
    DueDate           DATE NULL,
    TaskText          NVARCHAR(500) NOT NULL,
    Domain            NVARCHAR(64) NULL,
    Status            NVARCHAR(32) NOT NULL DEFAULT 'open',
    CONSTRAINT FK_SaigePlanItems_Plan FOREIGN KEY (PlanID) REFERENCES dbo.SaigePlans(PlanID)
  );
END
GO

IF OBJECT_ID('dbo.SaigeMonitoringRuns', 'U') IS NULL
BEGIN
  CREATE TABLE dbo.SaigeMonitoringRuns (
    RunID             UNIQUEIDENTIFIER NOT NULL PRIMARY KEY DEFAULT NEWID(),
    BusinessID        INT NOT NULL,
    PeopleID          INT NULL,
    ThreadID          NVARCHAR(128) NULL,
    Summary           NVARCHAR(MAX) NULL,
    CreatedAt         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
  );
END
GO

IF OBJECT_ID('dbo.SaigeMonitoringFindings', 'U') IS NULL
BEGIN
  CREATE TABLE dbo.SaigeMonitoringFindings (
    FindingID         UNIQUEIDENTIFIER NOT NULL PRIMARY KEY DEFAULT NEWID(),
    RunID             UNIQUEIDENTIFIER NOT NULL,
    FieldID           INT NULL,
    RankScore         FLOAT NULL,
    FindingText       NVARCHAR(MAX) NULL,
    CONSTRAINT FK_SaigeMonitoringFindings_Run FOREIGN KEY (RunID)
      REFERENCES dbo.SaigeMonitoringRuns(RunID)
  );
END
GO
