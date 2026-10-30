//! Render a validated `WorkbookSpec` with rust_xlsxwriter.
//!
//! Mirrors `xlsx.py::_write_workbook`: strings stay text (`write_string`), numbers stay
//! numeric (`write_number`), dates are 1900-date-system serials carrying a
//! `yyyy-mm-dd` number format, formulas are written with their declared cached result
//! (`Formula::set_result`) in an auto-calc workbook, the header row freezes when asked,
//! and column widths are set per column. Sheet order and sheet names are preserved.
//!
//! ## Empty strings
//!
//! rust_xlsxwriter deliberately drops empty strings ("Excel ignores them"), but the
//! reference writer (XlsxWriter) stores them as shared text so ``` round-trips through
//! the openpyxl read-back gate. To match that, empty cells are written as a unique
//! placeholder run and the `xl/sharedStrings.xml` entry is rewritten to an empty
//! `<t></t>` after the archive is saved. The rewrite touches one shared-string entry and
//! is skipped entirely when a workbook contains no empty-string cells.

use std::io::{Cursor, Read, Write};

use rust_xlsxwriter::{Format, Formula, Workbook, Worksheet, XlsxError};

use crate::error::WriteError;
use crate::spec::{Cell, WorkbookSpec};

/// Format for date cells; the same `yyyy-mm-dd` format the Python writer attaches.
const DATE_FORMAT: &str = "yyyy-mm-dd";
/// Base of the placeholder text written for empty-text cells (Unicode private use area).
const EMPTY_SENTINEL: char = '\u{E000}';

pub fn write_workbook(spec: &WorkbookSpec) -> Result<Vec<u8>, WriteError> {
    let mut workbook = Workbook::new();
    // rust_xlsxwriter writes `<calcPr fullCalcOnLoad="1"/>` by default, matching the
    // Python writer's `set_calc_mode("auto")`; the hutch gate asserts on that marker.
    let date_format = Format::new().set_num_format(DATE_FORMAT);
    let empty_sentinel = choose_empty_sentinel(spec);
    for sheet in &spec.sheets {
        let worksheet = workbook.add_worksheet();
        worksheet.set_name(&sheet.name).map_err(render_error)?;
        write_sheet(worksheet, sheet, &date_format, empty_sentinel.as_deref())?;
    }
    let data = workbook.save_to_buffer().map_err(render_error)?;
    match empty_sentinel {
        Some(sentinel) => rewrite_empty_string_entry(&data, &sentinel),
        None => Ok(data),
    }
}

/// Pick a placeholder that cannot collide with user-visible text, if any cell is empty.
fn choose_empty_sentinel(spec: &WorkbookSpec) -> Option<String> {
    let any_empty = spec.sheets.iter().any(|sheet| {
        sheet.rows.iter().any(|row| {
            row.iter()
                .any(|cell| matches!(cell, Cell::Str(text) if text.is_empty()))
        })
    });
    if !any_empty {
        return None;
    }
    let mut sentinel = String::from(EMPTY_SENTINEL);
    while workbook_contains(spec, &sentinel) {
        sentinel.push(EMPTY_SENTINEL);
    }
    Some(sentinel)
}

fn workbook_contains(spec: &WorkbookSpec, needle: &str) -> bool {
    spec.sheets.iter().any(|sheet| {
        sheet.header.iter().any(|text| text.contains(needle))
            || sheet.rows.iter().any(|row| {
                row.iter().any(|cell| match cell {
                    Cell::Str(text) => text.contains(needle),
                    Cell::Formula { expr, .. } => expr.contains(needle),
                    _ => false,
                })
            })
    })
}

fn write_sheet(
    worksheet: &mut Worksheet,
    sheet: &crate::spec::Sheet,
    date_format: &Format,
    empty_sentinel: Option<&str>,
) -> Result<(), WriteError> {
    let offset: u32 = if sheet.header.is_empty() { 0 } else { 1 };
    for (col, text) in sheet.header.iter().enumerate() {
        worksheet
            .write_string(0, col_u16(col), text)
            .map_err(render_error)?;
    }
    for (row, cells) in sheet.rows.iter().enumerate() {
        let excel_row = row as u32 + offset;
        for (col, cell) in cells.iter().enumerate() {
            write_cell(
                worksheet,
                excel_row,
                col_u16(col),
                cell,
                date_format,
                empty_sentinel,
            )?;
        }
    }
    if sheet.freeze {
        worksheet.set_freeze_panes(1, 0).map_err(render_error)?;
    }
    for (col, width) in sheet.col_widths.iter().enumerate() {
        worksheet
            .set_column_width(col_u16(col), *width)
            .map_err(render_error)?;
    }
    Ok(())
}

fn write_cell(
    worksheet: &mut Worksheet,
    row: u32,
    col: u16,
    cell: &Cell,
    date_format: &Format,
    empty_sentinel: Option<&str>,
) -> Result<(), WriteError> {
    match cell {
        Cell::Str(text) if text.is_empty() => {
            let placeholder = empty_sentinel
                .ok_or_else(|| WriteError::render("missing empty-text placeholder"))?;
            worksheet
                .write_string(row, col, placeholder)
                .map_err(render_error)?;
        }
        Cell::Str(text) => {
            worksheet
                .write_string(row, col, text)
                .map_err(render_error)?;
        }
        Cell::Num(number) => {
            worksheet
                .write_number(row, col, *number)
                .map_err(render_error)?;
        }
        Cell::Date(days) => {
            worksheet
                .write_number_with_format(row, col, *days as f64, date_format)
                .map_err(render_error)?;
        }
        Cell::Formula { expr, cached } => {
            let formula = Formula::new(format!("={expr}")).set_result(cached.to_string());
            worksheet
                .write_formula(row, col, formula)
                .map_err(render_error)?;
        }
    }
    Ok(())
}

/// Replace the placeholder shared-string entry with an empty text run.
fn rewrite_empty_string_entry(data: &[u8], sentinel: &str) -> Result<Vec<u8>, WriteError> {
    let mut archive = zip::ZipArchive::new(Cursor::new(data.to_vec())).map_err(render_error_zip)?;
    let mut output = zip::ZipWriter::new(Cursor::new(Vec::with_capacity(data.len())));
    let mut replaced = false;
    for index in 0..archive.len() {
        let mut entry = archive.by_index(index).map_err(render_error_zip)?;
        let name = entry.name().to_owned();
        let mut bytes = Vec::with_capacity(entry.size() as usize);
        entry.read_to_end(&mut bytes).map_err(render_error_io)?;
        if name == "xl/sharedStrings.xml" {
            bytes = replace_sentinel_text(&bytes, sentinel)?;
            replaced = true;
        }
        let options = zip::write::SimpleFileOptions::default()
            .compression_method(zip::CompressionMethod::Deflated);
        output
            .start_file(&name, options)
            .map_err(render_error_zip)?;
        output.write_all(&bytes).map_err(render_error_io)?;
    }
    if !replaced {
        return Err(WriteError::render(
            "the saved archive has no shared strings; cannot store empty text cells",
        ));
    }
    let cursor = output.finish().map_err(render_error_zip)?;
    Ok(cursor.into_inner())
}

fn replace_sentinel_text(shared_strings: &[u8], sentinel: &str) -> Result<Vec<u8>, WriteError> {
    let xml = std::str::from_utf8(shared_strings)
        .map_err(|_| WriteError::render("shared strings are not valid UTF-8"))?;
    for needle in [
        format!("<t>{sentinel}</t>"),
        format!("<t xml:space=\"preserve\">{sentinel}</t>"),
    ] {
        if let Some(start) = xml.find(&needle) {
            let mut replaced = String::with_capacity(xml.len());
            replaced.push_str(&xml[..start]);
            replaced.push_str("<t></t>");
            replaced.push_str(&xml[start + needle.len()..]);
            return Ok(replaced.into_bytes());
        }
    }
    Err(WriteError::render(
        "the empty-text placeholder was not found in the shared strings table",
    ))
}

/// Column indexes are bounded by `MAX_SHEET_COLS`, so the `u16` conversion is lossless.
fn col_u16(col: usize) -> u16 {
    col as u16
}

fn render_error(error: XlsxError) -> WriteError {
    WriteError::render(error.to_string())
}

fn render_error_zip(error: zip::result::ZipError) -> WriteError {
    WriteError::render(format!("xlsx archive: {error}"))
}

fn render_error_io(error: std::io::Error) -> WriteError {
    WriteError::render(format!("xlsx archive: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::spec::parse;

    fn write(json: &str) -> Vec<u8> {
        let spec = parse(json).unwrap();
        write_workbook(&spec).unwrap()
    }

    #[test]
    fn writes_zip_newline_and_recalc_marker() {
        let data = write(r#"{"sheets":[{"name":"Weekly","header":["h"],"rows":[[["num",1]]]}]}"#);
        assert_eq!(&data[..2], b"PK");
        assert!(data.len() > 500);
        let archive = read_archive(&data);
        let workbook_xml = String::from_utf8(archive.workbook_xml).unwrap();
        assert!(workbook_xml.contains(r#"fullCalcOnLoad="1""#));
        assert!(workbook_xml.contains(r#"calcPr calcId="124519""#));
    }

    #[test]
    fn formula_keeps_declared_cached_value() {
        let data = write(
            r#"{"sheets":[{"name":"S","header":["a","b"],"rows":[[["num",1],["num",2],["formula","SUM(A2:B2)",3]]]}]}"#,
        );
        let archive = read_archive(&data);
        let sheet_xml = String::from_utf8(archive.sheet_xml).unwrap();
        assert!(sheet_xml.contains("<f>SUM(A2:B2)</f>"));
        assert!(sheet_xml.contains("<v>3</v>"));
    }

    #[test]
    fn date_serial_uses_iso_format() {
        let data =
            write(r#"{"sheets":[{"name":"S","header":["d"],"rows":[[["date","2026-01-15"]]]}]}"#);
        let archive = read_archive(&data);
        let sheet_xml = String::from_utf8(archive.sheet_xml).unwrap();
        assert!(sheet_xml.contains("<v>46037</v>"));
        let styles_xml = String::from_utf8(archive.styles_xml).unwrap();
        assert!(styles_xml.contains("yyyy-mm-dd"));
    }

    #[test]
    fn freeze_and_columns_are_written() {
        let data = write(
            r#"{"sheets":[{"name":"S","header":["a","b"],"rows":[[["str","x"],["num",1]]],
                    "freeze":true,"col_widths":[12.5,8]}]}"#,
        );
        let archive = read_archive(&data);
        let sheet_xml = String::from_utf8(archive.sheet_xml).unwrap();
        assert!(sheet_xml.contains("pane") && sheet_xml.contains("frozen"));
        // XlsxWriter-compatible quantization: round(width * 7) + 5 pixels / 7.
        assert!(sheet_xml.contains(r#"width="13.28515625""#));
        assert!(sheet_xml.contains(r#"width="8.7109375""#));
    }

    #[test]
    fn unicode_and_leading_zero_strings_are_text_cells() {
        let data =
            write(r#"{"sheets":[{"name":"S","rows":[[["str","007"],["str","café 日本語"]]]}]}"#);
        let archive = read_archive(&data);
        let strings_xml = String::from_utf8(archive.shared_strings_xml).unwrap();
        assert!(strings_xml.contains("007"));
        assert!(strings_xml.contains("café 日本語"));
    }

    #[test]
    fn empty_string_cells_are_stored_as_text() {
        let data = write(
            r#"{"sheets":[{"name":"S","header":["a","b"],"rows":[[["num",5],["str",""]],[["num",6],["str",""]]]}]}"#,
        );
        let archive = read_archive(&data);
        let sheet_xml = String::from_utf8(archive.sheet_xml).unwrap();
        // Two header strings + the two empty-string cells are all shared-string cells.
        assert_eq!(
            sheet_xml.matches(r#"t="s""#).count(),
            4,
            "both empty cells are kept"
        );
        let strings_xml = String::from_utf8(archive.shared_strings_xml).unwrap();
        assert!(strings_xml.contains("<si><t></t></si>"));
        assert!(
            !strings_xml.contains(EMPTY_SENTINEL),
            "placeholder must be replaced"
        );
    }

    #[test]
    fn empty_string_placeholder_avoids_user_text() {
        let data = write(r#"{"sheets":[{"name":"S","rows":[[["str","\uE000"],["str",""]]]}]}"#);
        let archive = read_archive(&data);
        let strings_xml = String::from_utf8(archive.shared_strings_xml).unwrap();
        // The user's private-use character stays intact and the empty cell gets its own entry.
        assert_eq!(strings_xml.matches("<si>").count(), 2);
        assert!(strings_xml.contains("<si><t></t></si>"));
        // The user's own private-use text is preserved verbatim.
        assert!(strings_xml.contains("<si><t>\u{E000}</t></si>"));
    }

    struct Archive {
        workbook_xml: Vec<u8>,
        sheet_xml: Vec<u8>,
        styles_xml: Vec<u8>,
        shared_strings_xml: Vec<u8>,
    }

    fn read_archive(data: &[u8]) -> Archive {
        let mut zip = zip::ZipArchive::new(std::io::Cursor::new(data.to_vec())).unwrap();
        let mut read = |name: &str| -> Vec<u8> {
            use std::io::Read;
            let mut entry = zip.by_name(name).unwrap();
            let mut bytes = Vec::new();
            entry.read_to_end(&mut bytes).unwrap();
            bytes
        };
        Archive {
            workbook_xml: read("xl/workbook.xml"),
            sheet_xml: read("xl/worksheets/sheet1.xml"),
            styles_xml: read("xl/styles.xml"),
            shared_strings_xml: read("xl/sharedStrings.xml"),
        }
    }
}
