#!/usr/bin/env bash
# Offline test-fixture journeys through the real CLI against a throwaway state directory.
# The test scenario runtime is explicitly enabled here and is never a supported app model route.
# Usage: bash docs/realignment/journeys.sh        (from anywhere; uses the venv of this checkout)
# Everything that blocks (CLI runs wait for approvals) is backgrounded with output redirected to files.
set -euo pipefail
cd "$(dirname "$0")/../.."
H=.venv/bin/hutch
HUTCH_STATE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/hutch-journeys.XXXX")
export HUTCH_STATE_DIR
export HUTCH_TESTING=1
PROJECT_ROOT=$(pwd)
export PYTHONPATH="$PROJECT_ROOT/tests/support:$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"
cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  if [[ -n ${RUN_PID:-} ]]; then
    if kill -0 "$RUN_PID" 2>/dev/null; then
      timeout 10 "$H" stop-all >/dev/null 2>&1 || true
      kill "$RUN_PID" 2>/dev/null || true
    fi
    wait "$RUN_PID" 2>/dev/null || true
  fi
  if [[ ${HUTCH_REALIGNMENT_KEEP_STATE:-0} == 1 ]]; then
    echo "kept state: $HUTCH_STATE_DIR"
  else
    rm -rf -- "$HUTCH_STATE_DIR"
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
out() { sed -e 's/^/   /'; }
echo "state: $HUTCH_STATE_DIR"

echo "J1 init";                $H init 2>&1 | tail -4 | out
echo "J2 create fixture bots"; $H bot create ledger-bot --model mock/test --description "keeps a ledger" --tools files,memory 2>&1 | tail -2 | out
$H bot create research-briefing --template research-briefing --model mock/test 2>&1 | tail -2 | out
$H bot create repo-sweeper --template repo-sweeper --model mock/test 2>&1 | tail -2 | out

echo "J3 run that needs approval, approved from a second process"
$H run research-briefing "summarize this week's AI news" > "$HUTCH_STATE_DIR/j3.out" 2>&1 &
RUN_PID=$!
sleep 4
AID=$($H approvals list 2>&1 | grep -o 'apr_[0-9a-f]*' | head -1 || true)
echo "   pending approval: ${AID:-none}"
if [[ -n "$AID" ]]; then $H approvals approve "$AID" 2>&1 | tail -1 | out; fi
wait $RUN_PID
unset RUN_PID
tail -3 "$HUTCH_STATE_DIR/j3.out" | out

echo "J4 inspect";             RID=$(sqlite3 "$HUTCH_STATE_DIR/hutch.db" "select id from runs order by created_at limit 1"); $H runs show "$RID" 2>&1 | sed -n '1,8p' | out

echo "J5 follow-up in the same 'conversation' (a brand-new run; approve it so it can finish)"
$H run research-briefing "what did you write last time?" > "$HUTCH_STATE_DIR/j5.out" 2>&1 &
RUN_PID=$!; sleep 4
AID=$($H approvals list 2>&1 | grep -o 'apr_[0-9a-f]*' | head -1 || true); if [[ -n "$AID" ]]; then $H approvals approve "$AID" >/dev/null 2>&1; fi
wait $RUN_PID; unset RUN_PID; tail -4 "$HUTCH_STATE_DIR/j5.out" | out

echo "J6 schedule";            $H bot update ledger-bot --cron "* * * * *" 2>&1 | tail -1 | out

echo "J7 cross-process Stop: start a run that blocks on approval, then stop-all from another process"
$H run repo-sweeper "scan" > "$HUTCH_STATE_DIR/j7.out" 2>&1 &
RUN_PID=$!; sleep 4
$H stop-all 2>&1 | tail -1 | out
sleep 3
if kill -0 $RUN_PID 2>/dev/null; then echo "   RESULT: the run's process is STILL ALIVE after stop-all (cross-process stop did not work)"; kill $RUN_PID; else echo "   RESULT: the run's process exited"; fi
wait "$RUN_PID" 2>/dev/null || true
unset RUN_PID
$H runs list 2>&1 | sed -n 4,8p | out

echo "J8 restart: a daemon tick recovers orphaned runs"
if timeout 3 "$H" daemon >/dev/null 2>&1; then
  :
else
  timeout_status=$?
  [[ $timeout_status -eq 124 ]] || exit "$timeout_status"
fi
$H runs list 2>&1 | sed -n 4,9p | out
echo "tasks done flags (id|done):"; sqlite3 "$HUTCH_STATE_DIR/hutch.db" "select done,count(*) from tasks group by done" 2>/dev/null | out
