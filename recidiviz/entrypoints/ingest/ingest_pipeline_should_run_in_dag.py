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
""" Entrypoint for the ingest pipeline should run in dag check. """
import argparse
import logging

from recidiviz.common.constants.states import StateCode
from recidiviz.entrypoints.entrypoint_interface import EntrypointInterface
from recidiviz.entrypoints.entrypoint_utils import save_to_xcom
from recidiviz.ingest.direct import direct_ingest_regions
from recidiviz.ingest.direct.ingest_mappings.ingest_view_manifest_collector import (
    IngestViewManifestCollector,
)
from recidiviz.ingest.direct.ingest_mappings.ingest_view_manifest_compiler_delegate import (
    StateSchemaIngestViewManifestCompilerDelegate,
)
from recidiviz.ingest.direct.types.direct_ingest_instance import DirectIngestInstance
from recidiviz.utils import environment


def _has_launchable_ingest_views(
    state_code: StateCode, ingest_instance: DirectIngestInstance
) -> bool:
    region = direct_ingest_regions.get_direct_ingest_region(
        region_code=state_code.value.lower()
    )
    ingest_manifest_collector = IngestViewManifestCollector(
        region=region,
        delegate=StateSchemaIngestViewManifestCompilerDelegate(region=region),
    )
    return (
        len(
            ingest_manifest_collector.launchable_ingest_views(
                ingest_instance=ingest_instance
            )
        )
        > 0
    )


def ingest_pipeline_should_run_in_dag(
    state_code: StateCode, ingest_instance: DirectIngestInstance
) -> bool:
    """Returns True if we should run the ingest pipeline for this (state, instance),
    False otherwise.
    """
    if not direct_ingest_regions.get_direct_ingest_region(
        state_code.value.lower()
    ).is_ingest_launched_in_env():
        logging.info(
            "Ingest for [%s, %s] is not launched in environment [%s] - returning False",
            state_code.value,
            ingest_instance.value,
            environment.get_gcp_environment(),
        )
        return False

    if not _has_launchable_ingest_views(state_code, ingest_instance):
        logging.info(
            "No launchable views found for [%s, %s] - returning False",
            state_code.value,
            ingest_instance.value,
        )
        return False

    logging.info(
        "Ingest pipeline for [%s, %s] is eligible to run - returning True",
        state_code.value,
        ingest_instance.value,
    )
    return True


class IngestPipelineShouldRunInDagEntrypoint(EntrypointInterface):
    """Entrypoint for the ingest pipeline should run in dag check."""

    @staticmethod
    def get_parser() -> argparse.ArgumentParser:
        """Parses arguments for the ingest pipeline should run in dag check."""
        parser = argparse.ArgumentParser()

        parser.add_argument(
            "--state_code",
            help="The state code for which the ingest pipeline enabled status needs to be checked",
            type=StateCode,
            choices=list(StateCode),
            required=True,
        )

        parser.add_argument(
            "--ingest_instance",
            help="The ingest instance for which the ingest pipeline enabled status needs to be checked",
            type=DirectIngestInstance,
            choices=list(DirectIngestInstance),
            required=True,
        )

        return parser

    @staticmethod
    def run_entrypoint(args: argparse.Namespace) -> None:
        """Runs the raw data flashing check."""
        state_code = args.state_code
        ingest_instance = args.ingest_instance

        save_to_xcom(ingest_pipeline_should_run_in_dag(state_code, ingest_instance))
