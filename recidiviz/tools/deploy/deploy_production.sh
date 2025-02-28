#!/usr/bin/env bash
#
# Script for deploying tagged versions to production. Must be run within the pipenv shell.
#

# Used to track total time required to deploy to production.
# See how this works at https://stackoverflow.com/questions/8903239/how-to-calculate-time-elapsed-in-bash-script.
SECONDS=0

PROJECT="recidiviz-123"

BASH_SOURCE_DIR=$(dirname "${BASH_SOURCE[0]}")
# shellcheck source=recidiviz/tools/script_base.sh
source "${BASH_SOURCE_DIR}/../script_base.sh"
# shellcheck source=recidiviz/tools/deploy/deploy_helpers.sh
source "${BASH_SOURCE_DIR}/deploy_helpers.sh"

if [[ "$1" == "" ]]; then
    echo_error "usage: $0 <version_tag>"
    run_cmd exit 1
fi

echo "Performing pre-deploy verification"
run_cmd verify_can_deploy recidiviz-123

GIT_VERSION_TAG=$(echo "$1" | tr '-' '.') || exit_on_fail
if [[ ! ${GIT_VERSION_TAG} =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo_error "Invalid release version [$GIT_VERSION_TAG] - must match regex: v[0-9]+\.[0-9]+\.[0-9]+"
    run_cmd exit 1
fi


read -r -a VERSION_PARTS < <(parse_version "${GIT_VERSION_TAG}")
MAJOR_VERSION="${VERSION_PARTS[1]}"
MINOR_VERSION="${VERSION_PARTS[2]}"
CHANGES_SINCE_TAG=$(git log "tags/${GIT_VERSION_TAG}..releases/v${MAJOR_VERSION}.${MINOR_VERSION}-rc" --oneline)
if [ -n "${CHANGES_SINCE_TAG}" ]; then
  echo "There are newly-added commits in the release branch that will not be deployed in ${GIT_VERSION_TAG}:"
  echo "${CHANGES_SINCE_TAG}" | indent_output
  echo "Folks may be expecting the above changes to go out in this production deploy (did we miss a cherry-pick?)."
  script_prompt  "Would you like to continue deploying ${GIT_VERSION_TAG}?"
fi


LAST_DEPLOYED_GIT_VERSION_TAG=$(last_deployed_version_tag recidiviz-123) || exit_on_fail
if ! version_less_than "${LAST_DEPLOYED_GIT_VERSION_TAG}" "${GIT_VERSION_TAG}"; then
    echo_error "Deploy version [$GIT_VERSION_TAG] must be greater than last deployed tag [$LAST_DEPLOYED_GIT_VERSION_TAG]."
    run_cmd exit 1
fi

echo "Beginning deploy of version [$GIT_VERSION_TAG] to production. Last deployed version: [$LAST_DEPLOYED_GIT_VERSION_TAG]."
script_prompt "Do you want to continue?"

echo "Commits since last deploy:"
run_cmd git log --oneline "tags/${LAST_DEPLOYED_GIT_VERSION_TAG}..tags/${GIT_VERSION_TAG}"

script_prompt "Have you completed all Pre-Deploy tasks listed at http://go/deploy-checklist/ ?"

echo "Fetching all tags"
run_cmd git fetch --all --tags --prune --prune-tags --force

echo "Checking for clean git status"
if [[ -n "$(git status --porcelain)" ]]; then
    echo_error "Git status not clean - please commit or stash changes before retrying."
    run_cmd exit 1
fi

echo "Checking out tag [$GIT_VERSION_TAG]"
if ! git checkout tags/"${GIT_VERSION_TAG}" -b "${GIT_VERSION_TAG}"
then
    echo "Attempting to reuse existing branch $GIT_VERSION_TAG"
    run_cmd git checkout "${GIT_VERSION_TAG}"
fi

COMMIT_HASH=$(git rev-parse HEAD) || exit_on_fail

update_deployment_status "${DEPLOYMENT_STATUS_STARTED}" "${PROJECT}" "${COMMIT_HASH:0:7}" "${GIT_VERSION_TAG}"


# Use rev-list to get the hash of the commit that the tag points to, rev-parse parse
# returns the hash of the tag itself.
TAG_COMMIT_HASH=$(git rev-list -n 1 "${GIT_VERSION_TAG}") || exit_on_fail

echo "Updating configuration / infrastructure in preparation for deploy"
verify_hash "$TAG_COMMIT_HASH"
pre_deploy_configure_infrastructure 'recidiviz-123' "${GIT_VERSION_TAG}" "$TAG_COMMIT_HASH"

DATAFLOW_BUILD_URL="us-docker.pkg.dev/recidiviz-123/dataflow/build:${TAG_COMMIT_HASH}" || exit_on_fail
DATAFLOW_PROD_IMAGE_URL="us-docker.pkg.dev/recidiviz-123/dataflow/default:${GIT_VERSION_TAG}" || exit_on_fail

echo "Tagging dataflow image for deploy"
{
    run_cmd_no_exiting gcloud -q container images add-tag "${DATAFLOW_BUILD_URL}" "${DATAFLOW_PROD_IMAGE_URL}"
} || {
    echo "Falling back to manual docker tag commands"
    # We are running these fallback commands in case the add-tag command above times out
    # (likely due to network bandwidth)
    run_cmd docker pull "${DATAFLOW_BUILD_URL}"
    run_cmd docker tag "${DATAFLOW_BUILD_URL}" "${DATAFLOW_PROD_IMAGE_URL}"
    run_cmd docker push "${DATAFLOW_PROD_IMAGE_URL}"
}

APP_ENGINE_STAGING_IMAGE_URL="us.gcr.io/recidiviz-staging/appengine/default:${GIT_VERSION_TAG}" || exit_on_fail
APP_ENGINE_PROD_IMAGE_URL="us.gcr.io/recidiviz-123/appengine/default:${GIT_VERSION_TAG}" || exit_on_fail

echo "Starting deploy of main app - default"
{
    run_cmd_no_exiting gcloud -q container images add-tag "${APP_ENGINE_STAGING_IMAGE_URL}" "${APP_ENGINE_PROD_IMAGE_URL}"
} || {
    echo "Falling back to manual docker tag commands"
    # We are running these fallback commands in case the add-tag command above times out
    # (likely due to network bandwidth)
    run_cmd docker pull "${APP_ENGINE_STAGING_IMAGE_URL}"
    run_cmd docker tag "${APP_ENGINE_STAGING_IMAGE_URL}" "${APP_ENGINE_PROD_IMAGE_URL}"
    run_cmd docker push "${APP_ENGINE_PROD_IMAGE_URL}"
}


# TODO(#3928): Migrate deploy of app engine services to terraform.
GAE_VERSION=$(echo "${GIT_VERSION_TAG}" | tr '.' '-') || exit_on_fail
run_cmd gcloud -q app deploy prod.yaml --project="${PROJECT}" --version="${GAE_VERSION}" --image-url="${APP_ENGINE_PROD_IMAGE_URL}"

echo "Deploy succeeded - triggering post-deploy jobs."
post_deploy_triggers 'recidiviz-123'

update_deployment_status "${DEPLOYMENT_STATUS_SUCCEEDED}" "${PROJECT}" "${COMMIT_HASH:0:7}" "${GIT_VERSION_TAG}"

duration=$SECONDS
MINUTES=$((duration / 60))
echo "Production deploy completed in ${MINUTES} minutes."
echo "Release candidate staging deploy completed in ${MINUTES} minutes."

echo "Generating release notes."
GITHUB_DEPLOY_BOT_TOKEN=$(get_secret "$PROJECT" github_deploy_script_pat)
run_cmd pipenv run  python -m recidiviz.tools.deploy.generate_release_notes \
  --previous_tag "${LAST_DEPLOYED_GIT_VERSION_TAG}" \
  --new_tag "${GIT_VERSION_TAG}" \
  --github_token "${GITHUB_DEPLOY_BOT_TOKEN}"


script_prompt "Have you completed all Post-Deploy tasks listed at http://go/deploy-checklist/ ?"
