#!/usr/bin/env bash
# Copied from kavrynt-platform/.github/actions/approval; keep the two in step.
# Opens an approval issue and polls its comments. The first comment from a
# listed approver that is exactly "approve" (or "approved", "lgtm", "yes")
# approves; "deny" (or "denied", "no") denies. Exits 0 only when approved.
set -euo pipefail

: "${GH_TOKEN:?}" "${GITHUB_REPOSITORY:?}" "${APPROVERS:?}" "${TITLE:?}" "${BODY_FILE:?}" "${TIMEOUT_MINUTES:?}" "${RUN_URL:?}"

approvers=$(tr ',' '\n' <<<"${APPROVERS}" | tr -d ' ' | tr '[:upper:]' '[:lower:]' | grep -v '^$' || true)
if [ -z "${approvers}" ]; then
  echo "::error::No approvers. Set the repository variable LAB_APPROVERS (comma-separated GitHub logins)."
  exit 1
fi

deadline=$(($(date +%s) + TIMEOUT_MINUTES * 60))
expires=$(date -u -d "@${deadline}" '+%H:%M UTC')
mentions=$(while read -r login; do printf '@%s ' "${login}"; done <<<"${approvers}")

body=$(mktemp)
{
  cat "${BODY_FILE}"
  echo
  echo "---"
  echo
  echo "${mentions}: comment **approve** to apply this plan, or **deny** to cancel."
  echo "The run waits until ${expires}: ${RUN_URL}"
} >"${body}"

url=$(gh issue create --repo "${GITHUB_REPOSITORY}" --title "${TITLE}" --body-file "${body}")
number=${url##*/}
echo "Waiting for approval: ${url}"
echo "### Waiting for approval: ${url}" >>"${GITHUB_STEP_SUMMARY}"

finish() {
  gh issue comment "${number}" --repo "${GITHUB_REPOSITORY}" --body "$1" >/dev/null
  gh issue close "${number}" --repo "${GITHUB_REPOSITORY}" >/dev/null
}

decide() {
  gh api --paginate "repos/${GITHUB_REPOSITORY}/issues/${number}/comments" \
    --jq '.[] | [.user.login, .body] | @tsv' |
    while IFS=$'\t' read -r login text; do
      login=$(tr '[:upper:]' '[:lower:]' <<<"${login}")
      grep -qxF "${login}" <<<"${approvers}" || continue
      case $(tr '[:upper:]' '[:lower:]' <<<"${text}" | tr -d '[:space:].!') in
        approve | approved | lgtm | yes) echo "approved ${login}" && break ;;
        deny | denied | no) echo "denied ${login}" && break ;;
      esac
    done
}

while [ "$(date +%s)" -lt "${deadline}" ]; do
  # A failed API call just means another poll.
  decision=$(decide || true)
  case "${decision}" in
    approved\ *)
      finish "Approved by @${decision#approved }. Applying: ${RUN_URL}"
      echo "Approved by ${decision#approved }."
      exit 0
      ;;
    denied\ *)
      finish "Denied by @${decision#denied }. Nothing was applied."
      echo "::error::Denied by ${decision#denied }. Nothing was applied."
      exit 1
      ;;
  esac
  sleep 15
done

finish "No decision by ${expires}. Nothing was applied; run the workflow again to retry."
echo "::error::No decision by ${expires}. Nothing was applied."
exit 1
