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

from typing import List, Tuple, Union

class Checksum:
    def __init__(self) -> None: ...
    def update(self, chunk: Union[bytes, List[int], Tuple[int]]) -> None: ...
    def digest(self) -> bytes: ...

def extend(crc: int, chunk: Union[bytes, List[int], Tuple[int]]) -> int: ...
def value(chunk: Union[bytes, List[int], Tuple[int]]) -> int: ...
