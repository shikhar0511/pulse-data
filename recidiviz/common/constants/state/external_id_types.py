# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2019 Recidiviz, Inc.
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

"""Strings representing different types of external ids ingested by our system.

NOTE: Changing ANY STRING VALUE in this file will require a database migration.
The Python values pointing to the strings can be renamed without issue.

At present, these are specifically for cataloging the kinds of ids ingested into
the StatePersonExternalId entity. In this context, the id types represent the
source that actually creates the id in the real world.
"""

# StatePersonExternalId.id_type

US_AR_OFFENDERID = "US_AR_OFFENDERID"
US_AR_PARTYID = "US_AR_PARTYID"

US_ID_DOC = "US_ID_DOC"
# TODO(#10703): Remove US_IX once Atlas is merged into US_ID
US_IX_DOC = "US_IX_DOC"
# Identifier for the type of state staff id provided by the Atlas system (EmployerId)
US_IX_EMPLOYEE = "US_IX_EMPLOYEE"
# Identifier for the type of state staff id provided by the legacy CIS system (empl_cd)
US_IX_CIS_EMPL_CD = "US_IX_CIS_EMPL_CD"
# Identifier for StaffId which is common across the Atlas system and the legacy CIS system
US_IX_STAFF_ID = "US_IX_STAFF_ID"
# IX Staff Email
US_IX_STAFF_EMAIL = "US_IX_STAFF_EMAIL"


US_MO_DOC = "US_MO_DOC"
US_MO_SID = "US_MO_SID"
US_MO_FBI = "US_MO_FBI"
US_MO_OLN = "US_MO_OLN"
# Identifier for the type of state staff id provided by the MO system
US_MO_STAFF_BADGE_NUMBER = "US_MO_STAFF_BADGE_NUMBER"

# OffenderId
US_CO_DOC = "US_CO_DOC"
# PersonId
US_CO_PID = "US_CO_PID"

# ND Elite ID - tracks someone across all incarceration stays
US_ND_ELITE = "US_ND_ELITE"
# ND Booking ID - tracks someone across incarceration stays that are related to
# the same sentence. A person may be associated with more than one Booking ID.
US_ND_ELITE_BOOKING = "US_ND_ELITE_BOOKING"
# ND State ID
US_ND_SID = "US_ND_SID"
# ND Supervision Officer ID - tracks employees of ND P&P
US_ND_DOCSTARS_OFFICER = "US_ND_DOCSTARS_OFFICER"
# ND Elite Employee ID - tracks employees who work in facilities
US_ND_ELITE_OFFICER = "US_ND_ELITE_OFFICER"

# OR ID_NUMBER
US_OR_ID = "US_OR_ID"
# RECORD_KEY linking tables, each person should only have one doc and id number
US_OR_RECORD_KEY = "US_OR_RECORD_KEY"
# CASELOAD, each staff member is assigned a CASELOAD
US_OR_CASELOAD = "US_OR_CASELOAD"

# PA Control Number - tracks someone across all incarceration stays (theoretically)
US_PA_CONT = "US_PA_CONT"
# PA Parole Number - tracks someone across all supervision terms (theoretically)
US_PA_PBPP = "US_PA_PBPP"
# PA Inmate Number - associated with a single contiguous incarceration stay
US_PA_INMATE = "US_PA_INMATE"
# PA PBPP Employee Number - tracks employees of PBPP
US_PA_PBPP_EMPLOYEE_NUM = "US_PA_PBPP_EMPLOYEE_NUM"

US_TN_DOC = "US_TN_DOC"
# Identifier for the type of state staff id provided by the TN system
US_TN_STAFF_TOMIS = "US_TN_STAFF_TOMIS"

US_ME_DOC = "US_ME_DOC"
# Identifier for the type of state staff id provided by the ME system
US_ME_EMPLOYEE = "US_ME_EMPLOYEE"

# MI Offender Number
US_MI_DOC = "US_MI_DOC"
# MI Offender ID
US_MI_DOC_ID = "US_MI_DOC_ID"
# MI Offender Booking
US_MI_DOC_BOOK = "US_MI_DOC_BOOK"
# Identifier for the type of state staff id provided by the MI COMPAS system
US_MI_COMPAS_USER = "US_MI_COMPAS_USER"
# Identifier for the type of state staff id provided by the MI OMNI system
US_MI_OMNI_USER = "US_MI_OMNI_USER"

# CA Offender Number
US_CA_DOC = "US_CA_DOC"
# CA Staff Badge Number
US_CA_BADGE_NO = "US_CA_BADGE_NO"
# CA Staff Email
US_CA_STAFF_EMAIL = "US_CA_STAFF_EMAIL"

# NC DOC ID Number
US_NC_DOC_INMATE = "US_NC_DOC_INMATE"

# OZ ID types
US_OZ_VFDS = "US_OZ_VFDS"
US_OZ_INTERNDS = "US_OZ_INTERNDS"
US_OZ_ND = "US_OZ_ND"
US_OZ_GLOFS = "US_OZ_GLOFS"
US_OZ_EG = "US_OZ_EG"
US_OZ_AGEID_STAFF_ID = "US_OZ_AGEID_STAFF_ID"
US_OZ_AGEID_USER_ID = "US_OZ_AGEID_USER_ID"
US_OZ_LOTR_ID = "US_OZ_LOTR_ID"
US_OZ_SM = "US_OZ_SM"
US_OZ_HG_ID = "US_OZ_HG_ID"
US_OZ_EGT = "US_OZ_EGT"

# AZ Person ID Number (not necessarily resident or client)
US_AZ_PERSON_ID = "US_AZ_PERSON_ID"
# AZ DOC ID Number
US_AZ_DOC_ID = "US_AZ_DOC_ID"
