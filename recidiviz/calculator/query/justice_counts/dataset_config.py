# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2020 Recidiviz, Inc.
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
"""Various BigQuery datasets."""

# Transitional dataset in the same region (e.g. us-east1) as the Justice Counts CloudSQL
# instance where Justice Counts CloudSQL data is stored before the CloudSQL -> BQ refresh
# copies it to a dataset in the 'US' multi-region.
JUSTICE_COUNTS_BASE_REGIONAL_DATASET: str = "justice_counts_regional"

# Where the base tables for the JusticeCounts schema live
JUSTICE_COUNTS_BASE_DATASET: str = "justice_counts"

# Where the calculations for Corrections data live
JUSTICE_COUNTS_CORRECTIONS_DATASET: str = "justice_counts_corrections"

# Where the calculations for Jails data live
JUSTICE_COUNTS_JAILS_DATASET: str = "justice_counts_jails"

# Where the views that are exported to the dashboard live
JUSTICE_COUNTS_DASHBOARD_DATASET: str = "justice_counts_dashboard"
