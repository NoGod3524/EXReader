-- SPDX-License-Identifier: MIT
-- Product metadata only; never apply this migration to the SDK library.
PRAGMA foreign_keys=ON;
PRAGMA trusted_schema=OFF;
BEGIN IMMEDIATE;
CREATE TEMP TABLE reader_migration_guard(ok INTEGER NOT NULL CHECK(ok=1));
INSERT INTO reader_migration_guard
SELECT CASE WHEN (SELECT application_id FROM pragma_application_id)=0
  AND (SELECT user_version FROM pragma_user_version)=0
  AND NOT EXISTS(SELECT 1 FROM sqlite_master WHERE name NOT GLOB 'sqlite_*')
  THEN 1 ELSE 0 END;
DROP TABLE reader_migration_guard;

CREATE TABLE reader_books(
  book_key TEXT PRIMARY KEY NOT NULL CHECK(typeof(book_key)='text'),
  format TEXT NOT NULL CHECK(format IN('epub','pdf','cbz','txt','html','fb2','docx','rtf','mobi')),
  source_sha256 TEXT NOT NULL CHECK(typeof(source_sha256)='text' AND length(source_sha256)=64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'),
  source_bytes INTEGER NOT NULL CHECK(typeof(source_bytes)='integer' AND source_bytes>0),
  title TEXT NOT NULL CHECK(length(title)<=4096 AND instr(title,char(0))=0),
  author TEXT NOT NULL DEFAULT '' CHECK(length(author)<=4096 AND instr(author,char(0))=0),
  sort_title TEXT NOT NULL CHECK(length(sort_title)<=4096 AND instr(sort_title,char(0))=0),
  favorite INTEGER NOT NULL DEFAULT 0 CHECK(favorite IN(0,1)),
  deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN(0,1)),
  CHECK(book_key=format||':'||source_sha256)
);
CREATE INDEX reader_books_title ON reader_books(deleted,sort_title,book_key);
CREATE TRIGGER reader_books_no_replace BEFORE INSERT ON reader_books
WHEN EXISTS(SELECT 1 FROM reader_books WHERE book_key=NEW.book_key)
BEGIN SELECT RAISE(ABORT,'book identity already exists; update its metadata explicitly'); END;
CREATE TRIGGER reader_books_identity BEFORE UPDATE OF book_key,format,source_sha256,source_bytes ON reader_books
WHEN NEW.book_key<>OLD.book_key OR NEW.format<>OLD.format
  OR NEW.source_sha256<>OLD.source_sha256 OR NEW.source_bytes<>OLD.source_bytes
BEGIN SELECT RAISE(ABORT,'book source identity is immutable'); END;

-- One local SDK library belongs to each catalog. These IDs never go on the wire.
CREATE TABLE reader_local_books(
  book_key TEXT PRIMARY KEY NOT NULL REFERENCES reader_books(book_key),
  sdk_book_id INTEGER NOT NULL UNIQUE CHECK(typeof(sdk_book_id)='integer' AND sdk_book_id>0),
  location_kind TEXT NOT NULL CHECK(location_kind IN('epub_chapter','reflow_global','fixed_page'))
);
CREATE TRIGGER reader_local_books_format_insert BEFORE INSERT ON reader_local_books
WHEN NOT EXISTS(SELECT 1 FROM reader_books b WHERE b.book_key=NEW.book_key
  AND ((NEW.location_kind='fixed_page' AND b.format IN('pdf','cbz'))
    OR (NEW.location_kind='epub_chapter' AND b.format='epub')
    OR (NEW.location_kind='reflow_global' AND b.format NOT IN('pdf','cbz'))))
BEGIN SELECT RAISE(ABORT,'local location kind differs from book format'); END;
CREATE TRIGGER reader_local_books_format_update BEFORE UPDATE ON reader_local_books
WHEN NOT EXISTS(SELECT 1 FROM reader_books b WHERE b.book_key=NEW.book_key
  AND ((NEW.location_kind='fixed_page' AND b.format IN('pdf','cbz'))
    OR (NEW.location_kind='epub_chapter' AND b.format='epub')
    OR (NEW.location_kind='reflow_global' AND b.format NOT IN('pdf','cbz'))))
BEGIN SELECT RAISE(ABORT,'local location kind differs from book format'); END;

CREATE TABLE reader_shelves(
  shelf_id TEXT PRIMARY KEY NOT NULL CHECK(typeof(shelf_id)='text' AND length(shelf_id)=32 AND shelf_id NOT GLOB '*[^0-9a-f]*'),
  parent_id TEXT REFERENCES reader_shelves(shelf_id),
  name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 256 AND instr(name,char(0))=0),
  ordinal INTEGER NOT NULL DEFAULT 0 CHECK(typeof(ordinal)='integer' AND ordinal>=0),
  deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN(0,1))
);
CREATE INDEX reader_shelves_parent ON reader_shelves(parent_id,deleted,ordinal,shelf_id);
CREATE TRIGGER reader_shelves_identity BEFORE UPDATE OF shelf_id ON reader_shelves
WHEN NEW.shelf_id<>OLD.shelf_id
BEGIN SELECT RAISE(ABORT,'shelf identity is immutable'); END;
CREATE TRIGGER reader_shelves_insert BEFORE INSERT ON reader_shelves
BEGIN
  SELECT RAISE(ABORT,'shelf identity already exists; update its metadata explicitly')
    WHERE EXISTS(SELECT 1 FROM reader_shelves WHERE shelf_id=NEW.shelf_id);
  SELECT RAISE(ABORT,'shelf cycle') WHERE NEW.parent_id=NEW.shelf_id;
  SELECT RAISE(ABORT,'shelf depth exceeds eight') WHERE (
    WITH RECURSIVE ancestors(id,parent_id,depth) AS(
      SELECT shelf_id,parent_id,1 FROM reader_shelves WHERE shelf_id=NEW.parent_id
      UNION ALL SELECT s.shelf_id,s.parent_id,a.depth+1 FROM reader_shelves s
        JOIN ancestors a ON s.shelf_id=a.parent_id WHERE a.depth<8)
    SELECT coalesce(max(depth),0) FROM ancestors)>=8;
END;
CREATE TRIGGER reader_shelves_reparent BEFORE UPDATE OF parent_id ON reader_shelves
BEGIN
  SELECT RAISE(ABORT,'shelf cycle') WHERE NEW.parent_id=NEW.shelf_id OR EXISTS(
    WITH RECURSIVE ancestors(id,parent_id,depth) AS(
      SELECT shelf_id,parent_id,1 FROM reader_shelves WHERE shelf_id=NEW.parent_id
      UNION ALL SELECT s.shelf_id,s.parent_id,a.depth+1 FROM reader_shelves s
        JOIN ancestors a ON s.shelf_id=a.parent_id WHERE a.depth<8)
    SELECT 1 FROM ancestors WHERE id=NEW.shelf_id);
  SELECT RAISE(ABORT,'shelf depth exceeds eight') WHERE (
    WITH RECURSIVE ancestors(id,parent_id,depth) AS(
      SELECT shelf_id,parent_id,1 FROM reader_shelves WHERE shelf_id=NEW.parent_id
      UNION ALL SELECT s.shelf_id,s.parent_id,a.depth+1 FROM reader_shelves s
        JOIN ancestors a ON s.shelf_id=a.parent_id WHERE a.depth<8)
    SELECT coalesce(max(depth),0) FROM ancestors) + (
    WITH RECURSIVE descendants(id,depth) AS(
      SELECT OLD.shelf_id,1 UNION ALL SELECT s.shelf_id,d.depth+1
        FROM reader_shelves s JOIN descendants d ON s.parent_id=d.id WHERE d.depth<8)
    SELECT max(depth) FROM descendants)>8;
END;

CREATE TABLE reader_book_shelves(
  shelf_id TEXT NOT NULL REFERENCES reader_shelves(shelf_id),
  book_key TEXT NOT NULL REFERENCES reader_books(book_key),
  ordinal INTEGER NOT NULL DEFAULT 0 CHECK(typeof(ordinal)='integer' AND ordinal>=0),
  PRIMARY KEY(shelf_id,book_key)
);
CREATE INDEX reader_book_shelves_page ON reader_book_shelves(shelf_id,ordinal,book_key);
CREATE INDEX reader_book_shelves_book ON reader_book_shelves(book_key,shelf_id);
CREATE TABLE reader_tags(
  tag_id TEXT PRIMARY KEY NOT NULL CHECK(typeof(tag_id)='text' AND length(tag_id)=32 AND tag_id NOT GLOB '*[^0-9a-f]*'),
  name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 256 AND instr(name,char(0))=0),
  deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN(0,1))
);
CREATE TRIGGER reader_tags_identity BEFORE UPDATE OF tag_id ON reader_tags
WHEN NEW.tag_id<>OLD.tag_id
BEGIN SELECT RAISE(ABORT,'tag identity is immutable'); END;
CREATE TABLE reader_book_tags(
  book_key TEXT NOT NULL REFERENCES reader_books(book_key),
  tag_id TEXT NOT NULL REFERENCES reader_tags(tag_id),
  PRIMARY KEY(book_key,tag_id)
);
CREATE INDEX reader_book_tags_tag ON reader_book_tags(tag_id,book_key);
CREATE TABLE reader_series(
  series_id TEXT PRIMARY KEY NOT NULL CHECK(typeof(series_id)='text' AND length(series_id)=32 AND series_id NOT GLOB '*[^0-9a-f]*'),
  name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 256 AND instr(name,char(0))=0),
  deleted INTEGER NOT NULL DEFAULT 0 CHECK(deleted IN(0,1))
);
CREATE TRIGGER reader_series_identity BEFORE UPDATE OF series_id ON reader_series
WHEN NEW.series_id<>OLD.series_id
BEGIN SELECT RAISE(ABORT,'series identity is immutable'); END;
CREATE TABLE reader_book_series(
  series_id TEXT NOT NULL REFERENCES reader_series(series_id),
  book_key TEXT NOT NULL REFERENCES reader_books(book_key),
  ordinal INTEGER NOT NULL CHECK(typeof(ordinal)='integer' AND ordinal>=0),
  PRIMARY KEY(series_id,book_key)
);
CREATE INDEX reader_book_series_page ON reader_book_series(series_id,ordinal,book_key);
CREATE INDEX reader_book_series_book ON reader_book_series(book_key,series_id);

-- Wire JSON is retained verbatim. Validation and head/conflict selection belong
-- to the host, not to a JSON1 extension or SQL timestamp comparison.
CREATE TABLE reader_revisions(
  revision_id TEXT PRIMARY KEY NOT NULL CHECK(typeof(revision_id)='text' AND length(revision_id)=32 AND revision_id NOT GLOB '*[^0-9a-f]*'),
  entity_kind TEXT NOT NULL CHECK(entity_kind IN('book','shelf','tag','series','membership','progress','annotation')),
  entity_key TEXT NOT NULL CHECK(length(entity_key) BETWEEN 1 AND 256 AND instr(entity_key,char(0))=0),
  operation TEXT NOT NULL CHECK(operation IN('put','delete','restore')),
  body_json TEXT NOT NULL CHECK(typeof(body_json)='text' AND length(CAST(body_json AS BLOB)) BETWEEN 2 AND 1048576),
  body_sha256 TEXT NOT NULL CHECK(typeof(body_sha256)='text' AND length(body_sha256)=64 AND body_sha256 NOT GLOB '*[^0-9a-f]*')
);
CREATE INDEX reader_revisions_entity ON reader_revisions(entity_kind,entity_key,revision_id);
CREATE TRIGGER reader_revisions_no_replace BEFORE INSERT ON reader_revisions
WHEN EXISTS(SELECT 1 FROM reader_revisions WHERE revision_id=NEW.revision_id)
BEGIN SELECT RAISE(ABORT,'revision identity already exists; compare retained bytes'); END;
CREATE TRIGGER reader_revisions_no_update BEFORE UPDATE ON reader_revisions
BEGIN SELECT RAISE(ABORT,'revision bytes are immutable'); END;
CREATE TRIGGER reader_revisions_no_delete BEFORE DELETE ON reader_revisions
BEGIN SELECT RAISE(ABORT,'revision history and tombstones must be retained'); END;
CREATE VIEW reader_tombstones AS
  SELECT revision_id,entity_kind,entity_key,body_json,body_sha256
    FROM reader_revisions WHERE operation='delete';
CREATE TABLE reader_outbox(
  queue_id INTEGER PRIMARY KEY,
  revision_id TEXT NOT NULL UNIQUE REFERENCES reader_revisions(revision_id),
  attempts INTEGER NOT NULL DEFAULT 0 CHECK(typeof(attempts)='integer' AND attempts>=0),
  last_error TEXT NOT NULL DEFAULT '' CHECK(length(last_error)<=2048 AND instr(last_error,char(0))=0)
);
PRAGMA application_id=1163416144; -- EXRP; SDK EXRC has a different identity.
PRAGMA user_version=1;
COMMIT;
