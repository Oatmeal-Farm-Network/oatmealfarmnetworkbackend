-- Post-restore fixups for the cloned staging database.
-- A restored BAK carries prod's users as ORPHANED principals, so re-link the
-- app login and grant write roles. Run against the staging instance
-- (oatmeal-staging-sqlserver) as the 'sqlserver' root login.

USE [Oatmealailivedb];
GO

IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'oatmeal_app')
    ALTER USER [oatmeal_app] WITH LOGIN = [oatmeal_app];
ELSE
    CREATE USER [oatmeal_app] FOR LOGIN [oatmeal_app];
GO

ALTER ROLE db_datareader ADD MEMBER [oatmeal_app];
ALTER ROLE db_datawriter ADD MEMBER [oatmeal_app];
-- Grant db_ddladmin only if you want the routers' IF NOT EXISTS CREATE TABLE
-- ensure-blocks to be able to run (SKIP_SCHEMA_ENSURE=false):
ALTER ROLE db_ddladmin ADD MEMBER [oatmeal_app];
GO
