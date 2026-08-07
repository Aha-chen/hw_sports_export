#!/usr/bin/env sh
set -eu

UV_BIN="${UV:-uv}"
AUDIT_FILE="$(mktemp "${TMPDIR:-/tmp}/huawei-export-audit.XXXXXX")"
trap 'rm -f "$AUDIT_FILE"' EXIT

# pip-audit 暂不直接识别 uv.lock，因此先由 uv 导出锁定的运行依赖再执行审计。
"$UV_BIN" export \
    --quiet \
    --locked \
    --no-dev \
    --format requirements-txt \
    --no-hashes \
    --output-file "$AUDIT_FILE"
# uv 已导出完整传递依赖，因此禁止 pip-audit 再创建环境和重新解析依赖。
"$UV_BIN" run --locked --no-sync pip-audit \
    --requirement "$AUDIT_FILE" \
    --no-deps \
    --disable-pip
