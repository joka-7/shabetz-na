"""Reading working days and spreadsheets the way people actually write them."""

from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from shabetz.imports.days import DaysError, parse_weekdays
from shabetz.imports.tables import TableError, parse_delimited, read_table

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)
SUN_TO_THU = [MON, TUE, WED, THU, SUN]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Sun-Thu", SUN_TO_THU),
        ("sunday to thursday", SUN_TO_THU),
        ("א-ה", SUN_TO_THU),
        ("א׳-ה׳", SUN_TO_THU),
        ("ראשון עד חמישי", SUN_TO_THU),
        ("יום ראשון - יום חמישי", SUN_TO_THU),
        ("א', ב', ג'", [MON, TUE, SUN]),
        ("יום א, יום ו", [FRI, SUN]),
        ("Mon Tue Wed", [MON, TUE, WED]),
        ("mon, wed; fri", [MON, WED, FRI]),
        ("ראשון ושני", [MON, SUN]),
        ("sat and sun", [SAT, SUN]),
        # A range may run past the end of the week.
        ("Fri-Mon", [MON, FRI, SAT, SUN]),
        ("כל השבוע", list(range(7))),
        ("every day", list(range(7))),
    ],
)
def test_working_days_in_english_and_hebrew(text: str, expected: list[int]) -> None:
    assert parse_weekdays(text) == expected


def test_a_lone_vav_is_friday_not_and() -> None:
    assert parse_weekdays("א ו") == [FRI, SUN]


@pytest.mark.parametrize("text", ["1,2,3", "someday", "Mon, Funday", ""])
def test_unreadable_days_are_refused_rather_than_dropped(text: str) -> None:
    """Numbers are ambiguous (is 1 Sunday or Monday?) so they are refused too."""
    with pytest.raises(DaysError):
        parse_weekdays(text)


# -------------------------------------------------------------------- tables


def test_pasted_spreadsheet_cells_split_on_tabs_even_with_commas_inside() -> None:
    text = "Name\tDivision\nCohen, Dana\tNorth\n"
    assert parse_delimited(text) == [["Name", "Division"], ["Cohen, Dana", "North"]]


def test_quoted_csv() -> None:
    assert parse_delimited('name,division\n"Levi, Avi",South\n') == [
        ["name", "division"],
        ["Levi, Avi", "South"],
    ]


def test_semicolon_csv_from_european_excel() -> None:
    assert parse_delimited("a;b\n1;2") == [["a", "b"], ["1", "2"]]


def test_a_plain_list_is_one_column() -> None:
    assert parse_delimited("Dana\nAvi\n") == [["Dana"], ["Avi"]]


def test_hebrew_csv_saved_by_excel_in_windows_1255() -> None:
    data = "שם,מחלקה\nדנה,צפון\n".encode("cp1255")
    assert read_table(data, "roster.csv") == [["שם", "מחלקה"], ["דנה", "צפון"]]


def test_utf8_csv_with_a_byte_order_mark() -> None:
    data = "﻿שם\nדנה\n".encode()
    assert read_table(data, "roster.csv") == [["שם"], ["דנה"]]


def test_excel_workbook() -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Name", "Division", "Badge"])
    sheet.append(["Dana", "North", 1042.0])
    sheet.append([None, None, None])
    sheet.append(["Avi", None, None])
    buffer = io.BytesIO()
    workbook.save(buffer)

    assert read_table(buffer.getvalue(), "Roster.XLSX") == [
        ["Name", "Division", "Badge"],
        # A whole number stored as a float reads back as it was typed.
        ["Dana", "North", "1042"],
        ["Avi"],
    ]


def test_corrupt_workbook_is_a_clear_error() -> None:
    with pytest.raises(TableError) as caught:
        read_table(b"not a zip file", "roster.xlsx")
    assert caught.value.code == "unreadable_file"


def test_old_xls_is_refused_with_a_way_forward() -> None:
    with pytest.raises(TableError) as caught:
        read_table(b"\xd0\xcf\x11\xe0", "roster.xls")
    assert caught.value.code == "old_excel"
    assert ".xlsx" in str(caught.value)
