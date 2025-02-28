# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2024 Recidiviz, Inc.
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
"""Class for holding BigQuery source tables"""
from functools import cached_property
from typing import Any

import attr
from more_itertools import one

from recidiviz.big_query.big_query_address import BigQueryAddress
from recidiviz.source_tables.source_table_config import (
    SourceTableCollection,
    SourceTableConfig,
    SourceTableCouldNotGenerateError,
    SourceTableLabel,
)


@attr.s(auto_attribs=True)
class SourceTableRepository:
    """The SourceTableRepository aggregates definitions of all source tables in our view graph."""

    source_table_collections: list[SourceTableCollection] = attr.ib(factory=list)

    @cached_property
    def source_tables(self) -> dict[BigQueryAddress, SourceTableConfig]:
        return {
            source_table.address: source_table
            for collection in self.source_table_collections
            for source_table in collection.source_tables
        }

    def get_collections(
        self, labels: dict[type[SourceTableLabel], Any]
    ) -> list[SourceTableCollection]:
        return [
            collection
            for collection in self.source_table_collections
            if all(
                collection.has_label(label, value) for label, value in labels.items()
            )
        ]

    def get_collection(
        self, labels: dict[type[SourceTableLabel], Any]
    ) -> SourceTableCollection:
        return one(self.get_collections(labels=labels))

    def build_config(self, address: BigQueryAddress) -> SourceTableConfig:
        try:
            return self.source_tables[address]
        except KeyError as e:
            raise SourceTableCouldNotGenerateError from e
