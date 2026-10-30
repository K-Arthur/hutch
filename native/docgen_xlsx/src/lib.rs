//! Optional native XLSX write kernel for Hutch's document generator.
//!
//! The pure-Rust core parses the normalized sheet JSON produced by `xlsx.py` and renders
//! the same workbook `_write_workbook` renders with XlsxWriter. The PyO3 binding lives
//! behind the non-default `python` feature and exposes:
//!
//! ```python
//! import hutch_docgen_native
//! data: bytes = hutch_docgen_native.write_workbook(spec_json)
//! ```
//!
//! Bad input raises `ValueError`; it never panics. The pure-Python writer remains the
//! reference implementation and the fallback.

pub mod error;
pub mod spec;
pub mod writer;

#[cfg(feature = "python")]
mod pyapi;

pub use error::WriteError;
pub use spec::{parse, Cell, Sheet, WorkbookSpec};
pub use writer::write_workbook;
