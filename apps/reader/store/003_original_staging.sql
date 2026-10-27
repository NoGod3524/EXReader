-- SPDX-License-Identifier: MIT
-- Existing v2 books remain visible: their provenance cannot be reconstructed.
BEGIN IMMEDIATE;
CREATE TEMP TABLE reader_migration_guard(ok INTEGER NOT NULL CHECK(ok=1));
INSERT INTO reader_migration_guard SELECT CASE WHEN
 (SELECT application_id FROM pragma_application_id)=1163416144 AND
 (SELECT user_version FROM pragma_user_version)=2 THEN 1 ELSE 0 END;
DROP TABLE reader_migration_guard;
ALTER TABLE reader_originals RENAME TO reader_originals_v2;
CREATE TABLE reader_originals(
 book_key TEXT PRIMARY KEY NOT NULL,
 storage_ref TEXT NOT NULL UNIQUE CHECK(typeof(storage_ref)='text' AND length(storage_ref) BETWEEN 1 AND 1024 AND instr(storage_ref,char(0))=0),
 state TEXT NOT NULL CHECK(state IN('staged','ready','deleting'))
);
INSERT INTO reader_originals SELECT book_key,storage_ref,state FROM reader_originals_v2;
DROP TABLE reader_originals_v2;
CREATE TABLE reader_original_pending(
 book_key TEXT PRIMARY KEY NOT NULL REFERENCES reader_originals(book_key) ON DELETE CASCADE,
 format TEXT NOT NULL, source_sha256 TEXT NOT NULL, source_bytes INTEGER NOT NULL,
 title TEXT NOT NULL, author TEXT NOT NULL, sort_title TEXT NOT NULL, favorite INTEGER NOT NULL
);
PRAGMA user_version=3;
COMMIT;
