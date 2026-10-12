-- Runs once, when the database cluster is first created (docker-entrypoint-initdb.d).
-- Not named forge_*: the schema attestation fingerprints every forge_% role, so a forge_* name would break it.
-- The backup role can read every table (BYPASSRLS + pg_read_all_data) and can write nothing, so a leaked
-- backup credential cannot alter data. The password is read from the Docker secret, never from argv.
\set backup_password `cat /run/secrets/backup_reader`
CREATE ROLE backup_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS PASSWORD :'backup_password';
GRANT pg_read_all_data TO backup_reader;
GRANT CONNECT ON DATABASE :"DBNAME" TO backup_reader;  -- the migrations revoke CONNECT from PUBLIC
