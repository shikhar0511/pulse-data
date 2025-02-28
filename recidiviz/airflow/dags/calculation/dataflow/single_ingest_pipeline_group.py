# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2023 Recidiviz, Inc.
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
"""
Logic for state and ingest instance specific dataflow pipelines.
"""
import logging
from typing import Dict, Tuple

from airflow.decorators import task
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.utils.task_group import TaskGroup

from recidiviz.airflow.dags.calculation.dataflow.ingest_pipeline_task_group_delegate import (
    IngestDataflowPipelineTaskGroupDelegate,
)
from recidiviz.airflow.dags.calculation.ingest.add_ingest_job_completion_sql_query_generator import (
    AddIngestJobCompletionSqlQueryGenerator,
)
from recidiviz.airflow.dags.calculation.ingest.get_max_update_datetime_sql_query_generator import (
    GetMaxUpdateDateTimeSqlQueryGenerator,
)
from recidiviz.airflow.dags.calculation.ingest.get_watermark_sql_query_generator import (
    GetWatermarkSqlQueryGenerator,
)
from recidiviz.airflow.dags.calculation.ingest.set_watermark_sql_query_generator import (
    SetWatermarkSqlQueryGenerator,
)
from recidiviz.airflow.dags.calculation.initialize_calculation_dag_group import (
    INGEST_INSTANCE_JINJA_ARG,
)
from recidiviz.airflow.dags.operators.cloud_sql_query_operator import (
    CloudSqlQueryOperator,
)
from recidiviz.airflow.dags.operators.recidiviz_kubernetes_pod_operator import (
    build_kubernetes_pod_task,
)
from recidiviz.airflow.dags.utils.cloud_sql import cloud_sql_conn_id_for_schema_type
from recidiviz.airflow.dags.utils.dataflow_pipeline_group import (
    build_dataflow_pipeline_task_group,
)
from recidiviz.common.constants.states import StateCode
from recidiviz.ingest.direct.types.direct_ingest_instance import DirectIngestInstance
from recidiviz.persistence.database.schema_type import SchemaType

# Need a disable pointless statement because Python views the chaining operator ('>>')
# as a "pointless" statement
# pylint: disable=W0104 pointless-statement

# Need a "disable expression-not-assigned" because the chaining ('>>') doesn't need expressions to be assigned
# pylint: disable=W0106 expression-not-assigned


def _ingest_pipeline_should_run_in_dag(state_code: StateCode) -> KubernetesPodOperator:
    return build_kubernetes_pod_task(
        task_id="ingest_pipeline_should_run_in_dag",
        container_name="ingest_pipeline_should_run_in_dag",
        arguments=[
            "--entrypoint=IngestPipelineShouldRunInDagEntrypoint",
            f"--state_code={state_code.value}",
            INGEST_INSTANCE_JINJA_ARG,
        ],
        cloud_sql_connections=[SchemaType.OPERATIONS],
        do_xcom_push=True,
    )


@task.short_circuit(ignore_downstream_trigger_rules=False)
# allows skipping of downstream tasks until trigger rule prevents it (like ALL_DONE)
def handle_ingest_pipeline_should_run_in_dag_check(
    should_run_ingest_pipeline: bool,
) -> bool:
    """Returns True if the DAG should continue, otherwise short circuits."""
    if not isinstance(should_run_ingest_pipeline, bool):
        raise ValueError(
            f"Expected should_run_ingest_pipeline value to be of type bool, found type "
            f"[{type(should_run_ingest_pipeline)}]: {should_run_ingest_pipeline}"
        )

    if not should_run_ingest_pipeline:
        logging.info("should_run_ingest_pipeline did not return true, do not continue.")
        return False
    return True


@task.short_circuit(
    task_id="should_run_based_on_watermarks",
    ignore_downstream_trigger_rules=False
    # allows skipping of downstream tasks until trigger rule prevents it (like ALL_DONE)
)
def _should_run_based_on_watermarks(
    watermarks: Dict[str, str], max_update_datetimes: Dict[str, str]
) -> bool:
    for raw_file_tag, watermark_for_file in watermarks.items():
        if raw_file_tag not in max_update_datetimes:
            raise ValueError(
                f"Watermark file_tag '{raw_file_tag}' not found in max update datetimes: {max_update_datetimes.keys()}"
            )

        if watermark_for_file > max_update_datetimes[raw_file_tag]:
            logging.error(
                "Raw file %s has older data than the last time the ingest pipeline was run. Current max update_datetime: %s. Last ingest pipeline run update_datetime: %s.",
                raw_file_tag,
                max_update_datetimes[raw_file_tag],
                watermark_for_file,
            )
            return False

    return True


def _verify_raw_data_flashing_not_in_progress(
    state_code: StateCode,
) -> KubernetesPodOperator:
    return build_kubernetes_pod_task(
        task_id="verify_raw_data_flashing_not_in_progress",
        container_name="verify_raw_data_flashing_not_in_progress",
        arguments=[
            "--entrypoint=IngestCheckRawDataFlashingEntrypoint",
            f"--state_code={state_code.value}",
            INGEST_INSTANCE_JINJA_ARG,
        ],
        cloud_sql_connections=[SchemaType.OPERATIONS],
    )


def _initialize_dataflow_pipeline(
    state_code: StateCode,
    operations_cloud_sql_conn_id: str,
) -> Tuple[TaskGroup, CloudSqlQueryOperator]:
    """
    Initializes the dataflow pipeline by getting the max update datetimes and watermarks and checking if the pipeline should run.
    Returns the task group and the get_max_update_datetimes task for use in downstream tasks.
    """

    with TaskGroup("initialize_dataflow_pipeline") as initialize_dataflow_pipeline:
        check_ingest_pipeline_should_run_in_dag = (
            handle_ingest_pipeline_should_run_in_dag_check(
                _ingest_pipeline_should_run_in_dag(state_code).output
            )
        )

        get_max_update_datetimes = CloudSqlQueryOperator(
            task_id="get_max_update_datetimes",
            cloud_sql_conn_id=operations_cloud_sql_conn_id,
            query_generator=GetMaxUpdateDateTimeSqlQueryGenerator(
                region_code=state_code.value
            ),
        )

        get_watermarks = CloudSqlQueryOperator(
            task_id="get_watermarks",
            cloud_sql_conn_id=operations_cloud_sql_conn_id,
            query_generator=GetWatermarkSqlQueryGenerator(
                region_code=state_code.value,
            ),
        )

        should_run_based_on_watermarks = _should_run_based_on_watermarks(
            watermarks=get_watermarks.output,  # type: ignore[arg-type]
            max_update_datetimes=get_max_update_datetimes.output,  # type: ignore[arg-type]
        )

        (
            check_ingest_pipeline_should_run_in_dag
            >> [get_max_update_datetimes, get_watermarks]
            >> should_run_based_on_watermarks
            >> _verify_raw_data_flashing_not_in_progress(state_code)
        )

    return initialize_dataflow_pipeline, get_max_update_datetimes


def create_single_ingest_pipeline_group(state_code: StateCode) -> TaskGroup:
    """
    Creates a dataflow pipeline operator for the given state.
    """

    operations_cloud_sql_conn_id = cloud_sql_conn_id_for_schema_type(
        SchemaType.OPERATIONS
    )

    with TaskGroup(f"{state_code.value.lower()}_dataflow") as dataflow:
        (
            initialize_dataflow_pipeline,
            get_max_update_datetimes,
        ) = _initialize_dataflow_pipeline(state_code, operations_cloud_sql_conn_id)

        dataflow_pipeline_group, run_pipeline = build_dataflow_pipeline_task_group(
            delegate=IngestDataflowPipelineTaskGroupDelegate(
                state_code=state_code,
                default_ingest_instance=DirectIngestInstance.PRIMARY,
                max_update_datetimes_operator=get_max_update_datetimes,
            )
        )

        write_upper_bounds = CloudSqlQueryOperator(
            task_id="write_upper_bounds",
            cloud_sql_conn_id=operations_cloud_sql_conn_id,
            query_generator=SetWatermarkSqlQueryGenerator(
                region_code=state_code.value,
                get_max_update_datetime_task_id=get_max_update_datetimes.task_id,
                run_pipeline_task_id=run_pipeline.task_id,
            ),
        )

        write_ingest_job_completion = CloudSqlQueryOperator(
            task_id="write_ingest_job_completion",
            cloud_sql_conn_id=operations_cloud_sql_conn_id,
            query_generator=AddIngestJobCompletionSqlQueryGenerator(
                region_code=state_code.value,
                run_pipeline_task_id=run_pipeline.task_id,
            ),
        )

        (
            initialize_dataflow_pipeline
            >> dataflow_pipeline_group
            >> write_ingest_job_completion
            >> write_upper_bounds
        )

    return dataflow
