//! Deterministic JSON boundary shared with `xlsx.py`.
//!
//! The Python side normalizes a document spec into its `_Sheet` structures and
//! serializes them as:
//!
//! ```json
//! {"sheets": [{"name": "Weekly",
//!              "header": ["week", "units"],
//!              "rows": [[["str", "2026-W01"], ["num", 3], ["date", "2026-01-15"],
//!                        ["formula", "SUM(C2:C3)", 7]]],
//!              "freeze": true,
//!              "col_widths": [12.5, 8]}]}
//! ```
//!
//! A cell is a compact array: `["str", text]`, `["num", number]`,
//! `["date", "YYYY-MM-DD"]` or `["formula", expression, cached_number]`.
//! This module parses that shape and re-validates the bounds the Python normalizer
//! already enforces, so a native call can never write a workbook the pure-Python
//! path would reject.

use std::fmt;

use serde::de::{self, Deserializer, SeqAccess, Visitor};
use serde::Deserialize;

use crate::error::WriteError;

/// Hutch bounds; mirrored from `src/hutch/documents/docgen/xlsx.py`.
pub const MAX_SHEETS: usize = 20;
pub const MAX_SHEET_ROWS: usize = 100_000;
pub const MAX_SHEET_COLS: usize = 256;
pub const MAX_COL_WIDTH: f64 = 255.0;
/// Excel's hard cell-text limit; XlsxWriter silently truncates past it.
pub const MAX_CELL_CHARS: usize = 32_767;

/// Days between the 1899-12-30 epoch and 1970-01-01.
const UNIX_EPOCH_OFFSET_DAYS: i64 = 25_569;

#[derive(Debug, Clone, PartialEq)]
pub enum Cell {
    Str(String),
    Num(f64),
    /// Days since 1899-12-30 (the Excel 1900 date system epoch).
    Date(i64),
    Formula {
        expr: String,
        cached: f64,
    },
}

#[derive(Debug, Clone, PartialEq)]
pub struct Sheet {
    pub name: String,
    pub header: Vec<String>,
    pub rows: Vec<Vec<Cell>>,
    pub freeze: bool,
    pub col_widths: Vec<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WorkbookSpec {
    pub sheets: Vec<Sheet>,
}

/// Parse and validate the normalized sheet JSON.
pub fn parse(spec_json: &str) -> Result<WorkbookSpec, WriteError> {
    let raw: RawWorkbook = serde_json::from_str(spec_json).map_err(|error| {
        WriteError::invalid(format!("native spec JSON could not be decoded: {error}"))
    })?;
    validate(raw)
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RawWorkbook {
    sheets: Vec<RawSheet>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RawSheet {
    name: String,
    #[serde(default)]
    header: Vec<String>,
    #[serde(default)]
    rows: Vec<Vec<Cell>>,
    #[serde(default)]
    freeze: bool,
    #[serde(default)]
    col_widths: Vec<f64>,
}

fn validate(raw: RawWorkbook) -> Result<WorkbookSpec, WriteError> {
    if raw.sheets.is_empty() {
        return Err(WriteError::invalid(
            "a workbook must hold at least one sheet",
        ));
    }
    if raw.sheets.len() > MAX_SHEETS {
        return Err(WriteError::invalid(format!(
            "a workbook may hold at most {MAX_SHEETS} sheets"
        )));
    }
    let mut used: Vec<String> = Vec::with_capacity(raw.sheets.len());
    let mut sheets = Vec::with_capacity(raw.sheets.len());
    for (index, raw_sheet) in raw.sheets.into_iter().enumerate() {
        sheets.push(raw_sheet.validate(index, &mut used)?);
    }
    Ok(WorkbookSpec { sheets })
}

impl RawSheet {
    fn validate(self, index: usize, used: &mut Vec<String>) -> Result<Sheet, WriteError> {
        let RawSheet {
            name,
            header,
            rows,
            freeze,
            col_widths,
        } = self;
        validate_sheet_name(&name, used).map_err(|error| match error {
            WriteError::InvalidSpec(detail) => {
                WriteError::invalid(format!("sheet {index}: {detail}"))
            }
            other => other,
        })?;
        if header.len() > MAX_SHEET_COLS {
            return Err(WriteError::invalid(format!(
                "sheet {index} exceeds {MAX_SHEET_COLS} columns"
            )));
        }
        if rows.len() > MAX_SHEET_ROWS {
            return Err(WriteError::invalid(format!(
                "sheet {index} exceeds {MAX_SHEET_ROWS} rows"
            )));
        }
        let mut width = header.len();
        for (row_index, row) in rows.iter().enumerate() {
            if row.len() > MAX_SHEET_COLS {
                return Err(WriteError::invalid(format!(
                    "sheet {index} row {} exceeds {MAX_SHEET_COLS} columns",
                    row_index + 1
                )));
            }
            width = width.max(row.len());
        }
        if freeze && header.is_empty() {
            return Err(WriteError::invalid(format!(
                "sheet {index}: 'freeze' requires a 'header'"
            )));
        }
        if col_widths.len() > width {
            return Err(WriteError::invalid(format!(
                "sheet {index}: 'col_widths' covers {} columns but the sheet has {width}",
                col_widths.len()
            )));
        }
        for (col_index, width_value) in col_widths.iter().enumerate() {
            if !width_value.is_finite() || *width_value < 0.0 || *width_value > MAX_COL_WIDTH {
                return Err(WriteError::invalid(format!(
                    "sheet {index} column {}: column widths must be between 0 and {MAX_COL_WIDTH}",
                    col_index + 1
                )));
            }
        }
        for (row_index, row) in rows.iter().enumerate() {
            for (col_index, cell) in row.iter().enumerate() {
                validate_cell(cell).map_err(|error| match error {
                    WriteError::InvalidSpec(detail) => WriteError::invalid(format!(
                        "sheet {index} row {} column {}: {detail}",
                        row_index + 1,
                        col_index + 1
                    )),
                    other => other,
                })?;
            }
        }
        for (col_index, text) in header.iter().enumerate() {
            if text.chars().count() > MAX_CELL_CHARS {
                return Err(WriteError::invalid(format!(
                    "sheet {index} header column {}: text exceeds {MAX_CELL_CHARS} characters",
                    col_index + 1
                )));
            }
        }
        Ok(Sheet {
            name,
            header,
            rows,
            freeze,
            col_widths,
        })
    }
}

fn validate_cell(cell: &Cell) -> Result<(), WriteError> {
    match cell {
        Cell::Str(text) if text.chars().count() > MAX_CELL_CHARS => Err(WriteError::invalid(
            format!("text exceeds Excel's {MAX_CELL_CHARS} character cell limit"),
        )),
        Cell::Num(number) if !number.is_finite() => {
            Err(WriteError::invalid("numbers must be finite"))
        }
        Cell::Formula { expr, .. } if expr.is_empty() => Err(WriteError::invalid(
            "a formula cell needs a non-empty expression",
        )),
        Cell::Formula { cached, .. } if !cached.is_finite() => Err(WriteError::invalid(
            "a formula cell's cached value must be finite",
        )),
        _ => Ok(()),
    }
}

/// Excel sheet-name rules, matching `xlsx.py` normalization + XlsxWriter validation.
fn validate_sheet_name(name: &str, used: &mut Vec<String>) -> Result<(), WriteError> {
    if name.is_empty() {
        return Err(WriteError::invalid("sheet name cannot be blank"));
    }
    if name.chars().count() > 31 {
        return Err(WriteError::invalid(
            "sheet name cannot exceed 31 characters",
        ));
    }
    if name
        .chars()
        .any(|c| matches!(c, '[' | ']' | ':' | '*' | '?' | '/' | '\\'))
    {
        return Err(WriteError::invalid(
            "sheet name cannot contain any of the characters [ ] : * ? / \\",
        ));
    }
    if name.starts_with('\'') || name.ends_with('\'') {
        return Err(WriteError::invalid(
            "sheet name cannot start or end with an apostrophe",
        ));
    }
    if name.eq_ignore_ascii_case("history") {
        return Err(WriteError::invalid(
            "sheet name 'History' is reserved by Excel",
        ));
    }
    if used
        .iter()
        .any(|existing| existing.eq_ignore_ascii_case(name))
    {
        return Err(WriteError::invalid(
            "sheet name is already in use in this workbook",
        ));
    }
    used.push(name.to_owned());
    Ok(())
}

/// Normalize a formula the way `xlsx.py` does: strip leading `=` signs, then whitespace.
pub fn normalize_formula(raw: &str) -> String {
    raw.trim_start_matches('=').trim().to_owned()
}

/// Parse `YYYY-MM-DD` into Excel 1900-date-system serial days.
pub fn parse_iso_date(text: &str) -> Result<i64, String> {
    let bytes = text.as_bytes();
    if bytes.len() != 10 || bytes[4] != b'-' || bytes[7] != b'-' {
        return Err("'date' must be a 'YYYY-MM-DD' string".to_owned());
    }
    let year = parse_digits(&text[0..4])? as i32;
    let month = parse_digits(&text[5..7])?;
    let day = parse_digits(&text[8..10])?;
    if year < 1 {
        return Err("'date' years must be between 1 and 9999".to_owned());
    }
    if !(1..=12).contains(&month) {
        return Err(format!("{text:?} is not a real calendar date"));
    }
    let max_day = days_in_month(year, month);
    if day < 1 || day > max_day {
        return Err(format!("{text:?} is not a real calendar date"));
    }
    Ok(days_from_civil(year, month, day) + UNIX_EPOCH_OFFSET_DAYS)
}

fn parse_digits(part: &str) -> Result<u32, String> {
    if part.bytes().all(|b| b.is_ascii_digit()) {
        part.parse::<u32>()
            .map_err(|_| "date component out of range".to_owned())
    } else {
        Err("'date' must be a 'YYYY-MM-DD' string".to_owned())
    }
}

fn days_in_month(year: i32, month: u32) -> u32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if is_leap_year(year) => 29,
        _ => 28,
    }
}

fn is_leap_year(year: i32) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

/// Days since 1970-01-01 for a proleptic Gregorian date (Howard Hinnant's algorithm).
fn days_from_civil(year: i32, month: u32, day: u32) -> i64 {
    let year = if month <= 2 { year - 1 } else { year };
    let era = if year >= 0 { year } else { year - 399 } / 400;
    let year_of_era = (year - era * 400) as i64;
    let month_prime = ((month + 9) % 12) as i64;
    let day_of_year = (153 * month_prime + 2) / 5 + day as i64 - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era as i64 * 146_097 + day_of_era - 719_468
}

struct CellVisitor;

impl<'de> Visitor<'de> for CellVisitor {
    type Value = Cell;

    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a [kind, value] cell array")
    }

    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Self::Value, A::Error> {
        let kind: String = seq
            .next_element()?
            .ok_or_else(|| de::Error::invalid_length(0, &"a [kind, value] cell array"))?;
        let cell = match kind.as_str() {
            "str" => Cell::Str(next_value(&mut seq, &kind)?),
            "num" => Cell::Num(next_value(&mut seq, &kind)?),
            "date" => {
                let text: String = next_value(&mut seq, &kind)?;
                let days = parse_iso_date(&text).map_err(de::Error::custom)?;
                Cell::Date(days)
            }
            "formula" => {
                let raw: String = next_value(&mut seq, &kind)?;
                let cached: f64 = next_value(&mut seq, &kind)?;
                Cell::Formula {
                    expr: normalize_formula(&raw),
                    cached,
                }
            }
            other => {
                return Err(de::Error::unknown_variant(
                    other,
                    &["str", "num", "date", "formula"],
                ))
            }
        };
        if seq.next_element::<de::IgnoredAny>()?.is_some() {
            return Err(de::Error::custom(format!(
                "a {kind:?} cell has too many elements"
            )));
        }
        Ok(cell)
    }
}

fn next_value<'de, A, T>(seq: &mut A, kind: &str) -> Result<T, A::Error>
where
    A: SeqAccess<'de>,
    T: Deserialize<'de>,
{
    seq.next_element()?
        .ok_or_else(|| de::Error::custom(format!("a {kind:?} cell is missing its value")))
}

impl<'de> Deserialize<'de> for Cell {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        deserializer.deserialize_seq(CellVisitor)
    }
}

#[cfg(test)]
mod tests;
