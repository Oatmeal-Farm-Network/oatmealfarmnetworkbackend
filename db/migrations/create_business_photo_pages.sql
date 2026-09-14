-- Photo pages for a business directory listing.
-- Idempotent: safe to re-run.

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'BusinessPhotoPages')
BEGIN
    CREATE TABLE BusinessPhotoPages (
        BusinessPhotoPageID INT IDENTITY(1,1) PRIMARY KEY,
        BusinessID          INT NOT NULL,
        Title               NVARCHAR(120) NOT NULL,
        SortOrder           INT NOT NULL DEFAULT 0
    );
    CREATE INDEX IX_BusinessPhotoPages_BusinessID
        ON BusinessPhotoPages (BusinessID, SortOrder);
END
GO

IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'BusinessPhotos')
BEGIN
    CREATE TABLE BusinessPhotos (
        BusinessPhotoID     INT IDENTITY(1,1) PRIMARY KEY,
        BusinessID          INT NOT NULL,
        BusinessPhotoPageID INT NOT NULL,
        PhotoUrl            NVARCHAR(1024) NOT NULL,
        Caption             NVARCHAR(256) NULL,
        SortOrder           INT NOT NULL DEFAULT 0
    );
    CREATE INDEX IX_BusinessPhotos_Page
        ON BusinessPhotos (BusinessPhotoPageID, SortOrder);
    CREATE INDEX IX_BusinessPhotos_Business
        ON BusinessPhotos (BusinessID);
END
GO
