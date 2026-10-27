-- SPDX-License-Identifier: MIT
-- Product catalog only. Preserve all v1 rows and SDK mappings.
BEGIN IMMEDIATE;
CREATE TEMP TABLE reader_migration_guard(ok INTEGER NOT NULL CHECK(ok=1));
INSERT INTO reader_migration_guard SELECT CASE WHEN
 (SELECT application_id FROM pragma_application_id)=1163416144 AND
 (SELECT user_version FROM pragma_user_version)=1 THEN 1 ELSE 0 END;
DROP TABLE reader_migration_guard;
CREATE TABLE reader_originals(
 book_key TEXT PRIMARY KEY NOT NULL REFERENCES reader_books(book_key),
 storage_ref TEXT NOT NULL UNIQUE CHECK(typeof(storage_ref)='text' AND length(storage_ref) BETWEEN 1 AND 1024 AND instr(storage_ref,char(0))=0),
 state TEXT NOT NULL CHECK(state IN('staged','ready','deleting'))
);
PRAGMA user_version=2;
COMMIT;
