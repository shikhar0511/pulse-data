# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2021 Recidiviz, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# =============================================================================
"""Defines admin panel routes for ingest operations."""
import datetime
import logging
from http import HTTPStatus
from typing import List, Optional, Tuple, Union

from flask import Blueprint, Response, jsonify, request
from google.cloud import storage

from recidiviz.admin_panel.admin_stores import (
    fetch_state_codes,
    get_ingest_operations_store,
)
from recidiviz.admin_panel.ingest_dataflow_operations import (
    get_latest_run_ingest_view_results,
    get_latest_run_raw_data_watermarks,
    get_latest_run_state_results,
    get_raw_data_tags_not_meeting_watermark,
)
from recidiviz.admin_panel.ingest_operations.ingest_utils import (
    check_is_valid_sandbox_bucket,
    get_unprocessed_raw_files_in_bucket,
    import_raw_files_to_bq_sandbox,
)
from recidiviz.big_query.big_query_client import BigQueryClientImpl
from recidiviz.cloud_storage.gcsfs_factory import GcsfsFactory
from recidiviz.cloud_storage.gcsfs_path import GcsfsBucketPath, GcsfsFilePath
from recidiviz.common.constants.operations.direct_ingest_instance_status import (
    DirectIngestStatus,
)
from recidiviz.common.constants.states import StateCode
from recidiviz.ingest.direct.dataset_config import (
    ingest_view_materialization_results_dataset,
)
from recidiviz.ingest.direct.direct_ingest_regions import get_direct_ingest_region
from recidiviz.ingest.direct.gating import is_raw_data_import_dag_enabled
from recidiviz.ingest.direct.gcs.direct_ingest_gcs_file_system import (
    DirectIngestGCSFileSystem,
)
from recidiviz.ingest.direct.gcs.filename_parts import filename_parts_from_path
from recidiviz.ingest.direct.metadata.direct_ingest_dataflow_job_manager import (
    DirectIngestDataflowJobManager,
)
from recidiviz.ingest.direct.metadata.direct_ingest_instance_status_manager import (
    DirectIngestInstanceStatusManager,
)
from recidiviz.ingest.direct.metadata.direct_ingest_raw_file_metadata_manager import (
    DirectIngestRawFileMetadataManager,
)
from recidiviz.ingest.direct.raw_data.raw_file_configs import (
    DirectIngestRegionRawFileConfig,
)
from recidiviz.ingest.direct.types.direct_ingest_instance import DirectIngestInstance
from recidiviz.ingest.flash_database_tools import (
    copy_raw_data_between_instances,
    copy_raw_data_to_backup,
    delete_contents_of_raw_data_tables,
    delete_tables_in_pruning_datasets,
)
from recidiviz.pipelines.ingest.dataset_config import state_dataset_for_state_code
from recidiviz.utils.trigger_dag_helpers import trigger_calculation_dag_pubsub
from recidiviz.utils.types import assert_type

GCS_IMPORT_EXPORT_TIMEOUT_SEC = 60 * 30  # 30 min


def _get_state_code_from_str(state_code_str: str) -> StateCode:
    if not StateCode.is_state_code(state_code_str):
        raise ValueError(
            f"Unknown region_code [{state_code_str}] received, must be a valid state code."
        )

    return StateCode[state_code_str.upper()]


def _sql_export_path(
    project_id: str, state_code: StateCode, ingest_instance: DirectIngestInstance
) -> GcsfsFilePath:
    return GcsfsFilePath.from_absolute_path(
        f"gs://{project_id}-cloud-sql-exports/{ingest_instance.value.lower()}/{state_code.value}"
    )


def add_ingest_ops_routes(bp: Blueprint) -> None:
    """Adds routes for ingest operations."""

    @bp.route("/api/ingest_operations/fetch_ingest_state_codes", methods=["POST"])
    def _fetch_ingest_state_codes() -> Tuple[Response, HTTPStatus]:
        all_state_codes = get_ingest_operations_store().state_codes_launched_in_env
        state_code_info = fetch_state_codes(all_state_codes)
        return jsonify(state_code_info), HTTPStatus.OK

    # Trigger the task scheduler for a specific instance
    @bp.route(
        "/api/ingest_operations/<state_code_str>/trigger_task_scheduler",
        methods=["POST"],
    )
    def _trigger_task_scheduler(state_code_str: str) -> Tuple[str, HTTPStatus]:
        request_json = assert_type(request.json, dict)
        state_code = _get_state_code_from_str(state_code_str)
        try:
            instance = DirectIngestInstance(request_json["instance"].upper())
        except ValueError:
            return "invalid ingest instance provided", HTTPStatus.BAD_REQUEST

        get_ingest_operations_store().trigger_task_scheduler(state_code, instance)
        return "", HTTPStatus.OK

    # Start a raw data reimport in secondary
    @bp.route(
        "/api/ingest_operations/<state_code_str>/start_raw_data_reimport",
        methods=["POST"],
    )
    def _start_raw_data_reimport(state_code_str: str) -> Tuple[str, HTTPStatus]:
        state_code = _get_state_code_from_str(state_code_str)
        try:
            get_ingest_operations_store().start_secondary_raw_data_reimport(state_code)
        except Exception as e:
            # Catch all exceptions and display the errors associated.
            return str(e), HTTPStatus.BAD_REQUEST

        return "", HTTPStatus.OK

    # Update ingest queues
    @bp.route(
        "/api/ingest_operations/<state_code_str>/update_ingest_queues_state",
        methods=["POST"],
    )
    def _update_ingest_queues_state(state_code_str: str) -> Tuple[str, HTTPStatus]:
        request_json = assert_type(request.json, dict)
        state_code = _get_state_code_from_str(state_code_str)
        new_queue_state = request_json["new_queue_state"]
        get_ingest_operations_store().update_ingest_queues_state(
            state_code, new_queue_state
        )
        return "", HTTPStatus.OK

    # Get all ingest queues and their state for given state code
    @bp.route("/api/ingest_operations/<state_code_str>/get_ingest_queue_states")
    def _get_ingest_queue_states(state_code_str: str) -> Tuple[Response, HTTPStatus]:
        state_code = _get_state_code_from_str(state_code_str)
        ingest_queue_states = get_ingest_operations_store().get_ingest_queue_states(
            state_code
        )
        return jsonify(ingest_queue_states), HTTPStatus.OK

    # Get summary of an ingest instance for a state
    @bp.route(
        "/api/ingest_operations/<state_code_str>/get_ingest_instance_resources/<ingest_instance_str>"
    )
    def _get_ingest_instance_resources(
        state_code_str: str, ingest_instance_str: str
    ) -> Tuple[Union[str, Response], HTTPStatus]:
        state_code = _get_state_code_from_str(state_code_str)
        try:
            ingest_instance = DirectIngestInstance(ingest_instance_str.upper())
        except ValueError:
            return "invalid parameters provided", HTTPStatus.BAD_REQUEST
        ingest_instance_resources = (
            get_ingest_operations_store().get_ingest_instance_resources(
                state_code, ingest_instance
            )
        )
        return jsonify(ingest_instance_resources), HTTPStatus.OK

    # Get processing status of filetags for an ingest instance for a state
    @bp.route(
        "/api/ingest_operations/<state_code_str>/get_ingest_raw_file_processing_status/<ingest_instance_str>"
    )
    def _get_ingest_raw_file_processing_status(
        state_code_str: str, ingest_instance_str: str
    ) -> Tuple[Union[str, Response], HTTPStatus]:
        state_code = _get_state_code_from_str(state_code_str)
        try:
            ingest_instance = DirectIngestInstance(ingest_instance_str.upper())
        except ValueError:
            return "invalid parameters provided", HTTPStatus.BAD_REQUEST
        ingest_file_processing_status = (
            get_ingest_operations_store().get_ingest_raw_file_processing_status(
                state_code, ingest_instance
            )
        )
        return jsonify(ingest_file_processing_status), HTTPStatus.OK

    @bp.route("/api/ingest_operations/direct/sandbox_raw_data_import", methods=["POST"])
    def _sandbox_raw_data_import() -> Tuple[Union[str, Response], HTTPStatus]:
        try:
            data = assert_type(request.json, dict)
            state_code = StateCode(data["stateCode"])
            sandbox_dataset_prefix = data["sandboxDatasetPrefix"]
            source_bucket = GcsfsBucketPath(data["sourceBucket"])
            file_tags: Optional[List[str]] = data.get("fileTagFilters", None)
        except ValueError:
            return "invalid parameters provided", HTTPStatus.BAD_REQUEST

        if not file_tags:
            file_tags = None

        try:
            import_status = import_raw_files_to_bq_sandbox(
                state_code=state_code,
                sandbox_dataset_prefix=sandbox_dataset_prefix,
                source_bucket=source_bucket,
                file_tag_filters=file_tags,
                allow_incomplete_configs=True,
                big_query_client=BigQueryClientImpl(),
                gcsfs=GcsfsFactory.build(),
            )
        except ValueError as error:
            return str(error), HTTPStatus.INTERNAL_SERVER_ERROR

        return (
            jsonify(
                {
                    "fileStatusList": import_status.to_serializable()["fileStatuses"],
                }
            ),
            HTTPStatus.OK,
        )

    @bp.route("/api/ingest_operations/direct/list_sandbox_buckets", methods=["POST"])
    def _list_sandbox_buckets() -> Tuple[Union[str, Response], HTTPStatus]:
        try:
            storage_client = storage.Client()
            buckets = storage_client.list_buckets()

            bucket_names = [bucket.name for bucket in buckets]

            filtered_buckets = []
            for bucket in bucket_names:
                try:
                    check_is_valid_sandbox_bucket(GcsfsBucketPath(bucket))
                    filtered_buckets.append(bucket)
                except ValueError:
                    continue

        except Exception:
            return (
                "something went wrong getting the list of buckets",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

        return (
            jsonify({"bucketNames": filtered_buckets}),
            HTTPStatus.OK,
        )

    @bp.route("/api/ingest_operations/direct/list_raw_files", methods=["POST"])
    def _list_raw_files_in_sandbox_bucket() -> Tuple[Union[str, Response], HTTPStatus]:
        try:
            data = assert_type(request.json, dict)
            state_code = StateCode(data["stateCode"])
            source_bucket = GcsfsBucketPath(data["sourceBucket"])
        except ValueError:
            return "invalid source bucket", HTTPStatus.BAD_REQUEST

        try:
            region_code = state_code.value.lower()
            region = get_direct_ingest_region(region_code)
            raw_files_to_import = get_unprocessed_raw_files_in_bucket(
                fs=DirectIngestGCSFileSystem(GcsfsFactory.build()),
                bucket_path=source_bucket,
                region_raw_file_config=DirectIngestRegionRawFileConfig(
                    region_code=region.region_code,
                    region_module=region.region_module,
                ),
            )
        except ValueError:
            return (
                f"Something went wrong trying to get unprocessed raw files from {source_bucket} bucket",
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

        raw_files_list = []
        for file_path in raw_files_to_import:
            parts = filename_parts_from_path(file_path)
            raw_files_list.append(
                {
                    "fileTag": parts.file_tag,
                    "uploadDate": parts.utc_upload_datetime_str,
                }
            )

        return (
            jsonify({"rawFilesList": raw_files_list}),
            HTTPStatus.OK,
        )

    @bp.route("/api/ingest_operations/all_ingest_instance_statuses")
    def _all_ingest_instance_statuses() -> Tuple[Response, HTTPStatus]:
        all_instance_statuses = (
            get_ingest_operations_store().get_all_current_ingest_instance_statuses()
        )

        return (
            jsonify(
                {
                    instance_state_code.value: {
                        instance.value.lower(): curr_status_info.for_api()
                        for instance, curr_status_info in instances.items()
                    }
                    for instance_state_code, instances in all_instance_statuses.items()
                }
            ),
            HTTPStatus.OK,
        )

    @bp.route("/api/ingest_operations/get_all_latest_ingest_dataflow_jobs")
    def _all_dataflow_jobs() -> Tuple[Response, HTTPStatus]:
        all_instance_statuses = (
            get_ingest_operations_store().get_most_recent_dataflow_job_statuses()
        )

        return (
            jsonify(
                {
                    instance_state_code.value: (
                        curr_status_info.for_api() if curr_status_info else None
                    )
                    for instance_state_code, curr_status_info in all_instance_statuses.items()
                }
            ),
            HTTPStatus.OK,
        )

    @bp.route("/api/ingest_operations/get_latest_ingest_dataflow_job/<state_code_str>")
    def _get_latest_ingest_dataflow_job(
        state_code_str: str,
    ) -> Tuple[Response, HTTPStatus]:
        try:
            state_code = StateCode(state_code_str)
        except ValueError:
            return (jsonify("Invalid input data"), HTTPStatus.BAD_REQUEST)

        all_primary_pipeline_statuses = (
            get_ingest_operations_store().get_most_recent_dataflow_job_statuses()
        )

        job_info = all_primary_pipeline_statuses[state_code]

        return (
            jsonify(job_info.for_api() if job_info else None),
            HTTPStatus.OK,
        )

    @bp.route(
        "/api/ingest_operations/get_dataflow_job_additional_metadata_by_instance/<state_code_str>/<instance_str>"
    )
    def _get_dataflow_job_additional_metadata_by_instance(
        state_code_str: str,
        instance_str: str,
    ) -> Tuple[Response, HTTPStatus]:
        try:
            state_code = StateCode(state_code_str)
            instance = DirectIngestInstance(instance_str)
        except ValueError:
            return (jsonify("Invalid input data"), HTTPStatus.BAD_REQUEST)

        ingest_view_results_dataset = ingest_view_materialization_results_dataset(
            state_code, instance
        )
        state_results_dataset = state_dataset_for_state_code(state_code, instance)

        return (
            jsonify(
                {
                    "ingestViewResultsDatasetName": ingest_view_results_dataset,
                    "stateResultsDatasetName": state_results_dataset,
                }
            ),
            HTTPStatus.OK,
        )

    @bp.route(
        "/api/ingest_operations/get_current_ingest_instance_status", methods=["POST"]
    )
    def _get_current_ingest_instance_status() -> Tuple[str, HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
            ingest_instance = DirectIngestInstance(
                request_json["ingestInstance"].upper()
            )
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        status_manager = DirectIngestInstanceStatusManager(
            state_code.value,
            ingest_instance,
        )
        current_status: str = status_manager.get_current_status().value
        return (
            current_status,
            HTTPStatus.OK,
        )

    @bp.route(
        "/api/ingest_operations/get_current_ingest_instance_status_information",
        methods=["POST"],
    )
    def _get_current_ingest_instance_status_information() -> (
        Tuple[Union[str, Response], HTTPStatus]
    ):
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
            ingest_instance = DirectIngestInstance(
                request_json["ingestInstance"].upper()
            )
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        status_manager = DirectIngestInstanceStatusManager(
            state_code.value,
            ingest_instance,
        )
        current_status = status_manager.get_current_status_info()
        return (
            jsonify(current_status.for_api()),
            HTTPStatus.OK,
        )

    @bp.route(
        "/api/ingest_operations/change_ingest_instance_status",
        methods=["POST"],
    )
    def _change_ingest_instance_status() -> Tuple[str, HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
            ingest_instance = DirectIngestInstance(
                request_json["ingestInstance"].upper()
            )
            ingest_instance_status = DirectIngestStatus(
                request_json["ingestInstanceStatus"].upper()
            )
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        try:
            status_manager = DirectIngestInstanceStatusManager(
                state_code.value,
                ingest_instance,
            )
            status_manager.change_status_to(ingest_instance_status)
        except ValueError:
            return (
                f"Cannot set status={ingest_instance_status.value} in {ingest_instance.value}.",
                HTTPStatus.BAD_REQUEST,
            )

        return "", HTTPStatus.OK

    @bp.route(
        "/api/ingest_operations/get_recent_ingest_instance_status_history/<state_code_str>"
    )
    def _get_recent_ingest_instance_status_history(
        state_code_str: str,
    ) -> Tuple[Union[str, Response], HTTPStatus]:
        try:
            state_code = StateCode(state_code_str)
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        status_manager = DirectIngestInstanceStatusManager(
            state_code.value,
            DirectIngestInstance.PRIMARY,
        )
        statuses = status_manager.get_statuses_since(
            datetime.datetime.now() - datetime.timedelta(days=180)
        )
        return (
            jsonify([status.for_api() for status in statuses]),
            HTTPStatus.OK,
        )

    @bp.route(
        "/api/ingest_operations/flash_primary_db/copy_raw_data_to_backup",
        methods=["POST"],
    )
    def _copy_raw_data_to_backup() -> Tuple[str, HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
            ingest_instance = DirectIngestInstance(
                request_json["ingestInstance"].upper()
            )
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        try:
            copy_raw_data_to_backup(state_code, ingest_instance, BigQueryClientImpl())

            return (
                "",
                HTTPStatus.OK,
            )

        except ValueError as error:
            logging.exception(error)
            return f"{error}", HTTPStatus.INTERNAL_SERVER_ERROR

    @bp.route(
        "/api/ingest_operations/flash_primary_db/copy_raw_data_between_instances",
        methods=["POST"],
    )
    def _copy_raw_data_between_instances() -> Tuple[str, HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
            ingest_instance_source = DirectIngestInstance(
                request_json["srcIngestInstance"].upper()
            )
            ingest_instance_destination = DirectIngestInstance(
                request_json["destIngestInstance"].upper()
            )
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        try:
            copy_raw_data_between_instances(
                state_code=state_code,
                ingest_instance_source=ingest_instance_source,
                ingest_instance_destination=ingest_instance_destination,
                big_query_client=BigQueryClientImpl(),
            )

            return (
                "",
                HTTPStatus.OK,
            )

        except ValueError as error:
            logging.exception(error)
            return f"{error}", HTTPStatus.INTERNAL_SERVER_ERROR

    @bp.route(
        "/api/ingest_operations/flash_primary_db/delete_contents_of_raw_data_tables",
        methods=["POST"],
    )
    def _delete_contents_of_raw_data_tables() -> Tuple[str, HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
            ingest_instance = DirectIngestInstance(
                request_json["ingestInstance"].upper()
            )
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        try:
            delete_contents_of_raw_data_tables(
                state_code=state_code,
                ingest_instance=ingest_instance,
                big_query_client=BigQueryClientImpl(),
            )
            return (
                "",
                HTTPStatus.OK,
            )

        except ValueError as error:
            logging.exception(error)
            return f"{error}", HTTPStatus.INTERNAL_SERVER_ERROR

    @bp.route(
        "/api/ingest_operations/flash_primary_db/mark_instance_raw_data_invalidated",
        methods=["POST"],
    )
    def _mark_instance_raw_data_invalidated() -> Tuple[str, HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
            ingest_instance = DirectIngestInstance(
                request_json["ingestInstance"].upper()
            )
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        try:
            raw_file_metadata_manager = DirectIngestRawFileMetadataManager(
                region_code=state_code.value,
                raw_data_instance=ingest_instance,
            )
            raw_file_metadata_manager.mark_instance_data_invalidated()

            return (
                "",
                HTTPStatus.OK,
            )

        except ValueError as error:
            logging.exception(error)
            return f"{error}", HTTPStatus.INTERNAL_SERVER_ERROR

    # TODO(#29133) update to use DirectIngestRawFileMetadataManagerV2
    # TODO(#29133) add call to DirectIngestRawDataImportSessionManager.transfer_metadata_to_new_instance
    @bp.route(
        "/api/ingest_operations/flash_primary_db/transfer_raw_data_metadata_to_new_instance",
        methods=["POST"],
    )
    def _transfer_raw_data_metadata_to_new_instance() -> Tuple[str, HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
            src_ingest_instance = DirectIngestInstance(
                request_json["srcIngestInstance"].upper()
            )
            dest_ingest_instance = DirectIngestInstance(
                request_json["destIngestInstance"].upper()
            )
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        try:
            raw_data_manager = DirectIngestRawFileMetadataManager(
                region_code=state_code.value,
                raw_data_instance=src_ingest_instance,
            )

            new_instance_manager = DirectIngestRawFileMetadataManager(
                region_code=state_code.value,
                raw_data_instance=dest_ingest_instance,
            )

            raw_data_manager.transfer_metadata_to_new_instance(
                new_instance_manager=new_instance_manager
            )

            return (
                "",
                HTTPStatus.OK,
            )

        except ValueError as error:
            logging.exception(error)
            return f"{error}", HTTPStatus.INTERNAL_SERVER_ERROR

    @bp.route(
        "/api/ingest_operations/flash_primary_db/invalidate_ingest_pipeline_runs",
        methods=["POST"],
    )
    def _invalidate_ingest_pipeline_runs() -> Tuple[str, HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"].upper())
            ingest_instance = DirectIngestInstance(
                request_json["ingestInstance"].upper()
            )
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        try:
            dataflow_job_manager = DirectIngestDataflowJobManager()
            dataflow_job_manager.invalidate_all_dataflow_jobs(
                state_code, ingest_instance
            )
            return ("", HTTPStatus.OK)
        except ValueError as error:
            logging.exception(error)
            return f"{error}", HTTPStatus.INTERNAL_SERVER_ERROR

    # Purges the ingest queues for a given state code
    @bp.route(
        "/api/ingest_operations/purge_ingest_queues",
        methods=["POST"],
    )
    def _purge_ingest_queues() -> Tuple[str, HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        get_ingest_operations_store().purge_ingest_queues(state_code=state_code)
        return "", HTTPStatus.OK

    @bp.route(
        "/api/ingest_operations/get_latest_ingest_dataflow_raw_data_watermarks/<state_code_str>/<instance_str>"
    )
    def _get_latest_ingest_dataflow_raw_data_watermarks(
        state_code_str: str,
        instance_str: str,
    ) -> Tuple[Response, HTTPStatus]:
        try:
            state_code = StateCode(state_code_str)
            instance = DirectIngestInstance(instance_str)
        except ValueError:
            return (jsonify("Invalid input data"), HTTPStatus.BAD_REQUEST)

        raw_data_watermarks = get_latest_run_raw_data_watermarks(state_code, instance)

        return (
            jsonify(
                {
                    file_tag: watermark.isoformat()
                    for file_tag, watermark in raw_data_watermarks.items()
                }
            ),
            HTTPStatus.OK,
        )

    @bp.route(
        "/api/ingest_operations/get_latest_raw_data_tags_not_meeting_watermark/<state_code_str>/<instance_str>"
    )
    def _get_latest_raw_data_tags_not_meeting_watermark(
        state_code_str: str,
        instance_str: str,
    ) -> Tuple[Response, HTTPStatus]:
        try:
            state_code = StateCode(state_code_str)
            instance = DirectIngestInstance(instance_str)
        except ValueError:
            return (jsonify("Invalid input data"), HTTPStatus.BAD_REQUEST)

        raw_data_tags = get_raw_data_tags_not_meeting_watermark(state_code, instance)

        return (
            jsonify(raw_data_tags),
            HTTPStatus.OK,
        )

    @bp.route(
        "/api/ingest_operations/get_latest_run_ingest_view_results/<state_code_str>/<instance_str>"
    )
    def _get_latest_run_ingest_view_results(
        state_code_str: str,
        instance_str: str,
    ) -> Tuple[Response, HTTPStatus]:
        try:
            state_code = StateCode(state_code_str)
            instance = DirectIngestInstance(instance_str)
        except ValueError:
            return (jsonify("Invalid input data"), HTTPStatus.BAD_REQUEST)

        ingest_view_results = get_latest_run_ingest_view_results(state_code, instance)

        return (jsonify(ingest_view_results), HTTPStatus.OK)

    @bp.route(
        "/api/ingest_operations/get_latest_run_state_results/<state_code_str>/<instance_str>"
    )
    def _get_latest_run_state_results(
        state_code_str: str,
        instance_str: str,
    ) -> Tuple[Response, HTTPStatus]:
        try:
            state_code = StateCode(state_code_str)
            instance = DirectIngestInstance(instance_str)
        except ValueError:
            return (jsonify("Invalid input data"), HTTPStatus.BAD_REQUEST)

        ingest_view_results = get_latest_run_state_results(state_code, instance)

        return (jsonify(ingest_view_results), HTTPStatus.OK)

    @bp.route(
        "/api/ingest_operations/delete_tables_in_pruning_datasets",
        methods=["POST"],
    )
    def _delete_tables_in_pruning_datasets() -> Tuple[Union[str, Response], HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
            ingest_instance = DirectIngestInstance(request_json["instance"].upper())
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        try:
            delete_tables_in_pruning_datasets(
                state_code, ingest_instance, BigQueryClientImpl()
            )
            return (
                "",
                HTTPStatus.OK,
            )

        except ValueError as error:
            logging.exception(error)
            return f"{error}", HTTPStatus.INTERNAL_SERVER_ERROR

    @bp.route(
        "/api/ingest_operations/trigger_calculation_dag",
        methods=["POST"],
    )
    def _trigger_calculation_dag() -> Tuple[Union[str, Response], HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        try:
            trigger_calculation_dag_pubsub(DirectIngestInstance.PRIMARY, state_code)
            return (
                "",
                HTTPStatus.OK,
            )

        except ValueError as error:
            logging.exception(error)
            return f"{error}", HTTPStatus.INTERNAL_SERVER_ERROR

    # TODO(#28239): delete once raw data import dag is enabled in all states
    @bp.route(
        "/api/ingest_operations/is_raw_data_import_dag_enabled",
        methods=["POST"],
    )
    def _is_raw_data_import_dag_enabled() -> Tuple[Union[str, Response], HTTPStatus]:
        try:
            request_json = assert_type(request.json, dict)
            state_code = StateCode(request_json["stateCode"])
            ingest_instance = DirectIngestInstance(request_json["instance"].upper())
        except ValueError:
            return "Invalid input data", HTTPStatus.BAD_REQUEST

        return (
            jsonify(is_raw_data_import_dag_enabled(state_code, ingest_instance)),
            HTTPStatus.OK,
        )
