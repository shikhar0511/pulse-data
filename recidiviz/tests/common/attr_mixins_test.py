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
"""Tests for BuildableAttr base class."""

import unittest
from datetime import date
from enum import Enum
from typing import Dict, List, Optional

import attr

from recidiviz.common.attr_mixins import (
    BuildableAttr,
    BuildableAttrFieldType,
    BuilderException,
    CachedAttributeInfo,
    DefaultableAttr,
    _clear_class_structure_reference,
    _get_class_structure_reference,
    attr_field_enum_cls_for_field_name,
    attr_field_type_for_field_name,
    attribute_field_type_reference_for_class,
)


@attr.s
class FakeBuildableAttr(BuildableAttr):
    required_field: str = attr.ib()
    field_with_default: List[str] = attr.ib(factory=list)


@attr.s
class FakeDefaultableAttr(DefaultableAttr):
    field: str = attr.ib()
    field_another: Optional[int] = attr.ib()
    field_with_default: int = attr.ib(default=1)
    factory_field: List[int] = attr.ib(factory=list)


class FakeEnum(Enum):
    A = "A"
    B = "B"


class InvalidFakeEnum(Enum):
    A = "A"
    C = "C"
    D = "D"


@attr.s
class FakeBuildableAttrDeluxe(BuildableAttr):
    required_field: str = attr.ib()
    another_required_field: str = attr.ib()
    enum_nonnull_field: FakeEnum = attr.ib()
    enum_field: Optional[FakeEnum] = attr.ib(default=None)
    date_field: Optional[date] = attr.ib(default=None)
    boolean_field: Optional[bool] = attr.ib(default=None)
    field_list: List[str] = attr.ib(factory=list)
    field_forward_ref: Optional["FakeBuildableAttr"] = attr.ib(default=None)


class BuildableAttrTests(unittest.TestCase):
    """Tests for BuildableAttr base class."""

    def testBuild_WithRequiredFields_BuildsAttr(self) -> None:
        # Arrange
        subject = FakeBuildableAttr.builder()
        subject.required_field = "TEST"

        # Act
        result = subject.build()

        # Assert
        expected_result = FakeBuildableAttr(
            required_field="TEST", field_with_default=[]
        )

        self.assertEqual(result, expected_result)

    def testBuild_MissingRequiredField_RaisesException(self) -> None:
        # Arrange
        subject = FakeBuildableAttr.builder()

        # Act + Assert
        with self.assertRaises(BuilderException):
            subject.build()

    def testBuild_ExtraField_RaisesException(self) -> None:
        # Arrange
        subject = FakeBuildableAttr.builder()
        subject.required_field = "TEST"
        subject.not_a_real_field = "TEST_2"

        # Act + Assert
        with self.assertRaises(BuilderException):
            subject.build()

    def testInstantiateAbstractBuildableAttr_RaisesException(self) -> None:
        with self.assertRaises(Exception):
            BuildableAttr()

    def testNewWithDefaults(self) -> None:
        # Arrange
        subject = FakeDefaultableAttr.new_with_defaults(field="field")

        # Assert
        expected_result = FakeDefaultableAttr(
            field="field", field_another=None, field_with_default=1, factory_field=[]
        )

        self.assertEqual(subject, expected_result)

    def testInstantiateDefaultableAttr_RaisesException(self) -> None:
        with self.assertRaises(Exception):
            DefaultableAttr()

    def testBuildFromDictionary(self) -> None:
        # Construct dictionary representation
        subject_dict = {
            "required_field": "value",
            "another_required_field": "another_value",
            "enum_nonnull_field": FakeEnum.A.value,
            "enum_field": FakeEnum.B.value,
        }

        # Build from dictionary
        subject = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

        # Assert
        expected_result = FakeBuildableAttrDeluxe(
            required_field="value",
            another_required_field="another_value",
            enum_nonnull_field=FakeEnum.A,
            enum_field=FakeEnum.B,
        )

        self.assertEqual(subject, expected_result)

    def testBuildFromDictionary_Enum(self) -> None:
        # Construct dictionary representation
        subject_dict = {
            "required_field": "value",
            "another_required_field": "another_value",
            "enum_nonnull_field": FakeEnum.A,
        }

        # Build from dictionary
        subject = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

        # Assert
        expected_result = FakeBuildableAttrDeluxe(
            required_field="value",
            another_required_field="another_value",
            enum_nonnull_field=FakeEnum.A,
        )

        self.assertEqual(subject, expected_result)

    def testBuildFromDictionary_MissingRequiredArgs(self) -> None:
        with self.assertRaises(Exception):
            # Construct dictionary representation
            subject_dict = {"required_field": "value"}

            # Build from dictionary
            _ = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

    def testBuildFromDictionary_MissingNonnullEnum(self) -> None:
        with self.assertRaises(Exception):
            # Construct dictionary representation
            subject_dict = {
                "required_field": "value",
                "another_required_field": "another_value",
            }

            # Build from dictionary
            _ = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

    def testBuildFromDictionary_EmptyDict(self) -> None:
        with self.assertRaises(ValueError):
            _ = FakeBuildableAttr.build_from_dictionary({})

    def testBuildFromDictionary_ExtraArguments(self) -> None:
        # Construct dictionary representation
        subject_dict = {
            "required_field": "value",
            "another_required_field": "another_value",
            "enum_nonnull_field": FakeEnum.A.value,
            "extra_invalid_field": "extra_value",
        }

        # Build from dictionary
        subject = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

        # Assert
        expected_result = FakeBuildableAttrDeluxe(
            required_field="value",
            another_required_field="another_value",
            enum_nonnull_field=FakeEnum.A,
        )

        self.assertEqual(subject, expected_result)

    def testBuildFromDictionary_WrongEnum(self) -> None:
        with self.assertRaises(ValueError):
            # Construct dictionary representation
            subject_dict = {
                "required_field": "value",
                "another_required_field": "another_value",
                "enum_field": InvalidFakeEnum.C,
            }

            # Build from dictionary
            _ = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

    def testBuildFromDictionary_WrongEnumSameValue(self) -> None:
        with self.assertRaises(ValueError):
            # Construct dictionary representation
            subject_dict = {
                "required_field": "value",
                "another_required_field": "another_value",
                "enum_field": InvalidFakeEnum.A,
            }

            # Build from dictionary
            _ = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

    def testBuildFromDictionary_ListInDict(self) -> None:
        # Construct dictionary representation
        subject_dict = {
            "required_field": "value",
            "another_required_field": "another_value",
            "enum_nonnull_field": FakeEnum.A,
            "field_list": ["a", "b", "c"],
        }

        subject = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

        # Assert
        expected_result = FakeBuildableAttrDeluxe(
            required_field="value",
            another_required_field="another_value",
            enum_nonnull_field=FakeEnum.A,
            field_list=["a", "b", "c"],
        )

        self.assertEqual(subject, expected_result)

    def testBuildFromDictionary_InvalidForwardRefInDict(self) -> None:
        with self.assertRaises(ValueError):
            # Construct dictionary representation
            subject_dict = {
                "required_field": "value",
                "another_required_field": "another_value",
                "field_forward_ref": FakeBuildableAttr("a", ["a", "b"]),
            }

            # Build from dictionary
            _ = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

    def testBuildFromDictionary_WithDate(self) -> None:
        # Construct dictionary representation
        subject_dict = {
            "required_field": "value",
            "another_required_field": "another_value",
            "enum_nonnull_field": FakeEnum.A.value,
            "date_field": "2001-01-08",
        }

        # Build from dictionary
        subject = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

        # Assert
        expected_result = FakeBuildableAttrDeluxe(
            required_field="value",
            another_required_field="another_value",
            enum_nonnull_field=FakeEnum.A,
            date_field=date.fromisoformat("2001-01-08"),
        )

        self.assertEqual(subject, expected_result)

    def testBuildFromDictionary_WithEmptyDate(self) -> None:
        # Construct dictionary representation
        subject_dict = {
            "required_field": "value",
            "another_required_field": "another_value",
            "enum_nonnull_field": FakeEnum.A.value,
            "date_field": None,
        }

        # Build from dictionary
        subject = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

        # Assert
        expected_result = FakeBuildableAttrDeluxe(
            required_field="value",
            another_required_field="another_value",
            enum_nonnull_field=FakeEnum.A,
            date_field=None,
        )

        self.assertEqual(subject, expected_result)

    def testBuildFromDictionary_WithInvalidDateFormat(self) -> None:
        with self.assertRaises(ValueError):
            # Construct dictionary representation
            subject_dict = {
                "required_field": "value",
                "another_required_field": "another_value",
                "enum_nonnull_field": FakeEnum.A.value,
                "date_field": "01-01-1999",
            }

            # Build from dictionary
            _ = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

    def testBuildFromDictionary_WithInvalidDateString(self) -> None:
        with self.assertRaises(ValueError):
            # Construct dictionary representation
            subject_dict = {
                "required_field": "value",
                "another_required_field": "another_value",
                "enum_nonnull_field": FakeEnum.A.value,
                "date_field": "YYYY-MM-DD",
            }

            # Build from dictionary
            _ = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)


class CachedClassStructureReferenceTests(unittest.TestCase):
    """Tests the functionality of the cached _class_structure_reference."""

    def testCachedClassStructureReference(self) -> None:
        """Tests that the cached _class_structure_reference contains the attr field
        ref for the FakeBuildableAttrDeluxe class after the build_from_dictionary
        function was called on the class."""
        # Clear the _class_structure_reference cache
        _clear_class_structure_reference()

        class_structure_reference = _get_class_structure_reference()
        self.assertEqual({}, class_structure_reference)

        # Construct dictionary representation
        subject_dict = {
            "required_field": "value",
            "another_required_field": "another_value",
            "enum_nonnull_field": FakeEnum.A.value,
            "date_field": "2001-01-08",
        }

        # Build from dictionary
        subject = FakeBuildableAttrDeluxe.build_from_dictionary(subject_dict)

        # Assert
        expected_result = FakeBuildableAttrDeluxe(
            required_field="value",
            another_required_field="another_value",
            enum_nonnull_field=FakeEnum.A,
            date_field=date.fromisoformat("2001-01-08"),
        )

        self.assertEqual(expected_result, subject)

        cached_class_structure_reference = _get_class_structure_reference()

        self.assertIsNotNone(
            cached_class_structure_reference.get(FakeBuildableAttrDeluxe)
        )

    def testAttributeFieldTypeReferenceForClass(self) -> None:
        """Tests that the attribute_field_type_reference_for_class function returns
        the expected mapping from Attribute to BuildableAttrFieldType."""
        # Clear the _class_structure_reference cache
        _clear_class_structure_reference()

        attributes = attr.fields_dict(FakeBuildableAttrDeluxe).values()

        expected_attr_field_type_ref: Dict[str, CachedAttributeInfo] = {}
        for attribute in attributes:
            name = attribute.name
            if "enum" in name:
                enum_cls = FakeEnum

                expected_attr_field_type_ref[name] = CachedAttributeInfo(
                    attribute=attribute,
                    field_type=BuildableAttrFieldType.ENUM,
                    enum_cls=enum_cls,
                    referenced_cls_name=None,
                )
            elif "date" in attribute.name:
                expected_attr_field_type_ref[name] = CachedAttributeInfo(
                    attribute=attribute,
                    field_type=BuildableAttrFieldType.DATE,
                    enum_cls=None,
                    referenced_cls_name=None,
                )
            elif "bool" in attribute.name:
                expected_attr_field_type_ref[name] = CachedAttributeInfo(
                    attribute=attribute,
                    field_type=BuildableAttrFieldType.BOOLEAN,
                    enum_cls=None,
                    referenced_cls_name=None,
                )
            elif "forward_ref" in attribute.name:
                expected_attr_field_type_ref[name] = CachedAttributeInfo(
                    attribute=attribute,
                    field_type=BuildableAttrFieldType.FORWARD_REF,
                    enum_cls=None,
                    referenced_cls_name="FakeBuildableAttr",
                )
            elif "list" in attribute.name:
                expected_attr_field_type_ref[name] = CachedAttributeInfo(
                    attribute=attribute,
                    field_type=BuildableAttrFieldType.LIST,
                    enum_cls=None,
                    referenced_cls_name=None,
                )
            elif "required" in attribute.name:
                expected_attr_field_type_ref[name] = CachedAttributeInfo(
                    attribute=attribute,
                    field_type=BuildableAttrFieldType.STRING,
                    enum_cls=None,
                    referenced_cls_name=None,
                )
            else:
                expected_attr_field_type_ref[name] = CachedAttributeInfo(
                    attribute=attribute,
                    field_type=BuildableAttrFieldType.OTHER,
                    enum_cls=None,
                    referenced_cls_name=None,
                )

        attr_field_type_ref = attribute_field_type_reference_for_class(
            FakeBuildableAttrDeluxe
        )

        self.assertEqual(expected_attr_field_type_ref, attr_field_type_ref)


class TestAttrFieldTypeForFieldName(unittest.TestCase):
    """Tests the attr_field_type_for_field_name function."""

    def test_attr_field_type_for_field_name(self) -> None:
        self.assertEqual(
            BuildableAttrFieldType.ENUM,
            attr_field_type_for_field_name(FakeBuildableAttrDeluxe, "enum_field"),
        )

        self.assertEqual(
            BuildableAttrFieldType.DATE,
            attr_field_type_for_field_name(FakeBuildableAttrDeluxe, "date_field"),
        )

        self.assertEqual(
            BuildableAttrFieldType.FORWARD_REF,
            attr_field_type_for_field_name(
                FakeBuildableAttrDeluxe, "field_forward_ref"
            ),
        )

        self.assertEqual(
            BuildableAttrFieldType.LIST,
            attr_field_type_for_field_name(FakeBuildableAttrDeluxe, "field_list"),
        )
        self.assertEqual(
            BuildableAttrFieldType.BOOLEAN,
            attr_field_type_for_field_name(FakeBuildableAttrDeluxe, "boolean_field"),
        )


class TestAttrFieldEnumClsForFieldName(unittest.TestCase):
    """Tests the attr_field_enum_cls_for_field_name function."""

    def test_attr_enum_cls_for_field_name(self) -> None:
        self.assertEqual(
            FakeEnum,
            attr_field_enum_cls_for_field_name(FakeBuildableAttrDeluxe, "enum_field"),
        )

        self.assertIsNone(
            attr_field_enum_cls_for_field_name(FakeBuildableAttrDeluxe, "date_field")
        )

        self.assertIsNone(
            attr_field_enum_cls_for_field_name(
                FakeBuildableAttrDeluxe, "field_forward_ref"
            )
        )

        self.assertIsNone(
            attr_field_enum_cls_for_field_name(FakeBuildableAttrDeluxe, "field_list")
        )
