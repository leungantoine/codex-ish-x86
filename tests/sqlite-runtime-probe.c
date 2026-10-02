#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "sqlite3.h"
static void check(sqlite3 *db,const char *sql,const char *expected) {
  sqlite3_stmt *stmt;
  assert(sqlite3_prepare_v2(db,sql,-1,&stmt,NULL)==SQLITE_OK);
  assert(sqlite3_step(stmt)==SQLITE_ROW);
  const char *actual=(const char *)sqlite3_column_text(stmt,0);
  if(!actual || strcmp(actual,expected)) {
    fprintf(stderr,"SQL %s returned %s, expected %s\n",sql,actual?actual:"NULL",expected);
    assert(0);
  }
  assert(sqlite3_step(stmt)==SQLITE_DONE);
  assert(sqlite3_finalize(stmt)==SQLITE_OK);
}
int main(void) {
  sqlite3 *db; assert(sizeof(void *)==4); assert(sqlite3_open(":memory:",&db)==SQLITE_OK);
  check(db,"SELECT datetime(0,'unixepoch')","1970-01-01 00:00:00");
  check(db,"SELECT datetime('2000-02-29','+1 day')","2000-03-01 00:00:00");
  check(db,"SELECT datetime('1900-02-28','+1 day')","1900-03-01 00:00:00");
  check(db,"SELECT datetime('2026-10-01 23:59:59','+1 second')","2026-10-02 00:00:00");
  check(db,"SELECT datetime(2461314.5)","2026-10-01 00:00:00");
  check(db,"SELECT strftime('%Y-%m-%d','9999-12-31')","9999-12-31");
  check(db,"SELECT printf('%.2f',sqrt(2.0))","1.41");
  check(db,"SELECT printf('%.3f',1.25*2.5)","3.125");
  assert(sqlite3_exec(db,"CREATE TABLE t(ts TEXT DEFAULT CURRENT_TIMESTAMP); INSERT INTO t DEFAULT VALUES;",NULL,NULL,NULL)==SQLITE_OK);
  check(db,"SELECT length(ts) FROM t","19");
  assert(sqlite3_close(db)==SQLITE_OK);
  puts("PASS: real ELF32 SQLite scalar date, leap-year, timestamp and floating point checks");
}
